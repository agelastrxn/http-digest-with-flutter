import hmac
import re
import sqlite3
import unicodedata
from session_service import (
    create_session,
    validate_session,
    revoke_session,
)

from flask import request
from digest_utils import calculate_ha1
from flask import Flask, g, make_response
from config import (
    AUTH_SESSION_TTL_SECONDS,
    DIGEST_ALGORITHM,
    DIGEST_QOP,
    DIGEST_REALM,
)
from database import get_db_connection
from nonce_service import (
    create_nonce,
    validate_nonce,
    consume_nonce_count,
)
from digest_auth import (
    parse_digest_authorization,
    validate_digest_parameters,
    verify_digest_response,
)


app = Flask(__name__)

@app.teardown_appcontext
def close_db_connection(exception=None):
    connection = g.pop("db_connection", None)

    if connection is not None:
        connection.close()

@app.get("/health")
def health():
    return {
        "status": "ok",
        "message": "Backend is running"
    }

@app.post("/api/auth/register")
def register():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not isinstance(password, str):
        return {"error": "Username and password are required."}, 400

    username = username.strip().lower()
    password = unicodedata.normalize("NFC", password)

    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        return {"error": "Invalid username format."}, 400

    if not 12 <= len(password) <= 128:
        return {"error": "Password length must be between 12 and 128 characters."}, 400

    ha1 = calculate_ha1(username, password)

    connection = get_db()

    try:
        connection.execute(
            "INSERT INTO users (username, ha1) VALUES (?, ?)",
            (username, ha1),
        )
        connection.commit()

    except sqlite3.IntegrityError:
        connection.rollback()
        return {"error": "Username already exists."}, 409

    return {
        "status": "created",
        "username": username,
    }, 201

def get_db():
    if "db_connection" not in g:
        g.db_connection = get_db_connection()

    return g.db_connection

def create_digest_challenge_response(
    connection,
    stale=False,
):
    nonce = create_nonce(connection)

    response = make_response(
        {"error": "authentication_required"},
        401,
    )

    challenge = (
        f'Digest realm="{DIGEST_REALM}", '
        f'nonce="{nonce}", '
        f'algorithm={DIGEST_ALGORITHM}, '
        f'qop="{DIGEST_QOP}", '
        "charset=UTF-8"
    )

    if stale:
        challenge += ", stale=true"

    response.headers["WWW-Authenticate"] = challenge

    return response

@app.get("/db-check")
def db_check():
    connection = get_db()

    result = connection.execute("SELECT 1").fetchone()

    return {
        "status": "ok",
        "database": "connected",
        "test_value": result[0]
    }

@app.get("/digest-challenge")
def digest_challenge():
    return create_digest_challenge_response(get_db())

@app.post("/api/auth/digest")
def digest_login():
    connection = get_db()
    authorization = request.headers.get("Authorization")

    if not authorization:
        return create_digest_challenge_response(connection)

    try:
        parameters = parse_digest_authorization(authorization)
        validate_digest_parameters(parameters)
    except ValueError:
        return create_digest_challenge_response(connection)

    username = parameters["username"]

    user = connection.execute(
        """
        SELECT id, username, ha1, is_active, credential_version
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()

    if user is None or not user["is_active"]:
        return create_digest_challenge_response(connection)

    nonce_status = validate_nonce(connection, parameters["nonce"])

    if nonce_status != "valid":
        return create_digest_challenge_response(
            connection,
            stale=(nonce_status == "expired"),
        )

    request_uri = request.path

    if request.query_string:
        request_uri += "?" + request.query_string.decode("latin-1")

    try:
        response_is_valid = verify_digest_response(
            parameters=parameters,
            stored_ha1=user["ha1"],
            request_method=request.method,
            request_uri=request_uri,
        )
    except ValueError:
        return create_digest_challenge_response(connection)

    if not response_is_valid:
        return create_digest_challenge_response(connection)

    count_is_valid = consume_nonce_count(
        connection=connection,
        username=username,
        nonce=parameters["nonce"],
        nonce_count=parameters["nc"],
        cnonce=parameters["cnonce"],
    )

    if not count_is_valid:
        return create_digest_challenge_response(connection)

    session_token = create_session(
        connection=connection,
        user_id=user["id"],
        credential_version=user["credential_version"],
    )

    return {
        "status": "authenticated",
        "username": user["username"],
        "session_token": session_token,
        "token_type": "Bearer",
        "expires_in": AUTH_SESSION_TTL_SECONDS,
    }, 200


@app.get("/api/auth/me")
def auth_me():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    session = validate_session(
        get_db(),
        token.strip(),
    )

    if session is None:
        return {"error": "invalid_or_expired_session"}, 401

    return {
        "status": "ok",
        "username": session["username"],
        "role": session["role"],
    }, 200

@app.post("/api/auth/change-password")
def change_password():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    session = validate_session(
        connection,
        token.strip(),
    )

    if session is None:
        return {"error": "invalid_or_expired_session"}, 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not isinstance(current_password, str):
        return {"error": "Current password is required."}, 400

    if not isinstance(new_password, str):
        return {"error": "New password is required."}, 400

    current_password = unicodedata.normalize(
        "NFC",
        current_password,
    )

    new_password = unicodedata.normalize(
        "NFC",
        new_password,
    )

    if not 12 <= len(new_password) <= 128:
        return {
            "error": "New password length must be between 12 and 128 characters."
        }, 400

    user = connection.execute(
        """
        SELECT id, username, ha1, credential_version
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],),
    ).fetchone()

    if user is None:
        return {"error": "User not found."}, 404

    current_ha1 = calculate_ha1(
        user["username"],
        current_password,
    )

    if not hmac.compare_digest(current_ha1, user["ha1"]):
        return {"error": "Current password is incorrect."}, 401

    new_ha1 = calculate_ha1(
        user["username"],
        new_password,
    )

    if hmac.compare_digest(new_ha1, user["ha1"]):
        return {
            "error": "New password must be different from current password."
        }, 400

    try:
        cursor = connection.execute(
            """
            UPDATE users
            SET ha1 = ?,
                credential_version = credential_version + 1
            WHERE id = ?
              AND credential_version = ?
            """,
            (
                new_ha1,
                user["id"],
                user["credential_version"],
            ),
        )

        if cursor.rowcount != 1:
            connection.rollback()
            return {"error": "Password update conflict."}, 409

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    return {
        "status": "password_updated",
        "message": "Please log in again with your new password.",
    }, 200

@app.post("/api/auth/logout")
def auth_logout():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    token = token.strip()
    connection = get_db()

    session = validate_session(connection, token)

    if session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if not revoke_session(connection, token):
        return {"error": "session_revocation_failed"}, 500

    return {
        "status": "logged_out",
        "message": "Session successfully revoked.",
    }, 200


if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )