import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from config import DIGEST_REALM
from digest_auth import parse_digest_authorization
from digest_utils import (
    calculate_ha1,
    calculate_ha2,
    calculate_digest_response,
)
from session_service import create_session, validate_session, revoke_session
from group_service import create_group, add_user_to_group
from backup_code_service import generate_backup_codes


BASE_URL = "http://127.0.0.1:5000"

TEST_PASSWORD = "GroupSecurityTest123!"


def send_request(path, method="GET", token=None, payload=None):
    headers = {}
    data = None

    if token:
        headers["Authorization"] = f"Bearer {token}"

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


def digest_login_status(username, password):
    login_url = f"{BASE_URL}/api/auth/digest"
    method = "POST"
    uri = "/api/auth/digest"

    # Request the initial Digest challenge.
    initial_request = urllib.request.Request(
        login_url,
        data=b"",
        method=method,
    )

    try:
        urllib.request.urlopen(initial_request, timeout=5)
        raise RuntimeError("Expected Digest challenge.")

    except urllib.error.HTTPError as error:
        if error.code != 401:
            raise

        challenge_header = error.headers.get("WWW-Authenticate")

    if not challenge_header:
        raise RuntimeError("Digest challenge header is missing.")

    challenge = parse_digest_authorization(challenge_header)

    # Calculate the Digest response.
    ha1 = calculate_ha1(
        username,
        password,
        challenge["realm"],
    )

    ha2 = calculate_ha2(method, uri)

    nc = "00000001"
    cnonce = secrets.token_hex(16)

    response_hash = calculate_digest_response(
        ha1=ha1,
        nonce=challenge["nonce"],
        nonce_count=nc,
        client_nonce=cnonce,
        qop=challenge["qop"],
        ha2=ha2,
    )

    authorization = (
        f'Digest username="{username}", '
        f'realm="{challenge["realm"]}", '
        f'nonce="{challenge["nonce"]}", '
        f'uri="{uri}", '
        f'algorithm={challenge["algorithm"]}, '
        f'qop={challenge["qop"]}, '
        f'nc={nc}, '
        f'cnonce="{cnonce}", '
        f'response="{response_hash}"'
    )

    authenticated_request = urllib.request.Request(
        login_url,
        data=b"",
        headers={"Authorization": authorization},
        method=method,
    )

    try:
        with urllib.request.urlopen(
            authenticated_request,
            timeout=5,
        ) as response:
            return response.status

    except urllib.error.HTTPError as error:
        return error.code


connection = get_db_connection()

admin_token = None
old_user_token = None
new_user_token = None

temporary_user_id = None
group_id = None

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

    admin_token = create_session(
        connection,
        admin["id"],
        admin["credential_version"],
    )

    # 2. Create a temporary user.
    username = f"group_security_{secrets.token_hex(4)}"

    user_ha1 = calculate_ha1(
        username,
        TEST_PASSWORD,
        DIGEST_REALM,
    )

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, user_ha1),
    )

    temporary_user_id = cursor.lastrowid

    if temporary_user_id is None:
        raise RuntimeError("Failed to create temporary user.")

    connection.commit()

    # 3. Create a group and add the user.
    status, group_id = create_group(
        connection,
        f"Security_Test_{secrets.token_hex(4)}",
        "Temporary group security test.",
    )

    assert status == "created"
    assert group_id is not None

    add_result = add_user_to_group(
        connection,
        group_id,
        temporary_user_id,
    )

    assert add_result == "added"

    # 4. Generate backup codes.
    backup_codes = generate_backup_codes(
        connection,
        temporary_user_id,
    )

    test_backup_code = backup_codes[0]

    print("Temporary user and group created: True")
    print("Backup codes generated: True")

    # 5. Create a session while the group is active.
    user = connection.execute(
        """
        SELECT credential_version
        FROM users
        WHERE id = ?
        """,
        (temporary_user_id,),
    ).fetchone()

    old_user_token = create_session(
        connection,
        temporary_user_id,
        user["credential_version"],
    )

    assert validate_session(connection, old_user_token) is not None

    print("Session before group deactivation: valid")

    # 6. Administrator disables the group.
    status, result = send_request(
        f"/api/admin/groups/{group_id}/status",
        method="PATCH",
        token=admin_token,
        payload={"is_active": False},
    )

    assert status == 200, result

    print("Group deactivation status:", status)

    # 7. Existing session must become invalid.
    assert validate_session(connection, old_user_token) is None

    print("Existing session rejected: True")

    # 8. Digest login must be blocked.
    digest_status = digest_login_status(
        username,
        TEST_PASSWORD,
    )

    assert digest_status == 401

    print("Digest login blocked:", digest_status)

    # 9. Backup login must also be blocked.
    status, _ = send_request(
        "/api/auth/backup-login",
        method="POST",
        payload={
            "username": username,
            "backup_code": test_backup_code,
        },
    )

    assert status == 401

    print("Backup login blocked:", status)

    # 10. Administrator reactivates the group.
    status, result = send_request(
        f"/api/admin/groups/{group_id}/status",
        method="PATCH",
        token=admin_token,
        payload={"is_active": True},
    )

    assert status == 200, result

    print("Group reactivation status:", status)

    # 11. The old session must still be invalid.
    assert validate_session(connection, old_user_token) is None

    print("Old session remains invalid: True")

    # 12. The unused backup code must still work.
    status, result = send_request(
        "/api/auth/backup-login",
        method="POST",
        payload={
            "username": username,
            "backup_code": test_backup_code,
        },
    )

    assert status == 200, result

    new_user_token = result["session_token"]

    print("Backup login after reactivation:", status)

    # 13. Verify the new session.
    new_session = validate_session(
        connection,
        new_user_token,
    )

    assert new_session is not None
    assert new_session["username"] == username

    print("New session after reactivation: valid")
    print("All group security tests passed")

finally:
    # Revoke temporary sessions.
    if admin_token is not None:
        revoke_session(connection, admin_token)

    if old_user_token is not None:
        revoke_session(connection, old_user_token)

    if new_user_token is not None:
        revoke_session(connection, new_user_token)

    # Delete temporary group and user.
    if group_id is not None:
        connection.execute(
            "DELETE FROM user_groups WHERE id = ?",
            (group_id,),
        )

    if temporary_user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (temporary_user_id,),
        )

    connection.commit()
    connection.close()