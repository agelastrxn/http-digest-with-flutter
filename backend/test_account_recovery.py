import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from backup_code_service import generate_backup_codes
from session_service import create_session, validate_session

from digest_auth import parse_digest_authorization
from digest_utils import (
    calculate_ha1,
    calculate_ha2,
    calculate_digest_response,
)


BASE_URL = "http://127.0.0.1:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/digest"
RECOVERY_URL = f"{BASE_URL}/api/auth/recover"

INITIAL_PASSWORD = "RecoveryInitialPassword123!"
NEW_PASSWORD = "RecoveryNewPassword456!"


def send_json_request(url, payload):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
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


def digest_login(username, password):
    initial_request = urllib.request.Request(
        LOGIN_URL,
        data=b"",
        method="POST",
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

    method = "POST"
    uri = "/api/auth/digest"
    nonce_count = "00000001"
    client_nonce = secrets.token_hex(16)

    ha1 = calculate_ha1(
        username,
        password,
        challenge["realm"],
    )

    ha2 = calculate_ha2(method, uri)

    response_hash = calculate_digest_response(
        ha1=ha1,
        nonce=challenge["nonce"],
        nonce_count=nonce_count,
        client_nonce=client_nonce,
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
        f'nc={nonce_count}, '
        f'cnonce="{client_nonce}", '
        f'response="{response_hash}"'
    )

    authenticated_request = urllib.request.Request(
        LOGIN_URL,
        data=b"",
        headers={"Authorization": authorization},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            authenticated_request,
            timeout=5,
        ) as response:
            return response.status, json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        return error.code, None


connection = get_db_connection()
user_id: int | None = None

try:
    # 1. Create a temporary test user.
    username = f"recovery_test_{secrets.token_hex(4)}"

    initial_ha1 = calculate_ha1(
        username,
        INITIAL_PASSWORD,
    )

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, initial_ha1),
    )

    created_user_id = cursor.lastrowid

    if created_user_id is None:
        raise RuntimeError("Failed to create test user.")

    user_id = created_user_id
    connection.commit()

    print("Temporary user created: True")

    # 2. Generate backup codes.
    backup_codes = generate_backup_codes(
        connection,
        created_user_id,
    )

    recovery_code = backup_codes[0]

    print("Backup codes generated: True")

    # 3. Create an old session.
    user = connection.execute(
        """
        SELECT credential_version
        FROM users
        WHERE id = ?
        """,
        (created_user_id,),
    ).fetchone()

    old_token = create_session(
        connection,
        created_user_id,
        user["credential_version"],
    )

    assert validate_session(connection, old_token) is not None

    print("Old session initially valid: True")

    # 4. Recover the account using a backup code.
    status, result = send_json_request(
        RECOVERY_URL,
        {
            "username": username,
            "backup_code": recovery_code,
            "new_password": NEW_PASSWORD,
        },
    )

    assert status == 200, result

    print("Password recovery status:", status)

    # 5. Verify that the old session is invalid.
    assert validate_session(connection, old_token) is None

    print("Old session invalidated: True")

    # 6. Verify that the backup code cannot be reused.
    status, _ = send_json_request(
        RECOVERY_URL,
        {
            "username": username,
            "backup_code": recovery_code,
            "new_password": "AnotherTestPassword789!",
        },
    )

    assert status == 401

    print("Backup code reuse rejected:", status)

    # 7. Old password must no longer work.
    old_login_status, _ = digest_login(
        username,
        INITIAL_PASSWORD,
    )

    assert old_login_status == 401

    print("Old password rejected:", old_login_status)

    # 8. New password must work.
    new_login_status, new_login_result = digest_login(
    username,
    NEW_PASSWORD,
)

    assert new_login_status == 200

    if new_login_result is None:
        raise RuntimeError("Login response is missing.")

    new_token = new_login_result["session_token"]

    print("New password accepted:", new_login_status)

    # 9. Verify the new session.
    new_session = validate_session(
        connection,
        new_token,
    )

    assert new_session is not None
    assert new_session["username"] == username

    print("New session valid: True")

    print("All account recovery tests passed")

finally:
    # Remove temporary user and related records.
    if user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )
        connection.commit()

    connection.close()