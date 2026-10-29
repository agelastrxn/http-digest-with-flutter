from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "instance"
DATABASE_PATH = DATABASE_DIR / "auth.db"


def get_db_connection() -> sqlite3.Connection:
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            "Database not found. Run 'python init_db.py' first."
        )

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=5.0
    )

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection