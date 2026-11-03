import sqlite3
import time


def create_group(
    connection: sqlite3.Connection,
    name: str,
    description: str = "",
) -> tuple[str, int | None]:

    if not isinstance(name, str) or not name.strip():
        return "invalid_group_name", None

    if not isinstance(description, str):
        return "invalid_description", None

    name = name.strip()
    description = description.strip()

    if len(name) > 80 or len(description) > 250:
        return "invalid_group_data", None

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            INSERT INTO user_groups (name, description)
            VALUES (?, ?)
            """,
            (name, description),
        )

        group_id = cursor.lastrowid

        if group_id is None:
            connection.rollback()
            return "creation_failed", None

        connection.commit()

        return "created", group_id

    except sqlite3.IntegrityError:
        connection.rollback()
        return "already_exists", None

    except Exception:
        connection.rollback()
        raise

def add_user_to_group(
    connection: sqlite3.Connection,
    group_id: int,
    user_id: int,
) -> str:

    if (
        not isinstance(group_id, int)
        or isinstance(group_id, bool)
        or group_id <= 0
        or not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return "invalid_id"

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        group = connection.execute(
            """
            SELECT id, is_active
            FROM user_groups
            WHERE id = ?
            """,
            (group_id,),
        ).fetchone()

        if group is None:
            connection.rollback()
            return "group_not_found"

        if not group["is_active"]:
            connection.rollback()
            return "group_disabled"

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
            return "user_not_found"

        if not user["is_active"]:
            connection.rollback()
            return "user_disabled"

        connection.execute(
            """
            INSERT INTO group_members (group_id, user_id)
            VALUES (?, ?)
            """,
            (group_id, user_id),
        )

        connection.execute(
            """
            UPDATE users
            SET credential_version = credential_version + 1
            WHERE id = ?
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
        return "added"

    except sqlite3.IntegrityError:
        connection.rollback()
        return "already_member"

    except Exception:
        connection.rollback()
        raise

def remove_user_from_group(
    connection: sqlite3.Connection,
    group_id: int,
    user_id: int,
) -> str:

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        cursor = connection.execute(
            """
            DELETE FROM group_members
            WHERE group_id = ? AND user_id = ?
            """,
            (group_id, user_id),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return "not_member"

        connection.execute(
            """
            UPDATE users
            SET credential_version = credential_version + 1
            WHERE id = ?
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
        return "removed"

    except Exception:
        connection.rollback()
        raise

def set_group_active(
    connection: sqlite3.Connection,
    group_id: int,
    is_active: bool,
) -> str:

    if (
        not isinstance(group_id, int)
        or isinstance(group_id, bool)
        or group_id <= 0
    ):
        return "invalid_group_id"

    if not isinstance(is_active, bool):
        return "invalid_status"

    current_time = int(time.time())

    try:
        connection.execute("BEGIN IMMEDIATE")

        group = connection.execute(
            """
            SELECT id, is_active
            FROM user_groups
            WHERE id = ?
            """,
            (group_id,),
        ).fetchone()

        if group is None:
            connection.rollback()
            return "not_found"

        if bool(group["is_active"]) == is_active:
            connection.rollback()
            return "unchanged"

        if not is_active:
            available_admins = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM users AS u
                WHERE u.role = 'admin'
                  AND u.is_active = 1
                  AND NOT EXISTS (
                      SELECT 1
                      FROM group_members AS gm
                      JOIN user_groups AS g
                        ON g.id = gm.group_id
                      WHERE gm.user_id = u.id
                        AND (
                            g.is_active = 0
                            OR g.id = ?
                        )
                  )
                """,
                (group_id,),
            ).fetchone()["total"]

            if available_admins == 0:
                connection.rollback()
                return "last_admin"

        connection.execute(
            """
            UPDATE user_groups
            SET is_active = ?
            WHERE id = ?
            """,
            (int(is_active), group_id),
        )

        connection.execute(
            """
            UPDATE users
            SET credential_version = credential_version + 1
            WHERE id IN (
                SELECT user_id
                FROM group_members
                WHERE group_id = ?
            )
            """,
            (group_id,),
        )

        connection.execute(
            """
            UPDATE auth_sessions
            SET revoked_at = ?
            WHERE user_id IN (
                SELECT user_id
                FROM group_members
                WHERE group_id = ?
            )
              AND revoked_at IS NULL
            """,
            (current_time, group_id),
        )

        connection.commit()

        return "enabled" if is_active else "disabled"

    except Exception:
        connection.rollback()
        raise

def list_groups(
    connection: sqlite3.Connection,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[sqlite3.Row], int]:

    rows = connection.execute(
        """
        SELECT
            g.id,
            g.name,
            g.description,
            g.is_active,
            g.created_at,
            COUNT(gm.user_id) AS member_count
        FROM user_groups AS g
        LEFT JOIN group_members AS gm
            ON g.id = gm.group_id
        GROUP BY g.id
        ORDER BY g.id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    total = connection.execute(
        "SELECT COUNT(*) AS total FROM user_groups"
    ).fetchone()["total"]

    return rows, total

def list_group_members(
    connection: sqlite3.Connection,
    group_id: int,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[sqlite3.Row], int]:

    rows = connection.execute(
        """
        SELECT
            u.id,
            u.username,
            u.role,
            u.is_active
        FROM group_members AS gm
        INNER JOIN users AS u
            ON gm.user_id = u.id
        WHERE gm.group_id = ?
        ORDER BY u.id
        LIMIT ? OFFSET ?
        """,
        (group_id, limit, offset),
    ).fetchall()

    total = connection.execute(
        """
        SELECT COUNT(*) AS total
        FROM group_members
        WHERE group_id = ?
        """,
        (group_id,),
    ).fetchone()["total"]

    return rows, total

def user_has_disabled_group(
    connection: sqlite3.Connection,
    user_id: int,
) -> bool:

    result = connection.execute(
        """
        SELECT 1
        FROM group_members AS gm
        JOIN user_groups AS g
            ON g.id = gm.group_id
        WHERE gm.user_id = ?
          AND g.is_active = 0
        LIMIT 1
        """,
        (user_id,),
    ).fetchone()

    return result is not None