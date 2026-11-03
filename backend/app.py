import hmac
import re
import sqlite3
import unicodedata
from flask_limiter import Limiter
from flask_cors import CORS
from flask_limiter.util import get_remote_address
from group_service import (
    create_group,
    list_groups,
    add_user_to_group,
    remove_user_from_group,
    set_group_active,
    user_has_disabled_group,
    list_group_members
)
from admin_service import (
    deactivate_user,
    activate_user,
    change_user_role,
)
from backup_code_service import (
    generate_backup_codes,
    consume_backup_code_and_create_session,
    recover_password_with_backup_code,
)
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

CORS(
    app,
    resources={
        r"/api/.*": {
            "origins": [
                "http://localhost:7357",
            ],
            "methods": [
                "GET",
                "POST",
                "PATCH",
                "DELETE",
                "OPTIONS",
            ],
            "allow_headers": [
                "Content-Type",
                "Authorization",
            ],
            "expose_headers": [
                "WWW-Authenticate",
            ],
            "max_age": 600,
        }
    },
)

limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    storage_uri="memory://",
)

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
@limiter.limit("5 per minute")
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
@limiter.limit("10 per minute")
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

    if user_has_disabled_group(connection, user["id"]):
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

@app.post("/api/auth/backup-login")
@limiter.limit("5 per minute")
def backup_login():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    username = data.get("username")
    backup_code = data.get("backup_code")

    if (
        not isinstance(username, str)
        or not isinstance(backup_code, str)
        or not username.strip()
        or not backup_code.strip()
    ):
        return {"error": "Username and backup code are required."}, 400

    username = username.strip().lower()
    backup_code = backup_code.strip()

    connection = get_db()

    user = connection.execute(
        """
        SELECT id, username, role, is_active, credential_version
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()

    if (user is None or not user["is_active"] or user_has_disabled_group(connection, user["id"])):
        return {"error": "Invalid username or backup code."}, 401

    session_token = consume_backup_code_and_create_session(
        connection,
        user["id"],
        backup_code,
        )

    if session_token is None:
        return {"error": "Invalid username or backup code."}, 401

    response = make_response(
        {
            "status": "authenticated",
            "username": user["username"],
            "session_token": session_token,
            "token_type": "Bearer",
            "expires_in": AUTH_SESSION_TTL_SECONDS,
        },
        200,
    )

    response.headers["Cache-Control"] = "no-store"

    return response

@app.post("/api/auth/recover")
@limiter.limit("5 per minute")
def recover_account():
    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    username = data.get("username")
    backup_code = data.get("backup_code")
    new_password = data.get("new_password")

    if not isinstance(username, str):
        return {"error": "Username is required."}, 400

    if not isinstance(backup_code, str):
        return {"error": "Backup code is required."}, 400

    if not isinstance(new_password, str):
        return {"error": "New password is required."}, 400

    if not username.strip() or not backup_code.strip() or not new_password:
        return {
        "error": "Username, backup code and new password are required."
        }, 400

    username = username.strip().lower()
    backup_code = backup_code.strip()
    new_password = unicodedata.normalize("NFC", new_password)

    if not re.fullmatch(r"[a-z0-9_.-]{3,32}", username):
        return {"error": "Invalid username or backup code."}, 401

    if not 12 <= len(new_password) <= 128:
        return {
            "error": "New password length must be between 12 and 128 characters."
        }, 400

    connection = get_db()

    user = connection.execute(
        """
        SELECT id, username
        FROM users
        WHERE username = ?
        """,
        (username,),
    ).fetchone()

    if user is None:
        return {"error": "Invalid username or backup code."}, 401

    new_ha1 = calculate_ha1(
        user["username"],
        new_password,
    )

    recovered = recover_password_with_backup_code(
        connection=connection,
        user_id=user["id"],
        backup_code=backup_code,
        new_ha1=new_ha1,
    )

    if not recovered:
        return {"error": "Invalid username or backup code."}, 401

    response = make_response(
        {
            "status": "password_recovered",
            "message": "Password successfully reset. Please log in again.",
        },
        200,
    )

    response.headers["Cache-Control"] = "no-store"

    return response

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
@limiter.limit("5 per minute")
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

@app.post("/api/auth/backup-codes")
@limiter.limit("3 per hour")
def create_backup_codes():
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    session = validate_session(connection, token.strip())

    if session is None:
        return {"error": "invalid_or_expired_session"}, 401

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    current_password = data.get("current_password")

    if not isinstance(current_password, str) or not current_password:
        return {"error": "Current password is required."}, 400

    current_password = unicodedata.normalize(
        "NFC",
        current_password,
    )

    user = connection.execute(
        """
        SELECT id, username, ha1
        FROM users
        WHERE id = ?
        """,
        (session["user_id"],),
    ).fetchone()

    if user is None:
        return {"error": "User not found."}, 404

    calculated_ha1 = calculate_ha1(
        user["username"],
        current_password,
    )

    if not hmac.compare_digest(calculated_ha1, user["ha1"]):
        return {"error": "Current password is incorrect."}, 401

    codes = generate_backup_codes(
        connection,
        user["id"],
    )

    response = make_response(
        {
            "status": "created",
            "count": len(codes),
            "backup_codes": codes,
        },
        201,
    )

    response.headers["Cache-Control"] = "no-store"

    return response

@app.post("/api/admin/users/<int:user_id>/disable")
@limiter.limit("10 per minute")
def admin_disable_user(user_id):
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    if admin_session["user_id"] == user_id:
        return {"error": "You cannot disable your own account."}, 409

    result = deactivate_user(connection, user_id)

    if result == "not_found":
        return {"error": "User not found."}, 404

    if result == "already_disabled":
        return {"error": "User is already disabled."}, 409

    if result != "disabled":
        return {"error": "Invalid user ID."}, 400

    return {
        "status": "disabled",
        "user_id": user_id,
        "message": "User account and active sessions disabled.",
    }, 200

@app.post("/api/admin/users/<int:user_id>/enable")
@limiter.limit("10 per minute")
def admin_enable_user(user_id):
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    result = activate_user(connection, user_id)

    if result == "not_found":
        return {"error": "User not found."}, 404

    if result == "already_active":
        return {"error": "User is already active."}, 409

    if result != "enabled":
        return {"error": "Invalid user ID."}, 400

    return {
        "status": "enabled",
        "user_id": user_id,
        "message": "User account successfully enabled.",
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

@app.get("/api/admin/users")
@limiter.limit("30 per minute")
def admin_list_users():
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return {"error": "Invalid pagination parameters."}, 400

    if not 1 <= limit <= 100 or offset < 0:
        return {"error": "Invalid pagination parameters."}, 400

    rows = connection.execute(
        """
        SELECT
            id,
            username,
            role,
            is_active,
            created_at
        FROM users
        ORDER BY id
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()

    total = connection.execute(
        "SELECT COUNT(*) AS total FROM users"
    ).fetchone()["total"]

    users = [
        {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {
        "status": "ok",
        "total": total,
        "limit": limit,
        "offset": offset,
        "users": users,
    }, 200

@app.post("/api/admin/users/<int:user_id>/role")
@limiter.limit("10 per minute")
def admin_change_user_role(user_id):
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    if admin_session["user_id"] == user_id:
        return {"error": "You cannot change your own role."}, 409

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    new_role = data.get("role")

    if not isinstance(new_role, str):
        return {"error": "Role must be a string."}, 400

    result = change_user_role(
        connection,
        user_id,
        new_role,
    )

    if result == "not_found":
        return {"error": "User not found."}, 404

    if result == "invalid_role":
        return {"error": "Role must be user or admin."}, 400

    if result == "unchanged":
        return {"error": "User already has this role."}, 409

    if result == "last_admin":
        return {
            "error": "The last active administrator cannot be demoted."
        }, 409

    if result != "updated":
        return {"error": "Role update failed."}, 500

    return {
        "status": "updated",
        "user_id": user_id,
        "new_role": new_role,
        "message": "User role successfully updated.",
    }, 200

@app.post("/api/admin/groups")
@limiter.limit("10 per minute")
def admin_create_group():
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    name = data.get("name")
    description = data.get("description", "")

    if not isinstance(name, str):
        return {"error": "Group name must be a string."}, 400

    if not isinstance(description, str):
        return {"error": "Description must be a string."}, 400

    result, group_id = create_group(
        connection,
        name,
        description,
    )

    if result == "invalid_group_name":
        return {"error": "Invalid group name."}, 400

    if result == "invalid_description":
        return {"error": "Invalid group description."}, 400

    if result == "invalid_group_data":
        return {"error": "Group data exceeds the allowed length."}, 400

    if result == "already_exists":
        return {"error": "Group already exists."}, 409

    if result != "created":
        return {"error": "Group creation failed."}, 500

    return {
        "status": "created",
        "group_id": group_id,
        "name": name.strip(),
        "message": "Group successfully created.",
    }, 201

@app.get("/api/admin/groups")
@limiter.limit("30 per minute")
def admin_list_groups():
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return {"error": "Invalid pagination parameters."}, 400

    if not 1 <= limit <= 100 or offset < 0:
        return {"error": "Invalid pagination parameters."}, 400

    rows, total = list_groups(
        connection,
        limit,
        offset,
    )

    groups = [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "is_active": bool(row["is_active"]),
            "member_count": row["member_count"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]

    return {
        "status": "ok",
        "total": total,
        "limit": limit,
        "offset": offset,
        "groups": groups,
    }, 200

@app.patch("/api/admin/groups/<int:group_id>/status")
@limiter.limit("10 per minute")
def admin_set_group_status(group_id):
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    is_active = data.get("is_active")

    if not isinstance(is_active, bool):
        return {"error": "is_active must be a boolean."}, 400

    result = set_group_active(
        connection,
        group_id,
        is_active,
    )

    if result == "not_found":
        return {"error": "Group not found."}, 404

    if result == "last_admin":
        return {
            "error": "Cannot disable the group because it would block all active administrators."
        }, 409

    if result == "unchanged":
        return {"error": "Group already has this status."}, 409

    if result == "invalid_group_id":
        return {"error": "Invalid group ID."}, 400

    if result != ("enabled" if is_active else "disabled"):
        return {"error": "Group status update failed."}, 500

    return {
        "status": result,
        "group_id": group_id,
        "is_active": is_active,
    }, 200

@app.post("/api/admin/groups/<int:group_id>/members")
@limiter.limit("20 per minute")
def admin_add_group_member(group_id):
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return {"error": "Invalid JSON body."}, 400

    user_id = data.get("user_id")

    if (
        not isinstance(user_id, int)
        or isinstance(user_id, bool)
        or user_id <= 0
    ):
        return {"error": "Valid user_id is required."}, 400

    result = add_user_to_group(
        connection,
        group_id,
        user_id,
    )

    if result == "group_not_found":
        return {"error": "Group not found."}, 404

    if result == "user_not_found":
        return {"error": "User not found."}, 404

    if result == "group_disabled":
        return {"error": "Cannot add users to a disabled group."}, 409

    if result == "user_disabled":
        return {"error": "Cannot add a disabled user."}, 409

    if result == "already_member":
        return {"error": "User is already a group member."}, 409

    if result == "invalid_id":
        return {"error": "Invalid group or user ID."}, 400

    if result != "added":
        return {"error": "Failed to add group member."}, 500

    return {
        "status": "added",
        "group_id": group_id,
        "user_id": user_id,
        "message": "User successfully added to group.",
    }, 201


@app.get("/api/admin/groups/<int:group_id>/members")
@limiter.limit("30 per minute")
def admin_list_group_members(group_id):
    authorization = request.headers.get("Authorization", "")

    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    if group_id <= 0:
        return {"error": "Invalid group ID."}, 400

    group = connection.execute(
        """
        SELECT id
        FROM user_groups
        WHERE id = ?
        """,
        (group_id,),
    ).fetchone()

    if group is None:
        return {"error": "Group not found."}, 404

    try:
        limit = int(request.args.get("limit", "100"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        return {"error": "Invalid pagination parameters."}, 400

    if not 1 <= limit <= 100 or offset < 0:
        return {"error": "Invalid pagination parameters."}, 400

    rows, total = list_group_members(
        connection,
        group_id,
        limit,
        offset,
    )

    members = [
        {
            "id": row["id"],
            "username": row["username"],
            "role": row["role"],
            "is_active": bool(row["is_active"]),
        }
        for row in rows
    ]

    return {
        "status": "ok",
        "group_id": group_id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "members": members,
    }, 200

@app.delete("/api/admin/groups/<int:group_id>/members/<int:user_id>")
@limiter.limit("20 per minute")
def admin_remove_group_member(group_id, user_id):
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")

    if (
        not separator
        or scheme.lower() != "bearer"
        or not token.strip()
    ):
        return {"error": "authentication_required"}, 401

    connection = get_db()

    admin_session = validate_session(
        connection,
        token.strip(),
    )

    if admin_session is None:
        return {"error": "invalid_or_expired_session"}, 401

    if admin_session["role"] != "admin":
        return {"error": "administrator_access_required"}, 403

    result = remove_user_from_group(
        connection,
        group_id,
        user_id,
    )

    if result == "not_member":
        return {
            "error": "User is not a member of this group."
        }, 404

    if result != "removed":
        return {"error": "Failed to remove group member."}, 500

    return {
        "status": "removed",
        "group_id": group_id,
        "user_id": user_id,
        "message": "User successfully removed from group.",
    }, 200




if __name__ == "__main__":
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )