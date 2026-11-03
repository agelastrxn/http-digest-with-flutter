import sqlite3
import time


def deactivate_user(
    connection: sqlite3.Connection,
    user_id: int,
) -> str:

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return "invalid_user_id"

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id, is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            connection.rollback()
            return "not_found"

        if not user["is_active"]:
            connection.rollback()
            return "already_disabled"

        connection.execute(
            """
            UPDATE users
            SET is_active = 0,
                credential_version = credential_version + 1
            WHERE id = ?
              AND is_active = 1
            """,
            (user_id,),
        )

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
        return "disabled"

    except Exception:
        connection.rollback()
        raise

def activate_user(
    connection: sqlite3.Connection,
    user_id: int,
) -> str:

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return "invalid_user_id"

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id, is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            connection.rollback()
            return "not_found"

        if user["is_active"]:
            connection.rollback()
            return "already_active"

        connection.execute(
            """
            UPDATE users
            SET is_active = 1,
                credential_version = credential_version + 1
            WHERE id = ?
              AND is_active = 0
            """,
            (user_id,),
        )

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
        return "enabled"

    except Exception:
        connection.rollback()
        raise

def change_user_role(
    connection: sqlite3.Connection,
    user_id: int,
    new_role: str,
) -> str:

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return "invalid_user_id"

    if new_role not in ("user", "admin"):
        return "invalid_role"

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id, role, is_active
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            connection.rollback()
            return "not_found"

        if user["role"] == new_role:
            connection.rollback()
            return "unchanged"

        # Protect the last active administrator.
        if (
            user["role"] == "admin"
            and new_role == "user"
            and user["is_active"]
        ):
            admin_count = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM users
                WHERE role = 'admin'
                  AND is_active = 1
                """
            ).fetchone()["total"]

            if admin_count <= 1:
                connection.rollback()
                return "last_admin"

        connection.execute(
            """
            UPDATE users
            SET role = ?,
                credential_version = credential_version + 1
            WHERE id = ?
            """,
            (new_role, user_id),
        )

        # Revoke all existing sessions after a role change.
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
        return "updated"

    except Exception:
        connection.rollback()
        raise