import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from session_service import create_session, validate_session, revoke_session
from admin_service import change_user_role


BASE_URL = "http://127.0.0.1:5000"


def send_role_request(user_id, token, new_role):
    request = urllib.request.Request(
        f"{BASE_URL}/api/admin/users/{user_id}/role",
        data=json.dumps({"role": new_role}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
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

admin_token = None
temporary_tokens = []
temporary_user_ids = []

try:
    # Find the real administrator.
    admin = connection.execute(
        """
        SELECT id, role, is_active, credential_version
        FROM users
        WHERE username = 'student1'
        """
    ).fetchone()

    assert admin is not None
    assert admin["role"] == "admin"
    assert admin["is_active"] == 1

    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    # Create a temporary regular user.
    target_username = f"role_target_{secrets.token_hex(4)}"

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

    # Create a session before changing the role.
    old_target_token = create_session(
        connection,
        target_user_id,
        1,
    )
    temporary_tokens.append(old_target_token)

    print("Temporary user created: True")

    # Test 1: Promote regular user to admin.
    status, result = send_role_request(
        target_user_id,
        admin_token,
        "admin",
    )

    assert status == 200, result

    print("Promote user to admin:", status)

    target = connection.execute(
        """
        SELECT role, credential_version
        FROM users
        WHERE id = ?
        """,
        (target_user_id,),
    ).fetchone()

    assert target["role"] == "admin"
    assert target["credential_version"] == 2

    print("Role updated to admin: True")

    # The previous session must be invalid.
    assert validate_session(connection, old_target_token) is None

    print("Old session invalidated after promotion: True")

    # Create a new session for the promoted administrator.
    promoted_token = create_session(
        connection,
        target_user_id,
        2,
    )
    temporary_tokens.append(promoted_token)

    # Test 2: Demote the temporary administrator.
    status, result = send_role_request(
        target_user_id,
        admin_token,
        "user",
    )

    assert status == 200, result

    print("Demote admin to user:", status)

    target = connection.execute(
        """
        SELECT role, credential_version
        FROM users
        WHERE id = ?
        """,
        (target_user_id,),
    ).fetchone()

    assert target["role"] == "user"
    assert target["credential_version"] == 3

    print("Role updated to user: True")

    # The promoted administrator's session must also be invalid.
    assert validate_session(connection, promoted_token) is None

    print("Old admin session invalidated: True")

    # Test 3: Create another regular user.
    regular_username = f"role_regular_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (regular_username, "0" * 64),
    )

    regular_user_id = cursor.lastrowid

    if regular_user_id is None:
        raise RuntimeError("Failed to create regular user.")

    temporary_user_ids.append(regular_user_id)
    connection.commit()

    regular_token = create_session(
        connection,
        regular_user_id,
        1,
    )
    temporary_tokens.append(regular_token)

    # An ordinary user must not change another user's role.
    status, _ = send_role_request(
        regular_user_id,
        regular_token,
        "admin",
    )

    assert status == 403

    print("Regular user role change blocked:", status)

    # Test 4: Invalid role must be rejected.
    status, _ = send_role_request(
        regular_user_id,
        admin_token,
        "superadmin",
    )

    assert status == 400

    print("Invalid role rejected:", status)

    # Test 5: Administrator cannot change their own role.
    status, _ = send_role_request(
        admin["id"],
        admin_token,
        "user",
    )

    assert status == 409

    print("Admin self-role change blocked:", status)

    # Test 6: The last active administrator is protected.
    # The temporary admin has already been demoted.
    # student1 is now the only active administrator.
    result = change_user_role(
        connection,
        admin["id"],
        "user",
    )

    assert result == "last_admin"

    current_admin = connection.execute(
        """
        SELECT role
        FROM users
        WHERE id = ?
        """,
        (admin["id"],),
    ).fetchone()

    assert current_admin["role"] == "admin"

    print("Last active administrator protected: True")

    print("All admin role management tests passed")

finally:
    # Revoke temporary sessions.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    for token in temporary_tokens:
        revoke_session(connection, token)

    # Delete temporary users and their related records.
    for temporary_user_id in temporary_user_ids:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (temporary_user_id,),
        )

    connection.commit()
    connection.close()