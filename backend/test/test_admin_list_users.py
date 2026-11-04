import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from session_service import create_session, revoke_session


BASE_URL = "http://127.0.0.1:5000"


def send_request(path, token=None):
    headers = {}

    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers=headers,
        method="GET",
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
regular_token = None
temporary_user_id = None

try:
    # Find the administrator.
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

    # Create an administrator session.
    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    # Create a temporary regular user.
    username = f"list_test_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, "0" * 64),
    )

    temporary_user_id = cursor.lastrowid

    if temporary_user_id is None:
        raise RuntimeError("Failed to create test user.")

    connection.commit()

    # Create a regular user session.
    regular_token = create_session(
        connection,
        temporary_user_id,
        1,
    )

    print("Test accounts prepared: True")

    # Test 1: Administrator can list users.
    status, result = send_request(
        "/api/admin/users?limit=100&offset=0",
        admin_token,
    )

    assert status == 200

    assert result["status"] == "ok"
    assert result["total"] >= 2

    users = result["users"]

    assert any(
        user["username"] == username
        for user in users
    )

    print("Admin user list status:", status)
    print("Users returned:", len(users))
    print("Temporary user visible: True")

    # Test 2: Sensitive HA1 data must not be exposed.
    assert all("ha1" not in user for user in users)

    print("HA1 values hidden: True")

    # Test 3: Regular user must be blocked.
    status, _ = send_request(
        "/api/admin/users",
        regular_token,
    )

    assert status == 403

    print("Regular user access blocked:", status)

    # Test 4: Missing token must be rejected.
    status, _ = send_request(
        "/api/admin/users",
    )

    assert status == 401

    print("Unauthenticated access blocked:", status)

    # Test 5: Invalid pagination must be rejected.
    status, _ = send_request(
        "/api/admin/users?limit=101&offset=0",
        admin_token,
    )

    assert status == 400

    print("Invalid pagination rejected:", status)

    print("All admin user list tests passed")

finally:
    # Revoke temporary sessions.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    if regular_token is not None:
        revoke_session(connection, regular_token)

    # Delete the temporary test user.
    if temporary_user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (temporary_user_id,),
        )
        connection.commit()

    connection.close()
