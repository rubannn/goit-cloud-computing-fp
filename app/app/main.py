import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import DateTime, String, Text, create_engine, func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Quote(Base):
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str] = mapped_column(String(200), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class QuoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    author: str = Field(default="", max_length=200)
    category: str = Field(default="", max_length=100)

    @field_validator("text", "author", "category", mode="before")
    @classmethod
    def trim_strings(cls, value):
        return value.strip() if isinstance(value, str) else value


class QuoteOutput(QuoteInput):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


def create_app(database_url: str | None = None) -> FastAPI:
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("Set DATABASE_URL before starting the application")
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    sessions = sessionmaker(engine)

    @asynccontextmanager
    async def lifespan(app):
        # Run `python -m app.init_db` once before deploying application replicas.
        yield
        engine.dispose()

    app = FastAPI(title="Quote Collection", lifespan=lifespan)

    def get_session():
        with sessions() as session:
            yield session

    db = Annotated[Session, Depends(get_session)]

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        logging.getLogger("uvicorn.error").error(
            "Database operation failed (%s)", type(exc).__name__
        )
        return JSONResponse(status_code=503, content={"detail": "Database unavailable"})

    @app.get("/health")
    def health(session: db):
        session.execute(text("SELECT 1 FROM quotes LIMIT 1"))
        return {"status": "ok"}

    def filtered_query(q: str, category: str):
        statement = select(Quote)
        if q.strip():
            statement = statement.where(or_(
                Quote.text.icontains(q.strip(), autoescape=True),
                Quote.author.icontains(q.strip(), autoescape=True),
            ))
        if category:
            statement = statement.where(Quote.category == category)
        return statement

    @app.get("/api/categories", response_model=list[str])
    def categories(session: db):
        return session.scalars(
            select(Quote.category).where(Quote.category != "").distinct().order_by(Quote.category)
        ).all()

    @app.get("/api/quotes", response_model=list[QuoteOutput])
    def quotes(
        session: db,
        q: str = Query(default="", max_length=200),
        category: str = Query(default="", max_length=100),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=50, ge=1, le=100),
    ):
        return session.scalars(
            filtered_query(q, category).order_by(Quote.created_at.desc(), Quote.id.desc())
            .offset(offset).limit(limit)
        ).all()

    @app.get("/api/quotes/random", response_model=QuoteOutput)
    def random_quote(
        session: db,
        q: str = Query(default="", max_length=200),
        category: str = Query(default="", max_length=100),
    ):
        quote = session.scalar(filtered_query(q, category).order_by(func.random()).limit(1))
        if quote is None:
            raise HTTPException(404, "No quotes found")
        return quote

    def find_quote(session: Session, quote_id: int):
        quote = session.get(Quote, quote_id)
        if quote is None:
            raise HTTPException(404, "Quote not found")
        return quote

    @app.get("/api/quotes/{quote_id}", response_model=QuoteOutput)
    def get_quote(quote_id: int, session: db):
        return find_quote(session, quote_id)

    @app.post("/api/quotes", response_model=QuoteOutput, status_code=201)
    def add_quote(payload: QuoteInput, session: db):
        quote = Quote(**payload.model_dump())
        session.add(quote)
        session.commit()
        session.refresh(quote)
        return quote

    @app.put("/api/quotes/{quote_id}", response_model=QuoteOutput)
    def update_quote(quote_id: int, payload: QuoteInput, session: db):
        quote = find_quote(session, quote_id)
        for key, value in payload.model_dump().items():
            setattr(quote, key, value)
        session.commit()
        session.refresh(quote)
        return quote

    @app.delete("/api/quotes/{quote_id}", status_code=204)
    def delete_quote(quote_id: int, session: db):
        session.delete(find_quote(session, quote_id))
        session.commit()
        return Response(status_code=204)

    static = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(static / "index.html")

    return app
