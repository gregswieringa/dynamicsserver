import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

# Matches the users.phone_e164 CHECK constraint in db/init/001_buyer_schema.sql —
# validated here too so bad input fails fast with a clear 422 instead of a raw DB error.
_E164 = re.compile(r"^\+?[1-9]\d{6,14}$")


def _validate_phone(value: str | None) -> str | None:
    if value is not None and not _E164.match(value):
        raise ValueError("phone must be E.164 format, e.g. +14155552671 (digits only, no dashes/spaces)")
    return value


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    locale: str = "en-US"
    currency: str = "USD"
    marketing_opt_in: bool = False
    role: Literal["buyer", "seller", "both"] = "buyer"

    _validate_phone = field_validator("phone")(_validate_phone)


class UserUpdate(BaseModel):
    display_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    marketing_opt_in: bool | None = None
    account_status: Literal["pending_verification", "active", "suspended", "deactivated"] | None = None

    _validate_phone = field_validator("phone")(_validate_phone)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    email_verified: bool
    phone: str | None
    phone_verified: bool
    display_name: str
    first_name: str | None
    last_name: str | None
    date_of_birth: date | None
    locale: str
    currency: str
    marketing_opt_in: bool
    account_status: str
    role: str
    default_shipping_address_id: uuid.UUID | None
    default_payment_method_id: uuid.UUID | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AddressCreate(BaseModel):
    kind: Literal["shipping", "billing", "both"] = "shipping"
    recipient_name: str
    line1: str
    line2: str | None = None
    city: str
    region: str | None = None
    postal_code: str
    country: str
    is_default: bool = False


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    kind: str
    recipient_name: str
    line1: str
    line2: str | None
    city: str
    region: str | None
    postal_code: str
    country: str
    is_default: bool
    created_at: datetime
