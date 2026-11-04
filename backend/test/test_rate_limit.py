import json
import urllib.error
import urllib.request


URL = "http://127.0.0.1:5000/api/auth/backup-login"

payload = json.dumps({
    "username": "rate_limit_test_user",
    "backup_code": "A" * 22,
}).encode("utf-8")

results = []

for attempt in range(1, 7):
    request = urllib.request.Request(
        URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = response.status

    except urllib.error.HTTPError as error:
        status = error.code

    results.append(status)

    print(f"Attempt {attempt}: HTTP {status}")


assert results[:5] == [401, 401, 401, 401, 401]
assert results[5] == 429

print("Rate limiting tests passed")