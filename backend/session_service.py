import hashlib
import secrets
import sqlite3
import time

from config import AUTH_SESSION_TTL_SECONDS


def hash_session_token(token: str) -> str:
    if not isinstance(token, str) or not token:
        raise ValueError("Session token must not be empty.")

    try:
        token_bytes = token.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Invalid session token format.") from None

    return hashlib.sha256(token_bytes).hexdigest()


def create_session(
    connection: sqlite3.Connection,
    user_id: int,
    credential_version: int,
) -> str:
    if user_id <= 0 or credential_version < 1:
        raise ValueError("Invalid session parameters.")

    token = secrets.token_urlsafe(32)
    token_hash = hash_session_token(token)

    created_at = int(time.time())
    expires_at = created_at + AUTH_SESSION_TTL_SECONDS

    try:
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
                token_hash,
                user_id,
                credential_version,
                created_at,
                expires_at,
            ),
        )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return token


def validate_session(
    connection: sqlite3.Connection,
    token: str,
) -> sqlite3.Row | None:
    try:
        token_hash = hash_session_token(token)
    except ValueError:
        return None

    current_time = int(time.time())

    session = connection.execute(
        """
        SELECT
            s.user_id,
            s.credential_version AS session_credential_version,
            s.created_at,
            s.expires_at,
            u.username,
            u.role,
            u.is_active,
            u.credential_version AS current_credential_version
        FROM auth_sessions AS s
        JOIN users AS u ON u.id = s.user_id
        WHERE s.session_token_hash = ?
          AND s.revoked_at IS NULL
          AND s.expires_at > ?
        """,
        (token_hash, current_time),
    ).fetchone()

    if session is None:
        return None

    if not session["is_active"]:
        return None

    if (
        session["session_credential_version"]
        != session["current_credential_version"]
    ):
        return None

    return session


def revoke_session(
    connection: sqlite3.Connection,
    token: str,
) -> bool:
    try:
        token_hash = hash_session_token(token)
    except ValueError:
        return False

    current_time = int(time.time())

    cursor = connection.execute(
        """
        UPDATE auth_sessions
        SET revoked_at = ?
        WHERE session_token_hash = ?
          AND revoked_at IS NULL
        """,
        (current_time, token_hash),
    )

    connection.commit()

    return cursor.rowcount == 1