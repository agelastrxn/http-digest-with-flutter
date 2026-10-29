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

        connection.execute("""
            CREATE TABLE IF NOT EXISTS digest_nonces (
                nonce_hash TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                is_revoked INTEGER NOT NULL DEFAULT 0
                    CHECK (is_revoked IN (0, 1))
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS digest_nonce_usage (
                nonce_hash TEXT NOT NULL,
                username TEXT NOT NULL,
                nonce_count INTEGER NOT NULL
                    CHECK (nonce_count BETWEEN 1 AND 4294967295),
                cnonce TEXT NOT NULL,
                used_at INTEGER NOT NULL,
                PRIMARY KEY (nonce_hash, username, nonce_count),
                FOREIGN KEY (nonce_hash)
                    REFERENCES digest_nonces(nonce_hash)
                    ON DELETE CASCADE
            )
        """)

        connection.commit()
    finally:
        connection.close()

    print(f"Database created or verified: {DATABASE_PATH}")
    print("Table ready: users")


if __name__ == "__main__":
    initialize_database()