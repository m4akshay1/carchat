"""Settings, all read from environment variables. Nothing secret lives in code."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# Which Claude model answers questions. Override with CARCHAT_MODEL.
MODEL = os.getenv("CARCHAT_MODEL", "claude-opus-5-5")


@dataclass(frozen=True)
class Role:
    """A signed-in role: the one view it may read and the database user it connects as."""

    name: str          # "sales" or "gm"
    title: str         # shown to the model and on the page
    view: str          # the only relation this role may query
    db_url_var: str    # name of the env var holding its read-only connection string

    @property
    def db_url(self) -> str:
        return os.environ[self.db_url_var]


ROLES = {
    "sales": Role("sales", "sales manager", "inventory_view", "DATABASE_URL_SALES"),
    "gm": Role("gm", "general manager", "inventory_gm_view", "DATABASE_URL_GM"),
}
