import hashlib
import secrets
import time
import sqlite3
import re

from config import DIGEST_NONCE_TTL_SECONDS


def create_nonce(connection: sqlite3.Connection) -> str:
    nonce = secrets.token_urlsafe(32)
    nonce_hash = hashlib.sha256(
        nonce.encode("ascii")
    ).hexdigest()

    created_at = int(time.time())
    expires_at = created_at + DIGEST_NONCE_TTL_SECONDS

    connection.execute(
        """
        INSERT INTO digest_nonces (
            nonce_hash,
            created_at,
            expires_at
        )
        VALUES (?, ?, ?)
        """,
        (nonce_hash, created_at, expires_at),
    )

    connection.commit()

    return nonce

def validate_nonce(
    connection: sqlite3.Connection,
    nonce: str
) -> str:
    if not isinstance(nonce, str) or not nonce:
        return "invalid"

    try:
        nonce_bytes = nonce.encode("ascii")
    except UnicodeEncodeError:
        return "invalid"

    nonce_hash = hashlib.sha256(nonce_bytes).hexdigest()

    row = connection.execute(
        """
        SELECT expires_at, is_revoked
        FROM digest_nonces
        WHERE nonce_hash = ?
        """,
        (nonce_hash,),
    ).fetchone()

    if row is None:
        return "invalid"

    if row["is_revoked"]:
        return "invalid"

    if row["expires_at"] <= int(time.time()):
        return "expired"

    return "valid"

def consume_nonce_count(
    connection: sqlite3.Connection,
    username: str,
    nonce: str,
    nonce_count: str,
    cnonce: str,
) -> bool:
    if not username or not nonce or not cnonce:
        return False

    if not re.fullmatch(r"[0-9a-fA-F]{8}", nonce_count):
        return False

    try:
        nonce_bytes = nonce.encode("ascii")
        cnonce.encode("ascii")
    except UnicodeEncodeError:
        return False

    count = int(nonce_count, 16)

    if count == 0:
        return False

    nonce_hash = hashlib.sha256(nonce_bytes).hexdigest()
    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        nonce_row = connection.execute(
            """
            SELECT expires_at, is_revoked
            FROM digest_nonces
            WHERE nonce_hash = ?
            """,
            (nonce_hash,),
        ).fetchone()

        if (
            nonce_row is None
            or nonce_row["is_revoked"]
            or nonce_row["expires_at"] <= current_time
        ):
            connection.rollback()
            return False

        previous = connection.execute(
            """
            SELECT MAX(nonce_count) AS max_count
            FROM digest_nonce_usage
            WHERE nonce_hash = ? AND username = ?
            """,
            (nonce_hash, username),
        ).fetchone()

        highest_count = previous["max_count"] or 0

        if count <= highest_count:
            connection.rollback()
            return False

        connection.execute(
            """
            INSERT INTO digest_nonce_usage (
                nonce_hash,
                username,
                nonce_count,
                cnonce,
                used_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                nonce_hash,
                username,
                count,
                cnonce,
                current_time,
            ),
        )

        connection.commit()
        return True

    except sqlite3.IntegrityError:
        connection.rollback()
        return False

    except Exception:
        connection.rollback()
        raise
