import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from session_service import create_session, revoke_session


BASE_URL = "http://127.0.0.1:5000"


def send_request(path, token, method="GET", payload=None):
    headers = {
        "Authorization": f"Bearer {token}",
    }

    data = None

    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
        headers=headers,
        method=method,
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
group_id = None

try:
    # Find the administrator.
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

    # Create an administrator session.
    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    print("Administrator session created: True")

    # Generate a unique group name.
    group_name = f"Test_Group_{secrets.token_hex(4)}"

    # Test 1: Create a group.
    status, result = send_request(
        "/api/admin/groups",
        admin_token,
        method="POST",
        payload={
            "name": group_name,
            "description": "Temporary group for API testing.",
        },
    )

    assert status == 201, result

    group_id = result["group_id"]

    print("Group creation status:", status)
    print("Group ID:", group_id)

    # Test 2: Duplicate group creation.
    status, _ = send_request(
        "/api/admin/groups",
        admin_token,
        method="POST",
        payload={
            "name": group_name,
            "description": "Duplicate group.",
        },
    )

    assert status == 409

    print("Duplicate group blocked:", status)

    # Test 3: List groups.
    status, result = send_request(
        "/api/admin/groups?limit=50&offset=0",
        admin_token,
    )

    assert status == 200

    groups = result["groups"]

    assert any(
        group["id"] == group_id
        and group["name"] == group_name
        for group in groups
    )

    print("Group list status:", status)
    print("Created group visible: True")

    # Test 4: Verify group properties.
    created_group = next(
        group for group in groups
        if group["id"] == group_id
    )

    assert created_group["is_active"] is True
    assert created_group["member_count"] == 0

    print("Group status correct: True")
    print("Initial member count:", created_group["member_count"])

    # Test 5: Missing authentication.
    status, _ = send_request(
        "/api/admin/groups",
        "",
    )

    assert status == 401

    print("Unauthenticated access blocked:", status)

    # Test 6: Invalid pagination.
    status, _ = send_request(
        "/api/admin/groups?limit=101&offset=0",
        admin_token,
    )

    assert status == 400

    print("Invalid pagination rejected:", status)

    print("All group management API tests passed")

finally:
    # Revoke the temporary administrator session.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    # Remove the temporary group.
    if group_id is not None:
        connection.execute(
            "DELETE FROM user_groups WHERE id = ?",
            (group_id,),
        )
        connection.commit()

    connection.close()