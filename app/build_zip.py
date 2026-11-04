"""Build the Elastic Beanstalk bundle using only deployment files."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
FILES = (
    "Procfile",
    "requirements.txt",
    ".ebextensions/01_init_db.config",
    "app/__init__.py",
    "app/main.py",
    "app/init_db.py",
    "app/seed.csv",
    "app/static/index.html",
    "app/static/app.js",
    "app/static/style.css",
)


def main() -> int:
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit("Missing deployment files: " + ", ".join(missing))

    output = ROOT / "quotes-eb.zip"
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, arcname=name)
    print(f"Created: {output}")
    print(f"Deployment files: {len(FILES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
