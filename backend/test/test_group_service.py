import secrets

from database import get_db_connection
from group_service import (
    create_group,
    add_user_to_group,
    remove_user_from_group,
    set_group_active,
)
from session_service import create_session, validate_session


connection = get_db_connection()

user_id: int | None = None
group_id: int | None = None

try:
    # 1. Create a temporary test user.
    username = f"group_test_{secrets.token_hex(4)}"

    cursor = connection.execute(
        """
        INSERT INTO users (username, ha1)
        VALUES (?, ?)
        """,
        (username, "0" * 64),
    )

    created_user_id = cursor.lastrowid

    if created_user_id is None:
        raise RuntimeError("Failed to create test user.")

    user_id = created_user_id
    connection.commit()

    print("Temporary user created: True")

    # 2. Create a group.
    group_name = f"Test_Group_{secrets.token_hex(4)}"

    status, created_group_id = create_group(
        connection,
        group_name,
        "Temporary group for testing.",
    )

    assert status == "created"
    assert created_group_id is not None

    group_id = created_group_id

    print("Group created: True")

    # 3. Test duplicate group creation.
    duplicate_status, _ = create_group(
        connection,
        group_name,
        "Duplicate group.",
    )

    assert duplicate_status == "already_exists"

    print("Duplicate group creation blocked: True")

    # 4. Create a session before adding the user to the group.
    old_token = create_session(
        connection,
        created_user_id,
        1,
    )

    assert validate_session(connection, old_token) is not None

    # 5. Add the user to the group.
    result = add_user_to_group(
        connection,
        created_group_id,
        created_user_id,
    )

    assert result == "added"

    print("User added to group: True")

    # Adding the user must invalidate the previous session.
    assert validate_session(connection, old_token) is None

    print("Previous session invalidated: True")

    # 6. Test duplicate membership.
    duplicate_membership = add_user_to_group(
        connection,
        created_group_id,
        created_user_id,
    )

    assert duplicate_membership == "already_member"

    print("Duplicate membership blocked: True")

    # 7. Remove the user from the group.
    updated_user = connection.execute(
        """
        SELECT credential_version
        FROM users
        WHERE id = ?
        """,
        (created_user_id,),
    ).fetchone()

    current_version = updated_user["credential_version"]

    removal_token = create_session(
        connection,
        created_user_id,
        current_version,
    )

    result = remove_user_from_group(
        connection,
        created_group_id,
        created_user_id,
    )

    assert result == "removed"

    print("User removed from group: True")

    assert validate_session(connection, removal_token) is None

    print("Session invalidated after removal: True")

    # 8. Add the user again.
    result = add_user_to_group(
        connection,
        created_group_id,
        created_user_id,
    )

    assert result == "added"

    print("User added again: True")

    updated_user = connection.execute(
        """
        SELECT credential_version
        FROM users
        WHERE id = ?
        """,
        (created_user_id,),
    ).fetchone()

    current_version = updated_user["credential_version"]

    group_session = create_session(
        connection,
        created_user_id,
        current_version,
    )

    assert validate_session(connection, group_session) is not None

    # 9. Disable the group.
    result = set_group_active(
        connection,
        created_group_id,
        False,
    )

    assert result == "disabled"

    print("Group disabled: True")

    # Group deactivation must invalidate existing sessions.
    assert validate_session(connection, group_session) is None

    print("Group member session invalidated: True")

    # 10. Adding users to disabled groups must be rejected.
    add_result = add_user_to_group(
        connection,
        created_group_id,
        created_user_id,
    )

    assert add_result == "group_disabled"

    print("Disabled group membership blocked: True")

    # 11. Enable the group again.
    result = set_group_active(
        connection,
        created_group_id,
        True,
    )

    assert result == "enabled"

    print("Group reactivated: True")

    # Previous sessions must remain invalid.
    assert validate_session(connection, group_session) is None

    print("Old session remains invalid: True")

    # 12. Check that the group cannot be enabled twice.
    unchanged_result = set_group_active(
        connection,
        created_group_id,
        True,
    )

    assert unchanged_result == "unchanged"

    print("Repeated activation handled: True")

    print("All group service tests passed")

finally:
    # Remove temporary test data.
    if user_id is not None:
        connection.execute(
            "DELETE FROM users WHERE id = ?",
            (user_id,),
        )

    if group_id is not None:
        connection.execute(
            "DELETE FROM user_groups WHERE id = ?",
            (group_id,),
        )

    connection.commit()
    connection.close()