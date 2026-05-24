from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_buyer_forgot_password_returns_generic_message():
    r = client.post(
        "/api/v1/auth/buyer/forgot-password",
        json={"email": "nobody@example.com"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert "reset link" in r.json()["message"].lower()


def test_reset_password_requires_matching_passwords():
    r = client.post(
        "/api/v1/auth/buyer/reset-password",
        json={
            "token": "a" * 32,
            "new_password": "NewPass123!",
            "new_password_confirm": "Mismatch123!",
        },
    )
    assert r.status_code == 422


def test_reset_password_invalid_token():
    r = client.post(
        "/api/v1/auth/buyer/reset-password",
        json={
            "token": "b" * 32,
            "new_password": "NewPass123!",
            "new_password_confirm": "NewPass123!",
        },
    )
    assert r.status_code == 400
