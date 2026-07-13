import os

import httpx
import psycopg
import pytest

BASE_URL = os.environ.get("BUYER_API_BASE_URL", "http://localhost:8001")
DATABASE_URL = os.environ.get(
    "BUYER_API_TEST_DATABASE_URL", "postgresql://buyer:buyer@localhost:5433/marketplace"
)


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as http_client:
        yield http_client


@pytest.fixture
def db_conn():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        yield conn


@pytest.fixture(autouse=True)
def _clean_tables():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute("TRUNCATE TABLE payment_methods, addresses, users RESTART IDENTITY CASCADE")
    yield
