import uuid

import psycopg
import pytest

# These two invariants are enforced only at the DB layer and aren't reachable
# through the API: Pydantic's phone regex in schemas.py rejects bad phone
# formats before a request ever reaches Postgres, and FastAPI/Pydantic reject
# an invalid `role`/`account_status` literal before the DB's enum type would.
# So they're tested by talking to Postgres directly (item 3, item 5), proving
# the DDL backstops described in CLAUDE.md ("Validation duplicated by design")
# actually exist and fire, independent of the app layer.


def test_phone_e164_check_constraint_rejects_bad_format(db_conn) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        db_conn.execute(
            "INSERT INTO users (email, display_name, phone) VALUES (%s, %s, %s)",
            (f"checkviol-{uuid.uuid4()}@example.com", "Bad Phone", "not-a-phone"),
        )


def test_account_status_enum_rejects_invalid_value(db_conn) -> None:
    with pytest.raises(psycopg.errors.InvalidTextRepresentation):
        db_conn.execute(
            "INSERT INTO users (email, display_name, account_status) VALUES (%s, %s, %s)",
            (f"enumviol-{uuid.uuid4()}@example.com", "Bad Status", "not_a_status"),
        )
