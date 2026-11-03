import json
import secrets
import urllib.error
import urllib.request

from database import get_db_connection
from admin_service import deactivate_user
from session_service import (
    create_session,
    validate_session,
    revoke_session,
)
from digest_auth import parse_digest_authorization
from digest_utils import (
    calculate_ha1,
    calculate_ha2,
    calculate_digest_response,
)


BASE_URL = "http://127.0.0.1:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/digest"

TEST_PASSWORD = "TemporaryTestPassword123!"


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

    uri = "/api/auth/digest"
    method = "POST"
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

    with urllib.request.urlopen(
        authenticated_request,
        timeout=5,
    ) as response:
        return json.loads(response.read().decode("utf-8"))


connection = get_db_connection()

admin_token = None
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

    # Create a temporary user.
    username = f"enable_test_{secrets.token_hex(4)}"

    ha1 = calculate_ha1(username, TEST_PASSWORD)

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, ha1),
    )

    temporary_user_id = cursor.lastrowid

    if temporary_user_id is None:
        raise RuntimeError("Failed to create test user.")

    connection.commit()

    print("Temporary user created: True")

    # Create an old session.
    old_token = create_session(
        connection,
        temporary_user_id,
        1,
    )

    assert validate_session(connection, old_token) is not None

    print("Initial session valid: True")

    # Disable the user.
    result = deactivate_user(
        connection,
        temporary_user_id,
    )

    assert result == "disabled"
    assert validate_session(connection, old_token) is None

    print("User disabled: True")
    print("Old session invalidated: True")

    # Administrator enables the user through the API.
    enable_request = urllib.request.Request(
        f"{BASE_URL}/api/admin/users/{temporary_user_id}/enable",
        data=b"",
        headers={
            "Authorization": f"Bearer {admin_token}",
        },
        method="POST",
    )

    with urllib.request.urlopen(
        enable_request,
        timeout=5,
    ) as response:
        enable_result = json.loads(
            response.read().decode("utf-8")
        )

        assert response.status == 200

    print("Admin enable status:", response.status)

    # Verify database state.
    user = connection.execute(
        """
        SELECT is_active, credential_version
        FROM users
        WHERE id = ?
        """,
        (temporary_user_id,),
    ).fetchone()

    assert user["is_active"] == 1
    assert user["credential_version"] == 3

    print("User account reactivated: True")

    # The old session must remain invalid.
    assert validate_session(connection, old_token) is None

    print("Old session remains invalid: True")

    # Authenticate again using the previous password.
    login_result = digest_login(username, TEST_PASSWORD)

    new_token = login_result["session_token"]

    print("Digest login after reactivation: successful")

    # Verify the new session.
    new_session = validate_session(
        connection,
        new_token,
    )

    assert new_session is not None
    assert new_session["username"] == username

    print("New session valid: True")

    print("All admin enable tests passed")

finally:
    if admin_token is not None:
        revoke_session(connection, admin_token)

    if temporary_user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (temporary_user_id,),
        )
        connection.commit()

    connection.close()