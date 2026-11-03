import hashlib
import re
import secrets
import sqlite3
import time

from config import (
    BACKUP_CODE_COUNT,
    AUTH_SESSION_TTL_SECONDS,
)


CODE_PATTERN = re.compile(r"^[A-Za-z0-9_-]{22}$")


def hash_backup_code(code: str) -> str:
    if not isinstance(code, str):
        raise ValueError("Backup code must be a string.")

    code = code.strip()

    if not CODE_PATTERN.fullmatch(code):
        raise ValueError("Invalid backup code format.")

    return hashlib.sha256(code.encode("ascii")).hexdigest()

def generate_backup_codes(
    connection: sqlite3.Connection,
    user_id: int,
) -> list[str]:

    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise ValueError("Invalid user ID.")

    codes = [
        secrets.token_urlsafe(16)
        for _ in range(BACKUP_CODE_COUNT)
    ]

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            "SELECT id FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if user is None:
            raise ValueError("User does not exist.")

        connection.execute(
            """
            UPDATE backup_codes
            SET revoked_at = ?
            WHERE user_id = ?
              AND used_at IS NULL
              AND revoked_at IS NULL
            """,
            (current_time, user_id),
        )

        connection.executemany(
            """
            INSERT INTO backup_codes (
                code_hash,
                user_id,
                created_at
            )
            VALUES (?, ?, ?)
            """,
            [
                (hash_backup_code(code), user_id, current_time)
                for code in codes
            ],
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return codes

def consume_backup_code(
    connection: sqlite3.Connection,
    user_id: int,
    code: str,
) -> bool:

    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        return False

    try:
        code_hash = hash_backup_code(code)
    except ValueError:
        return False

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            UPDATE backup_codes
            SET used_at = ?
            WHERE code_hash = ?
              AND user_id = ?
              AND used_at IS NULL
              AND revoked_at IS NULL
            """,
            (current_time, code_hash, user_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise

def consume_backup_code_and_create_session(
    connection: sqlite3.Connection,
    user_id: int,
    code: str,
) -> str | None:

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return None

    try:
        code_hash = hash_backup_code(code)
    except ValueError:
        return None

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id, credential_version
            FROM users
            WHERE id = ? AND is_active = 1
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            connection.rollback()
            return None

        cursor = connection.execute(
            """
            UPDATE backup_codes
            SET used_at = ?
            WHERE code_hash = ?
              AND user_id = ?
              AND used_at IS NULL
              AND revoked_at IS NULL
            """,
            (current_time, code_hash, user_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return None

        session_token = secrets.token_urlsafe(32)

        session_token_hash = hashlib.sha256(
            session_token.encode("ascii")
        ).hexdigest()

        expires_at = current_time + AUTH_SESSION_TTL_SECONDS

        connection.execute(
            """
            INSERT INTO auth_sessions (
                session_token_hash,
                user_id,
                credential_version,
                created_at,
                expires_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_token_hash,
                user["id"],
                user["credential_version"],
                current_time,
                expires_at,
            ),
        )

        connection.commit()

        return session_token

    except Exception:
        connection.rollback()
        raise

def recover_password_with_backup_code(
    connection: sqlite3.Connection,
    user_id: int,
    backup_code: str,
    new_ha1: str,
) -> bool:

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return False

    if not isinstance(new_ha1, str) or not re.fullmatch(
        r"[0-9a-f]{64}", new_ha1
    ):
        return False

    try:
        code_hash = hash_backup_code(backup_code)
    except ValueError:
        return False

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id
            FROM users AS u
            WHERE u.id = ?
              AND u.is_active = 1
              AND NOT EXISTS (
                  SELECT 1
                  FROM group_members AS gm
                  JOIN user_groups AS g
                    ON g.id = gm.group_id
                  WHERE gm.user_id = u.id
                    AND g.is_active = 0
              )
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            connection.rollback()
            return False

        cursor = connection.execute(
            """
            UPDATE backup_codes
            SET used_at = ?
            WHERE code_hash = ?
              AND user_id = ?
              AND used_at IS NULL
              AND revoked_at IS NULL
            """,
            (current_time, code_hash, user_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        cursor = connection.execute(
            """
            UPDATE users
            SET ha1 = ?,
                credential_version = credential_version + 1
            WHERE id = ?
              AND is_active = 1
            """,
            (new_ha1, user_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return False

        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE user_id = ?
              AND revoked_at IS NULL
            """,
            (current_time, user_id),
        )

        connection.commit()
        return True

    except Exception:
        connection.rollback()
        raise
