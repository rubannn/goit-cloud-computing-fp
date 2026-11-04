"""Create the schema and optionally seed an empty quotes table before deployment."""
import argparse
import csv
import os
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from .main import Base, Quote, QuoteInput


DEFAULT_SEED = Path(__file__).with_name("seed.csv")


def load_seed(path: Path) -> list[QuoteInput]:
    """Validate the entire CSV before any rows are inserted."""
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source, strict=True)
        if reader.fieldnames != ["text", "author", "category"]:
            raise ValueError("CSV header must be: text,author,category")
        quotes = []
        for row in reader:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"Invalid column count at CSV line {reader.line_num}")
            try:
                quotes.append(QuoteInput.model_validate(row))
            except ValidationError:
                # Do not print CSV contents in deployment logs.
                raise ValueError(f"Invalid quote at CSV line {reader.line_num}") from None
        return quotes


def initialize_database(database_url: str, seed_path: Path | None = None) -> int:
    """Seed only an empty table; preserve existing quotes on repeated deployments."""
    engine = create_engine(database_url)
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session, session.begin():
            if session.scalar(select(Quote.id).limit(1)) is not None:
                return 0
            path = DEFAULT_SEED if seed_path is None else seed_path
            if seed_path is None and not path.exists():
                return 0
            quotes = load_seed(path)
            session.add_all(Quote(**quote.model_dump()) for quote in quotes)
            return len(quotes)
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed", type=Path,
        help="CSV file to load into an empty table (default: seed.csv beside this module)",
    )
    args = parser.parse_args()
    try:
        inserted = initialize_database(os.environ["DATABASE_URL"], args.seed)
    except (OSError, ValueError, csv.Error) as exc:
        parser.exit(1, f"Database initialization failed: {exc}\n")
    print(f"Database initialized; seeded {inserted} quotes.")


if __name__ == "__main__":
    main()
