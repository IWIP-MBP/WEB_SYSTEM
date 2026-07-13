import pytest
from datetime import datetime, timedelta
from fastapi import HTTPException
from jose import jwt
from sqlalchemy import insert

import services.auth as auth
from database import settings
from models import users


class TestCreateAndVerifyToken:
    def test_roundtrip(self):
        token = auth.create_token({"sub": "alice"})
        payload = auth.verify_token(token)
        assert payload["sub"] == "alice"

    def test_token_includes_expiry(self):
        token = auth.create_token({"sub": "bob"})
        payload = auth.verify_token(token)
        assert "exp" in payload

    def test_verify_invalid_token_returns_none(self):
        assert auth.verify_token("not.a.jwt") is None

    def test_verify_wrong_signature_returns_none(self):
        forged = jwt.encode({"sub": "eve"}, "some-other-key", algorithm=settings.ALGORITHM)
        assert auth.verify_token(forged) is None

    def test_verify_expired_token_returns_none(self):
        expired = jwt.encode(
            {"sub": "alice", "exp": datetime.utcnow() - timedelta(hours=1)},
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM,
        )
        assert auth.verify_token(expired) is None


class _FakeRequest:
    def __init__(self, headers):
        self.headers = headers


class TestGetCurrentUser:
    def test_missing_header_raises_401(self, db):
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(_FakeRequest({}), db=db)
        assert e.value.status_code == 401

    def test_non_bearer_header_raises_401(self, db):
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(_FakeRequest({"Authorization": "Basic abc"}), db=db)
        assert e.value.status_code == 401

    def test_invalid_token_raises_401(self, db):
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(_FakeRequest({"Authorization": "Bearer garbage"}), db=db)
        assert e.value.status_code == 401

    def test_unknown_user_raises_401(self, db):
        token = auth.create_token({"sub": "ghost"})
        with pytest.raises(HTTPException) as e:
            auth.get_current_user(_FakeRequest({"Authorization": f"Bearer {token}"}), db=db)
        assert e.value.status_code == 401

    def test_valid_token_returns_user(self, db):
        db.execute(insert(users).values(username="alice", hashed_password="x", role="admin"))
        db.commit()
        token = auth.create_token({"sub": "alice"})
        user = auth.get_current_user(_FakeRequest({"Authorization": f"Bearer {token}"}), db=db)
        assert user["username"] == "alice"
        assert user["role"] == "admin"
