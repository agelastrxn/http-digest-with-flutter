import hashlib
import re
import unicodedata

from config import DIGEST_ALGORITHM, DIGEST_REALM, DIGEST_QOP


def calculate_ha1(
    username: str,
    password: str,
    realm: str = DIGEST_REALM
) -> str:
    if not isinstance(username, str) or not username:
        raise ValueError("Username must be a non-empty string.")

    if not isinstance(password, str) or not password:
        raise ValueError("Password must be a non-empty string.")

    if not isinstance(realm, str) or not realm:
        raise ValueError("Realm must be a non-empty string.")

    if DIGEST_ALGORITHM != "SHA-256":
        raise ValueError("Unsupported Digest algorithm.")

    normalized_username = unicodedata.normalize("NFC", username)
    normalized_password = unicodedata.normalize("NFC", password)
    ha1_input = f"{normalized_username}:{realm}:{normalized_password}"          
    ha1_bytes = ha1_input.encode("utf-8")

    return hashlib.sha256(ha1_bytes).hexdigest()

def calculate_ha2(method: str, request_uri: str) -> str:
    if not isinstance(method, str) or not method:
        raise ValueError("HTTP method must be a non-empty string.")

    if not isinstance(request_uri, str) or not request_uri:
        raise ValueError("Request URI must be a non-empty string.")

    if DIGEST_ALGORITHM != "SHA-256":
        raise ValueError("Unsupported Digest algorithm.")

    ha2_input = f"{method}:{request_uri}"
    ha2_bytes = ha2_input.encode("utf-8")

    return hashlib.sha256(ha2_bytes).hexdigest()

def calculate_digest_response(
    ha1: str,
    nonce: str,
    nonce_count: str,
    client_nonce: str,
    qop: str,
    ha2: str,
) -> str:
    if DIGEST_ALGORITHM != "SHA-256":
        raise ValueError("Unsupported Digest algorithm.")

    if qop != DIGEST_QOP:
        raise ValueError("Unsupported quality of protection.")

    if not re.fullmatch(r"[0-9a-f]{64}", ha1):
        raise ValueError("Invalid HA1 value.")

    if not re.fullmatch(r"[0-9a-f]{64}", ha2):
        raise ValueError("Invalid HA2 value.")

    if not nonce or not client_nonce:
        raise ValueError("Nonce values must not be empty.")

    if not re.fullmatch(r"[0-9a-fA-F]{8}", nonce_count):
        raise ValueError("Nonce count must contain 8 hexadecimal digits.")

    response_input = (f"{ha1}:{nonce}:{nonce_count}:{client_nonce}:{qop}:{ha2}")

    response_bytes = response_input.encode("utf-8")

    return hashlib.sha256(response_bytes).hexdigest()
