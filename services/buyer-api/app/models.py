import uuid
from datetime import date, datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger
from sqlalchemy.dialects.postgresql import ENUM, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# create_type=False: these types already exist in Postgres via db/init/001_buyer_schema.sql
AccountStatus = ENUM(
    "pending_verification", "active", "suspended", "deactivated",
    name="account_status", create_type=False,
)
UserRole = ENUM("buyer", "seller", "both", name="user_role", create_type=False)
AddressKind = ENUM("shipping", "billing", "both", name="address_kind", create_type=False)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(unique=True)
    email_verified: Mapped[bool] = mapped_column(default=False)
    phone: Mapped[str | None]
    phone_verified: Mapped[bool] = mapped_column(default=False)
    password_hash: Mapped[str | None]
    display_name: Mapped[str]
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    date_of_birth: Mapped[date | None]
    locale: Mapped[str] = mapped_column(default="en-US")
    currency: Mapped[str] = mapped_column(default="USD")
    marketing_opt_in: Mapped[bool] = mapped_column(default=False)
    account_status: Mapped[str] = mapped_column(AccountStatus, default="pending_verification")
    role: Mapped[str] = mapped_column(UserRole, default="buyer")
    risk_score: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    fraud_flags: Mapped[list] = mapped_column(JSONB, default=list)
    default_shipping_address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id")
    )
    default_payment_method_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payment_methods.id")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    addresses: Mapped[list["Address"]] = relationship(
        back_populates="user", foreign_keys="Address.user_id"
    )


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(AddressKind, default="shipping")
    recipient_name: Mapped[str]
    line1: Mapped[str]
    line2: Mapped[str | None]
    city: Mapped[str]
    region: Mapped[str | None]
    postal_code: Mapped[str]
    country: Mapped[str]
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    user: Mapped["User"] = relationship(back_populates="addresses", foreign_keys=[user_id])


class PaymentMethod(Base):
    __tablename__ = "payment_methods"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    processor: Mapped[str]
    processor_token: Mapped[str]
    brand: Mapped[str | None]
    last4: Mapped[str | None]
    exp_month: Mapped[int | None] = mapped_column(SmallInteger)
    exp_year: Mapped[int | None] = mapped_column(SmallInteger)
    is_default: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
