import getpass
import json
import urllib.error
import urllib.request


BASE_URL = "http://127.0.0.1:5000"


def send_request(path, payload):
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=data,
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


username = input("Username: ").strip()
backup_code = getpass.getpass("Backup code: ")

# Step 1: Authenticate using a backup code.
status, result = send_request(
    "/api/auth/backup-login",
    {
        "username": username,
        "backup_code": backup_code,
    },
)

assert status == 200, result

session_token = result.get("session_token")

assert session_token is not None

print("Backup login: successful")
print("Session token received:", bool(session_token))

# Step 2: Verify the newly created session.
profile_request = urllib.request.Request(
    f"{BASE_URL}/api/auth/me",
    headers={
        "Authorization": f"Bearer {session_token}",
    },
    method="GET",
)

with urllib.request.urlopen(profile_request, timeout=5) as response:
    profile = json.loads(response.read().decode("utf-8"))

assert response.status == 200
assert profile["username"] == username.lower()

print("Protected endpoint:", response.status)
print("Authenticated user:", profile["username"])

# Step 3: Attempt to reuse the same backup code.
repeat_status, _ = send_request(
    "/api/auth/backup-login",
    {
        "username": username,
        "backup_code": backup_code,
    },
)

assert repeat_status == 401

print("Reusing backup code:", repeat_status)
print("Backup login tests passed")