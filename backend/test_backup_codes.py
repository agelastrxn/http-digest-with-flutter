import secrets

from config import BACKUP_CODE_COUNT
from database import get_db_connection
from backup_code_service import (
    generate_backup_codes,
    consume_backup_code,
    hash_backup_code,
)


connection = get_db_connection()
user_id: int | None = None

try:
    # Create a temporary test user.
    username = f"backup_test_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, "0" * 64),
    )

    created_user_id = cursor.lastrowid

    if created_user_id is None:
        raise RuntimeError("Failed to obtain test user ID.")

    user_id = created_user_id
    connection.commit()

    # Generate backup codes.
    codes = generate_backup_codes(
        connection,
        created_user_id,
    )

    assert len(codes) == BACKUP_CODE_COUNT

    print("Backup codes generated:", len(codes))

    # Verify that only hashes are stored.
    rows = connection.execute(
        """
        SELECT code_hash
        FROM backup_codes
        WHERE user_id = ?
        """,
        (created_user_id,),
    ).fetchall()

    stored_hashes = {
        row["code_hash"]
        for row in rows
    }

    expected_hashes = {
        hash_backup_code(code)
        for code in codes
    }

    assert stored_hashes == expected_hashes
    assert not stored_hashes.intersection(codes)

    print("Only code hashes stored: True")

    # Verify one-time usage.
    first_code = codes[0]

    first_attempt = consume_backup_code(
        connection,
        created_user_id,
        first_code,
    )

    second_attempt = consume_backup_code(
        connection,
        created_user_id,
        first_code,
    )

    assert first_attempt is True
    assert second_attempt is False

    print("Code can be consumed once: True")

    # Generate new codes and verify old unused codes are revoked.
    old_unused_code = codes[1]

    new_codes = generate_backup_codes(
        connection,
        created_user_id,
    )

    old_code_hash = hash_backup_code(old_unused_code)

    old_code = connection.execute(
        """
        SELECT revoked_at
        FROM backup_codes
        WHERE code_hash = ?
        """,
        (old_code_hash,),
    ).fetchone()

    assert old_code is not None
    assert old_code["revoked_at"] is not None

    assert not consume_backup_code(
        connection,
        created_user_id,
        old_unused_code,
    )

    print("Unused old codes revoked: True")

    # Verify newly generated codes.
    assert len(new_codes) == BACKUP_CODE_COUNT

    new_attempt = consume_backup_code(
        connection,
        created_user_id,
        new_codes[0],
    )

    repeated_attempt = consume_backup_code(
        connection,
        created_user_id,
        new_codes[0],
    )

    assert new_attempt is True
    assert repeated_attempt is False

    print("New codes work correctly: True")

    print("All backup code tests passed")

finally:
    # Remove the temporary test user and related records.
    if user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )
        connection.commit()

    connection.close()