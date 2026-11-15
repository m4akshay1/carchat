"""Tests for login, sessions and the chat API. Claude is replaced by a stub."""

import os

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app.chat import ChatResult

pytestmark = pytest.mark.skipif(not os.getenv("SALES_PASSCODE"), reason="needs .env")


@pytest.fixture
def client(monkeypatch):
    main.limiter.reset()
    monkeypatch.setattr(main, "COOKIE_SECURE", False)  # the test client speaks plain http
    seen = []

    def fake_answer(question, role):
        seen.append((question, role.name))
        return ChatResult(answer="stub", sql="SELECT 1", columns=["n"], rows=[[1]])

    monkeypatch.setattr(main, "answer_question", fake_answer)
    test_client = TestClient(main.app)
    test_client.seen = seen
    return test_client


def login(client, role):
    passcode = os.environ["SALES_PASSCODE" if role == "sales" else "GM_PASSCODE"]
    return client.post("/api/login", json={"passcode": passcode})


def test_chat_requires_a_session(client):
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 401
    assert client.get("/api/me").status_code == 401
    assert client.seen == []


def test_wrong_passcode_is_rejected(client):
    assert client.post("/api/login", json={"passcode": "not-the-passcode"}).status_code == 401
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("role", ["sales", "gm"])
def test_passcode_decides_the_role(client, role):
    assert login(client, role).json()["role"] == role
    assert client.get("/api/me").json()["role"] == role
    reply = client.post("/api/chat", json={"question": "How many?"})
    assert reply.status_code == 200 and reply.json()["rows"] == [[1]]
    assert client.seen == [("How many?", role)]


def test_cookie_is_httponly_and_strict(client):
    header = login(client, "sales").headers["set-cookie"].lower()
    assert "httponly" in header and "samesite=strict" in header


def test_tampered_cookie_is_rejected(client):
    login(client, "sales")
    token = client.cookies.get(main.COOKIE_NAME)
    client.cookies.clear()  # otherwise the genuine cookie is still sent alongside the tampered one
    client.cookies.set(main.COOKIE_NAME, token[:-2] + ("aa" if token[-2:] != "aa" else "bb"))
    assert client.post("/api/chat", json={"question": "hi"}).status_code == 401


def test_forged_role_cookie_is_rejected(client):
    client.cookies.set(main.COOKIE_NAME, "gm")
    assert client.get("/api/me").status_code == 401


def test_sign_out_ends_the_session(client):
    login(client, "gm")
    client.post("/api/logout", json={})
    assert client.get("/api/me").status_code == 401


def test_long_question_is_rejected(client):
    login(client, "sales")
    assert client.post("/api/chat", json={"question": "x" * 501}).status_code == 422
    assert client.seen == []


def test_login_is_rate_limited(client):
    codes = [client.post("/api/login", json={"passcode": "guess"}).status_code for _ in range(7)]
    assert codes[:5] == [401] * 5 and codes[-1] == 429


def test_chat_is_rate_limited(client):
    login(client, "sales")
    codes = [client.post("/api/chat", json={"question": "q"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[-1] == 429


def test_security_headers_and_no_api_docs(client):
    page = client.get("/")
    assert page.status_code == 200 and "CarChat" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
