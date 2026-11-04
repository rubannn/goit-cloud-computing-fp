"""Test the initialization CLI using isolated SQLite databases."""
from contextlib import closing
import csv
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.database = Path(self.temp.name) / "quotes.db"
        self.seed = Path(self.temp.name) / "seed.csv"
        self.env = dict(os.environ, DATABASE_URL=f"sqlite:///{self.database}")

    def write_seed(self, rows):
        with self.seed.open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["text", "author", "category"])
            writer.writerows(rows)

    def initialize(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "app.init_db", *map(str, args)],
            cwd=ROOT, env=self.env, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )

    def records(self):
        with closing(sqlite3.connect(self.database)) as connection, connection:
            return connection.execute(
                "SELECT text, author, category, created_at FROM quotes ORDER BY id"
            ).fetchall()

    def test_imports_bom_unicode_and_quoted_multiline_fields(self):
        text = "  \u0426\u0438\u0442\u0430\u0442\u0430, \"example\"\nSecond line  "
        self.write_seed([(text, " Author ", " Learning "), ("Another quote", "", "")])
        result = self.initialize("--seed", self.seed)
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = self.records()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][:3], (text.strip(), "Author", "Learning"))
        self.assertTrue(rows[0][3])
        self.assertEqual(rows[1][:3], ("Another quote", "", ""))

    def test_reinitialization_preserves_edits_and_deletions(self):
        self.write_seed([("Original", "Author", "Life"), ("To delete", "", "")])
        result = self.initialize("--seed", self.seed)
        self.assertEqual(result.returncode, 0, result.stderr)
        with closing(sqlite3.connect(self.database)) as connection, connection:
            connection.execute("UPDATE quotes SET text='Edited' WHERE id=1")
            connection.execute("DELETE FROM quotes WHERE id=2")
        result = self.initialize("--seed", self.seed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("seeded 0 quotes", result.stdout)
        self.assertEqual([row[0] for row in self.records()], ["Edited"])

    def test_invalid_row_leaves_no_partial_import(self):
        for invalid in [("   ", "", ""), ("x" * 5001, "", ""), ("x", "a" * 201, "")]:
            with self.subTest(invalid_length=len(invalid[0])):
                self.write_seed([("Valid", "", ""), invalid])
                result = self.initialize("--seed", self.seed)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Invalid quote at CSV line 3", result.stderr)
                self.assertEqual(self.records(), [])

    def test_bad_header_column_count_or_quoting_fails(self):
        for contents in [
            "quote,author,category\nExample,A,B\n",
            "text,author,category\nExample,A\n",
            "text,author,category\nExample,A,B,Extra\n",
            'text,author,category\n"Unclosed,A,B\n',
        ]:
            with self.subTest(contents=contents):
                self.seed.write_text(contents, encoding="utf-8")
                result = self.initialize("--seed", self.seed)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.records(), [])

    def test_explicit_missing_file_fails(self):
        result = self.initialize("--seed", self.seed)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.records(), [])

    def test_normal_command_loads_bundled_seed(self):
        result = self.initialize()
        self.assertEqual(result.returncode, 0, result.stderr)
        with (ROOT / "app" / "seed.csv").open(encoding="utf-8-sig", newline="") as source:
            expected = list(csv.DictReader(source))
        self.assertEqual(
            [row[:3] for row in self.records()],
            [(r["text"].strip(), r["author"].strip(), r["category"].strip()) for r in expected],
        )


if __name__ == "__main__":
    unittest.main()
