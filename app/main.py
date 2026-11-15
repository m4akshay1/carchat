"""CarChat web service: passcode login, the chat API, and the static page."""

from __future__ import annotations

import hmac
import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, URLSafeTimedSerializer
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.chat import answer_question
from app.config import ROLES, Role

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
COOKIE_NAME = "carchat_session"
SESSION_SECONDS = 8 * 60 * 60  # a signed-in session lasts one working day
# Send the cookie over HTTPS only. Set COOKIE_SECURE=false for local http.
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() != "false"

app = FastAPI(title="CarChat", docs_url=None, redoc_url=None, openapi_url=None)

# --- Rate limiting: per IP address, so a public link cannot drain the API key.
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
def too_many_requests(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse({"detail": "Too many requests. Wait a minute and try again."}, status_code=429)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    # The page loads only its own files: no inline scripts, no third parties.
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# --- Sessions: the passcode decides the role; the role lives in a signed cookie.
def _signer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(os.environ["SESSION_SECRET"], salt="carchat-session")


def _role_for_passcode(passcode: str) -> Role | None:
    """Compare in constant time so response timing does not leak the passcode."""
    for role_name, env_var in (("sales", "SALES_PASSCODE"), ("gm", "GM_PASSCODE")):
        expected = os.environ.get(env_var, "")
        if expected and hmac.compare_digest(passcode.encode(), expected.encode()):
            return ROLES[role_name]
    return None


def current_role(request: Request) -> Role:
    """The signed-in role, read from the signed cookie. 401 if missing or tampered with."""
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        role_name = _signer().loads(token, max_age=SESSION_SECONDS)
    except BadSignature:  # also covers an expired signature
        raise HTTPException(status_code=401, detail="Sign in first.") from None
    if role_name not in ROLES:
        raise HTTPException(status_code=401, detail="Sign in first.")
    return ROLES[role_name]


class LoginIn(BaseModel):
    passcode: str = Field(min_length=1, max_length=200)


class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ChatOut(BaseModel):
    answer: str
    refused: bool
    sql: str | None
    columns: list[str]
    rows: list[list]


# --- API routes
@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check for the host. Touches nothing secret."""
    return {"status": "ok"}


@app.post("/api/login")
@limiter.limit("5/minute")  # slows down passcode guessing
def login(request: Request, response: Response, body: LoginIn) -> dict[str, str]:
    role = _role_for_passcode(body.passcode)
    if role is None:
        raise HTTPException(status_code=401, detail="That passcode is not recognised.")
    response.set_cookie(
        COOKIE_NAME,
        _signer().dumps(role.name),
        max_age=SESSION_SECONDS,
        httponly=True,       # not readable by JavaScript
        secure=COOKIE_SECURE,
        samesite="strict",   # never sent on requests started by another site
    )
    return {"role": role.name, "title": role.title}


@app.post("/api/logout")
def logout(response: Response) -> dict[str, bool]:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/me")
def me(role: Role = Depends(current_role)) -> dict[str, str]:
    return {"role": role.name, "title": role.title}


@app.post("/api/chat", response_model=ChatOut)
@limiter.limit("10/minute")
def chat(request: Request, body: ChatIn, role: Role = Depends(current_role)) -> ChatOut:
    result = answer_question(body.question.strip(), role)
    return ChatOut(
        answer=result.answer,
        refused=result.refused,
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
    )


# --- The page: one static HTML file plus its script and stylesheet.
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
