"""Standalone fast tests that can run with core installed Python dependencies."""
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.schemas import ProjectCreate, RegisterRequest


def test_passwords_and_jwt():
    encoded = hash_password("correct-horse-battery")
    assert encoded != "correct-horse-battery"
    assert verify_password("correct-horse-battery", encoded)
    assert not verify_password("incorrect", encoded)
    assert decode_access_token(create_access_token(17)) == 17
    assert decode_access_token("not-a-token") is None


def test_pydantic_normalization():
    assert RegisterRequest(email="User@Example.com", password="abcdefgh").email == "user@example.com"
    assert ProjectCreate(name="  Test Project  ").name == "Test Project"
