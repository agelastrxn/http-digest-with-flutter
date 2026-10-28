from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DATABASE_DIR = BASE_DIR / "instance"
DATABASE_PATH = DATABASE_DIR / "auth.db"


def initialize_database():
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                ha1 TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user'
                    CHECK (role IN ('user', 'admin')),
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1)),
                credential_version INTEGER NOT NULL DEFAULT 1
                    CHECK (credential_version >= 1),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.commit()
    finally:
        connection.close()

    print(f"Database created or verified: {DATABASE_PATH}")
    print("Table ready: users")


if __name__ == "__main__":
    initialize_database()