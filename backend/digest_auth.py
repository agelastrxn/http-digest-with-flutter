import re
import hmac
from config import DIGEST_ALGORITHM, DIGEST_QOP, DIGEST_REALM
from digest_utils import calculate_ha2, calculate_digest_response

TOKEN_PATTERN = re.compile(
    r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+"
)


def parse_digest_authorization(header: str) -> dict[str, str]:
    if not isinstance(header, str):
        raise ValueError("Authorization header must be a string.")

    parts = header.strip().split(None, 1)

    if len(parts) != 2 or parts[0].lower() != "digest":
        raise ValueError("Missing or invalid Digest scheme.")

    parameters_text = parts[1]
    parameters = {}
    index = 0
    length = len(parameters_text)

    while index < length:
        while (
            index < length
            and parameters_text[index] in " \t"
        ):
            index += 1

        key_match = TOKEN_PATTERN.match(parameters_text, index)

        if key_match is None:
            raise ValueError("Invalid Digest parameter name.")

        key = key_match.group(0).lower()
        index = key_match.end()

        while (
            index < length
            and parameters_text[index] in " \t"
        ):
            index += 1

        if index >= length or parameters_text[index] != "=":
            raise ValueError("Missing '=' after Digest parameter name.")

        index += 1

        while (
            index < length
            and parameters_text[index] in " \t"
        ):
            index += 1

        if index >= length:
            raise ValueError("Missing Digest parameter value.")

        if parameters_text[index] == '"':
            index += 1
            value_characters = []
            closed = False

            while index < length:
                character = parameters_text[index]

                if character == "\\":
                    index += 1

                    if index >= length:
                        raise ValueError("Invalid escape sequence.")

                    character = parameters_text[index]

                    if ord(character) < 32 or ord(character) == 127:
                        raise ValueError("Control character is not allowed.")

                    value_characters.append(character)
                    index += 1

                elif character == '"':
                    index += 1
                    closed = True
                    break

                else:
                    if ord(character) < 32 and character != "\t":
                        raise ValueError("Control character is not allowed.")

                    if ord(character) == 127:
                        raise ValueError("Control character is not allowed.")

                    value_characters.append(character)
                    index += 1

            if not closed:
                raise ValueError("Unclosed quoted parameter value.")

            value = "".join(value_characters)

        else:
            value_match = TOKEN_PATTERN.match(
                parameters_text,
                index
            )

            if value_match is None:
                raise ValueError("Invalid unquoted parameter value.")

            value = value_match.group(0)
            index = value_match.end()

        if key in parameters:
            raise ValueError(f"Duplicate Digest parameter: {key}")

        parameters[key] = value

        while (
            index < length
            and parameters_text[index] in " \t"
        ):
            index += 1

        if index < length:
            if parameters_text[index] != ",":
                raise ValueError("Expected a comma between parameters.")

            index += 1

            if index >= length:
                raise ValueError("Unexpected comma at the end of header.")

    return parameters



REQUIRED_DIGEST_FIELDS = {
    "username",
    "realm",
    "nonce",
    "uri",
    "response",
    "algorithm",
    "qop",
    "nc",
    "cnonce",
}


def validate_digest_parameters(
    parameters: dict[str, str],
) -> None:
    missing_fields = REQUIRED_DIGEST_FIELDS - parameters.keys()

    if missing_fields:
        raise ValueError(
            f"Missing required parameters: {', '.join(sorted(missing_fields))}"
        )

    for field in (
        "username",
        "realm",
        "nonce",
        "uri",
        "response",
        "cnonce",
    ):
        if not parameters[field]:
            raise ValueError(f"Parameter '{field}' must not be empty.")

    if parameters["realm"] != DIGEST_REALM:
        raise ValueError("Unexpected Digest realm.")

    if parameters["algorithm"].upper() != DIGEST_ALGORITHM.upper():
        raise ValueError("Unsupported Digest algorithm.")

    if parameters["qop"] != DIGEST_QOP:
        raise ValueError("Unsupported quality of protection.")

    if not re.fullmatch(r"[0-9a-fA-F]{8}", parameters["nc"]):
        raise ValueError("Invalid nonce count format.")

    if int(parameters["nc"], 16) == 0:
        raise ValueError("Nonce count must be greater than zero.")

    if not re.fullmatch(r"[0-9a-fA-F]{64}", parameters["response"]):
        raise ValueError("Invalid SHA-256 response format.")

    try:
        parameters["cnonce"].encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Client nonce must contain ASCII characters.") from None



def verify_digest_response(
    parameters: dict[str, str],
    stored_ha1: str,
    request_method: str,
    request_uri: str,
) -> bool:
    validate_digest_parameters(parameters)

    if parameters["uri"] != request_uri:
        raise ValueError("Digest URI does not match request target.")

    ha2 = calculate_ha2(request_method, request_uri)

    expected_response = calculate_digest_response(
        ha1=stored_ha1,
        nonce=parameters["nonce"],
        nonce_count=parameters["nc"],
        client_nonce=parameters["cnonce"],
        qop=parameters["qop"],
        ha2=ha2,
    )

    return hmac.compare_digest(
        parameters["response"].lower(),
        expected_response,
    )