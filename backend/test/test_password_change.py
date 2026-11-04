import getpass
import json
import secrets
import urllib.error
import urllib.request

from digest_auth import parse_digest_authorization
from digest_utils import calculate_ha1, calculate_ha2, calculate_digest_response


BASE_URL = "http://127.0.0.1:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/digest"


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

    with urllib.request.urlopen(
        authenticated_request,
        timeout=5,
    ) as result:
        return json.loads(result.read().decode("utf-8"))


def send_authenticated_request(
    path,
    token,
    method="GET",
    payload=None,
):
    headers = {
        "Authorization": f"Bearer {token}"
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
        with urllib.request.urlopen(request, timeout=5) as result:
            return result.status, json.loads(
                result.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        return error.code, json.loads(
            error.read().decode("utf-8")
        )


username = input("Username: ").strip().lower()
current_password = getpass.getpass("Current password: ")
new_password = getpass.getpass("New password: ")
confirmation = getpass.getpass("Confirm new password: ")

if new_password != confirmation:
    raise SystemExit("New passwords do not match.")

if not 12 <= len(new_password) <= 128:
    raise SystemExit("New password must be 12-128 characters.")

# Step 1: Authenticate with the current password.
login_result = digest_login(username, current_password)
old_token = login_result["session_token"]

print("Initial login: successful")

# Step 2: Confirm that the current session works.
status, _ = send_authenticated_request(
    "/api/auth/me",
    old_token,
)

assert status == 200
print("Old session before password change: valid")

# Step 3: Change the password.
status, result = send_authenticated_request(
    "/api/auth/change-password",
    old_token,
    method="POST",
    payload={
        "current_password": current_password,
        "new_password": new_password,
    },
)

assert status == 200, result
print("Password change: successful")

# Step 4: Check that the old session is invalid.
status, _ = send_authenticated_request(
    "/api/auth/me",
    old_token,
)

assert status == 401
print("Old session after password change: rejected")

# Step 5: Authenticate using the new password.
new_login = digest_login(username, new_password)
new_token = new_login["session_token"]

print("Login with new password: successful")

# Step 6: Check the new session.
status, profile = send_authenticated_request(
    "/api/auth/me",
    new_token,
)

assert status == 200
assert profile["username"] == username

print("New session: valid")
print("Password change tests passed")