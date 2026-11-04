import getpass
import json
import secrets
import urllib.error
import urllib.request

from digest_auth import parse_digest_authorization
from digest_utils import (
    calculate_ha1,
    calculate_ha2,
    calculate_digest_response,
)


BASE_URL = "http://127.0.0.1:5000"
LOGIN_URL = f"{BASE_URL}/api/auth/digest"
BACKUP_URL = f"{BASE_URL}/api/auth/backup-codes"


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

    with urllib.request.urlopen(
        authenticated_request,
        timeout=5,
    ) as result:
        return json.loads(result.read().decode("utf-8"))


username = input("Username: ").strip().lower()
password = getpass.getpass("Password: ")

# Step 1: Authenticate using HTTP Digest.
login_result = digest_login(username, password)

session_token = login_result.get("session_token")

if not session_token:
    raise SystemExit("Login failed: session token is missing.")

print("Digest login: successful")

# Step 2: Prepare the backup code request.
payload = {
    "current_password": password
}

backup_request = urllib.request.Request(
    BACKUP_URL,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": f"Bearer {session_token}",
        "Content-Type": "application/json",
    },
    method="POST",
)

# Step 3: Request backup codes.
try:
    with urllib.request.urlopen(
        backup_request,
        timeout=5,
    ) as result:
        backup_result = json.loads(
            result.read().decode("utf-8")
        )

        print("HTTP status:", result.status)

except urllib.error.HTTPError as error:
    print("HTTP status:", error.code)
    print(error.read().decode("utf-8"))
    raise SystemExit("Backup code generation failed.")

# Step 4: Validate the response.
codes = backup_result.get("backup_codes", [])

assert result.status == 201
assert backup_result.get("status") == "created"
assert len(codes) == 10

print("Backup codes generated:", len(codes))
print("Backup code generation test passed")

# Step 5: Display codes once for secure storage.
print("\nYour backup codes:")

for index, code in enumerate(codes, start=1):
    print(f"{index}. {code}")