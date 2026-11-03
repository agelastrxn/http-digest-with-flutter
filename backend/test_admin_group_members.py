import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from group_service import create_group
from session_service import (
    create_session,
    validate_session,
    revoke_session,
)


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
regular_token = None
old_target_token = None
target_token = None

group_id = None
target_user_id = None
second_user_id = None

try:
    # 1. Find the administrator.
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

    # Create administrator session.
    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    # 2. Create a temporary group.
    group_name = f"Membership_Test_{secrets.token_hex(4)}"

    status, created_group_id = create_group(
        connection,
        group_name,
        "Temporary membership test group.",
    )

    assert status == "created"
    assert created_group_id is not None

    group_id = created_group_id

    # 3. Create two temporary users.
    target_username = f"member_test_{secrets.token_hex(4)}"
    second_username = f"member_test_{secrets.token_hex(4)}"

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

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (second_username, "0" * 64),
    )

    second_user_id = cursor.lastrowid

    if second_user_id is None:
        raise RuntimeError("Failed to create second user.")

    connection.commit()

    print("Test group and users created: True")

    # 4. Create a session before group membership.
    old_target_token = create_session(
        connection,
        target_user_id,
        1,
    )

    assert validate_session(
        connection,
        old_target_token,
    ) is not None

    # 5. Admin adds the target user to the group.
    status, result = send_request(
        f"/api/admin/groups/{group_id}/members",
        admin_token,
        method="POST",
        payload={"user_id": target_user_id},
    )

    assert status == 201, result

    print("Add user to group:", status)

    # 6. Verify that the previous session is invalid.
    assert validate_session(
        connection,
        old_target_token,
    ) is None

    print("Previous user session revoked: True")

    # 7. Duplicate membership must be rejected.
    status, _ = send_request(
        f"/api/admin/groups/{group_id}/members",
        admin_token,
        method="POST",
        payload={"user_id": target_user_id},
    )

    assert status == 409

    print("Duplicate membership blocked:", status)

    # 8. Create a new session for the regular user.
    target = connection.execute(
        """
        SELECT credential_version
        FROM users
        WHERE id = ?
        """,
        (target_user_id,),
    ).fetchone()

    target_token = create_session(
        connection,
        target_user_id,
        target["credential_version"],
    )

    regular_token = target_token

    # 9. A regular user must not add another user to a group.
    status, _ = send_request(
        f"/api/admin/groups/{group_id}/members",
        regular_token,
        method="POST",
        payload={"user_id": second_user_id},
    )

    assert status == 403

    print("Regular user access blocked:", status)

    # 10. Admin removes the target user from the group.
    status, result = send_request(
        f"/api/admin/groups/{group_id}/members/{target_user_id}",
        admin_token,
        method="DELETE",
    )

    assert status == 200, result

    print("Remove user from group:", status)

    # 11. Removing the user must revoke their session.
    assert validate_session(
        connection,
        target_token,
    ) is None

    print("Session revoked after removal: True")

    # 12. Removing a non-member must return 404.
    status, _ = send_request(
        f"/api/admin/groups/{group_id}/members/{target_user_id}",
        admin_token,
        method="DELETE",
    )

    assert status == 404

    print("Non-member removal rejected:", status)

    # 13. Verify final group membership count.
    status, result = send_request(
        "/api/admin/groups?limit=100&offset=0",
        admin_token,
    )

    assert status == 200

    group = next(
        item for item in result["groups"]
        if item["id"] == group_id
    )

    assert group["member_count"] == 0

    print("Final group member count:", group["member_count"])

    print("All group membership API tests passed")

finally:
    # Revoke temporary sessions.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    if regular_token is not None:
        revoke_session(connection, regular_token)

    if old_target_token is not None:
        revoke_session(connection, old_target_token)

    # Remove temporary group and users.
    if group_id is not None:
        connection.execute(
            "DELETE FROM user_groups WHERE id = ?",
            (group_id,),
        )

    for user_id in (target_user_id, second_user_id):
        if user_id is not None:
            connection.execute(
                "DELETE FROM users WHERE id = ?",
                (user_id,),
            )

    connection.commit()
    connection.close()