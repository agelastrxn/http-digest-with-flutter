import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from session_service import (
    create_session,
    validate_session,
    revoke_session,
)


BASE_URL = "http://127.0.0.1:5000"


def send_disable_request(user_id, token):
    request = urllib.request.Request(
        f"{BASE_URL}/api/admin/users/{user_id}/disable",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        return error.code, json.loads(
            error.read().decode("utf-8")
        )


connection = get_db_connection()

temporary_user_ids = []
admin_token = None

try:
    # Find the existing administrator.
    admin = connection.execute(
        """
        SELECT id, credential_version, role, is_active
        FROM users
        WHERE username = 'student1'
        """
    ).fetchone()

    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["is_active"] == 1

    # Create an admin session for testing.
    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    # Create a temporary target user.
    target_username = f"disable_target_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (target_username, "0" * 64),
    )

    target_user_id = cursor.lastrowid

    if target_user_id is None:
        raise RuntimeError("Failed to create target user.")

    temporary_user_ids.append(target_user_id)
    connection.commit()

    # Create a session for the target user.
    target_token = create_session(
        connection,
        target_user_id,
        1,
    )

    assert validate_session(connection, target_token) is not None

    print("Target user created: True")
    print("Target session initially valid: True")

    # Admin disables the target account.
    status, result = send_disable_request(
        target_user_id,
        admin_token,
    )

    assert status == 200, result

    print("Admin disable status:", status)

    # Verify that the account is disabled.
    target_user = connection.execute(
        """
        SELECT is_active, credential_version
        FROM users
        WHERE id = ?
        """,
        (target_user_id,),
    ).fetchone()

    assert target_user["is_active"] == 0
    assert target_user["credential_version"] == 2

    print("Target account disabled: True")

    # Verify that the old session is invalid.
    assert validate_session(connection, target_token) is None

    print("Target session revoked: True")

    # Test that an administrator cannot disable their own account.
    status, _ = send_disable_request(
        admin["id"],
        admin_token,
    )

    assert status == 409

    print("Admin self-deactivation blocked: True")

    # Create a temporary ordinary user.
    regular_username = f"regular_test_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (regular_username, "0" * 64),
    )

    regular_user_id = cursor.lastrowid

    if regular_user_id is None:
        raise RuntimeError("Failed to create regular test user.")

    temporary_user_ids.append(regular_user_id)
    connection.commit()

    regular_token = create_session(
        connection,
        regular_user_id,
        1,
    )

    # Create another temporary target user.
    second_target_username = f"target_test_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (second_target_username, "0" * 64),
    )

    second_target_id = cursor.lastrowid

    if second_target_id is None:
        raise RuntimeError("Failed to create second target user.")

    temporary_user_ids.append(second_target_id)
    connection.commit()

    # An ordinary user must not be able to disable another account.
    status, _ = send_disable_request(
        second_target_id,
        regular_token,
    )

    assert status == 403

    print("Regular user admin access blocked: True")

    print("All admin disable tests passed")

finally:
    # Revoke the temporary administrator session.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    # Remove all temporary test users.
    for temporary_user_id in temporary_user_ids:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (temporary_user_id,),
        )

    connection.commit()
    connection.close()