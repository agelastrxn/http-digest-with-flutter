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

        connection.execute("""
            CREATE TABLE IF NOT EXISTS auth_sessions (
                session_token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                credential_version INTEGER NOT NULL
                    CHECK (credential_version >= 1),
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                revoked_at INTEGER,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)


        connection.execute("""
            CREATE TABLE IF NOT EXISTS backup_codes (
                code_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at INTEGER NOT NULL,
                used_at INTEGER,
                revoked_at INTEGER,
                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_backup_codes_user_id
            ON backup_codes(user_id)
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id
            ON auth_sessions(user_id)
        """)


        connection.execute("""
            CREATE TABLE IF NOT EXISTS user_groups (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1
                    CHECK (is_active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS group_members (
                group_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

                PRIMARY KEY (group_id, user_id),

                FOREIGN KEY (group_id)
                    REFERENCES user_groups(id)
                    ON DELETE CASCADE,

                FOREIGN KEY (user_id)
                    REFERENCES users(id)
                    ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_group_members_user_id
            ON group_members(user_id)
        """)

        connection.commit()
    finally:
        connection.close()

    print(f"Database created or verified: {DATABASE_PATH}")
    print("Table ready: users")


if __name__ == "__main__":
    initialize_database()