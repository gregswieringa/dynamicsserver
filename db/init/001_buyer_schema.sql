-- Phase 0: buyer/user profile schema.
-- Source of truth for the schema. The API's SQLAlchemy models mirror this;
-- they never call create_all() against it.

CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

CREATE TYPE account_status AS ENUM ('pending_verification', 'active', 'suspended', 'deactivated');
CREATE TYPE user_role AS ENUM ('buyer', 'seller', 'both');
CREATE TYPE address_kind AS ENUM ('shipping', 'billing', 'both');

CREATE TABLE users (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email                       TEXT NOT NULL UNIQUE,
    email_verified              BOOLEAN NOT NULL DEFAULT FALSE,
    phone                       TEXT,
    phone_verified              BOOLEAN NOT NULL DEFAULT FALSE,
    password_hash               TEXT,
    display_name                TEXT NOT NULL,
    first_name                  TEXT,
    last_name                   TEXT,
    date_of_birth               DATE,
    locale                      TEXT NOT NULL DEFAULT 'en-US',
    currency                    TEXT NOT NULL DEFAULT 'USD',
    marketing_opt_in            BOOLEAN NOT NULL DEFAULT FALSE,
    account_status              account_status NOT NULL DEFAULT 'pending_verification',
    role                        user_role NOT NULL DEFAULT 'buyer',
    risk_score                  NUMERIC(5, 2) NOT NULL DEFAULT 0,
    fraud_flags                 JSONB NOT NULL DEFAULT '[]'::jsonb,
    last_login_at               TIMESTAMPTZ,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT phone_e164 CHECK (phone IS NULL OR phone ~ '^\+?[1-9]\d{6,14}$')
);

CREATE TABLE addresses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    kind            address_kind NOT NULL DEFAULT 'shipping',
    recipient_name  TEXT NOT NULL,
    line1           TEXT NOT NULL,
    line2           TEXT,
    city            TEXT NOT NULL,
    region          TEXT,
    postal_code     TEXT NOT NULL,
    country         TEXT NOT NULL,
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE payment_methods (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    processor        TEXT NOT NULL,
    processor_token  TEXT NOT NULL, -- opaque reference from the processor; never raw card data
    brand            TEXT,
    last4            TEXT,
    exp_month        SMALLINT,
    exp_year         SMALLINT,
    is_default       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- users -> addresses/payment_methods is circular, so these defaults are
-- added after both sides exist.
ALTER TABLE users ADD COLUMN default_shipping_address_id UUID REFERENCES addresses(id);
ALTER TABLE users ADD COLUMN default_payment_method_id UUID REFERENCES payment_methods(id);

CREATE INDEX idx_addresses_user_id ON addresses(user_id);
CREATE INDEX idx_payment_methods_user_id ON payment_methods(user_id);

-- at most one default address/payment method per user
CREATE UNIQUE INDEX one_default_address_per_user ON addresses(user_id) WHERE is_default;
CREATE UNIQUE INDEX one_default_payment_method_per_user ON payment_methods(user_id) WHERE is_default;

CREATE FUNCTION set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_set_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();
