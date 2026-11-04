import getpass
import secrets
import urllib.error
import urllib.request
import json

from digest_auth import parse_digest_authorization
from digest_utils import calculate_ha1, calculate_ha2, calculate_digest_response


URL = "http://127.0.0.1:5000/api/auth/digest"
METHOD = "POST"
REQUEST_URI = "/api/auth/digest"


username = input("Username: ").strip().lower()
password = getpass.getpass("Password: ")

initial_request = urllib.request.Request(
    URL,
    method=METHOD,
)

try:
    urllib.request.urlopen(initial_request, timeout=5)
    raise SystemExit("Expected a Digest challenge, but received success.")

except urllib.error.HTTPError as error:
    if error.code != 401:
        raise SystemExit(f"Unexpected HTTP status: {error.code}")

    challenge_header = error.headers.get("WWW-Authenticate")

if not challenge_header:
    raise SystemExit("Digest challenge header is missing.")

challenge = parse_digest_authorization(challenge_header)

ha1 = calculate_ha1(
    username,
    password,
    challenge["realm"],
)

ha2 = calculate_ha2(
    METHOD,
    REQUEST_URI,
)

nonce_count = "00000001"
client_nonce = secrets.token_hex(16)

response_hash = calculate_digest_response(
    ha1=ha1,
    nonce=challenge["nonce"],
    nonce_count=nonce_count,
    client_nonce=client_nonce,
    qop=challenge["qop"],
    ha2=ha2,
)

authorization_header = (
    f'Digest username="{username}", '
    f'realm="{challenge["realm"]}", '
    f'nonce="{challenge["nonce"]}", '
    f'uri="{REQUEST_URI}", '
    f'algorithm={challenge["algorithm"]}, '
    f'qop={challenge["qop"]}, '
    f'nc={nonce_count}, '
    f'cnonce="{client_nonce}", '
    f'response="{response_hash}"'
)

authenticated_request = urllib.request.Request(
    URL,
    data=b"",
    headers={"Authorization": authorization_header},
    method=METHOD,
)

try:
    with urllib.request.urlopen(
        authenticated_request,
        timeout=5,
    ) as result:
        payload = json.loads(result.read().decode("utf-8"))

    session_token = payload.get("session_token")

    print("Login status:", result.status)
    print("Session token received:", bool(session_token))

    if not session_token:
        raise SystemExit("Session token was not returned.")

    headers = {
        "Authorization": f"Bearer {session_token}"
    }

    protected_request = urllib.request.Request(
        "http://127.0.0.1:5000/api/auth/me",
        headers=headers,
        method="GET",
    )

    with urllib.request.urlopen(protected_request, timeout=5) as result:
        print("Protected endpoint before logout:", result.status)

    logout_request = urllib.request.Request(
        "http://127.0.0.1:5000/api/auth/logout",
        headers=headers,
        method="POST",
        data=b"",
    )

    with urllib.request.urlopen(logout_request, timeout=5) as result:
        print("Logout status:", result.status)
        print(result.read().decode("utf-8"))

    revoked_request = urllib.request.Request(
        "http://127.0.0.1:5000/api/auth/me",
        headers=headers,
        method="GET",
    )

    try:
        with urllib.request.urlopen(revoked_request, timeout=5) as result:
            raise AssertionError("Revoked session was accepted.")

    except urllib.error.HTTPError as error:
        print("Protected endpoint after logout:", error.code)
        assert error.code == 401

    print("Logout and session revocation tests passed")

except urllib.error.HTTPError as error:
    print("HTTP status:", error.code)
    print(error.read().decode("utf-8"))