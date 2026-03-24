from __future__ import annotations

import os
from typing import Final

from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_int(name: str, default: int) -> int:
    return int(_get_env(name, str(default)))


def _get_float(name: str, default: float) -> float:
    return float(_get_env(name, str(default)))


def _get_bool(name: str, default: bool = False) -> bool:
    return _get_env(name, str(default)).lower() in {"1", "true", "yes", "on"}


def _get_int_list(name: str) -> list[int]:
    raw_value = _get_env(name)
    if not raw_value:
        return []

    values: list[int] = []
    for part in raw_value.split(","):
        value = part.strip()
        if value:
            values.append(int(value))
    return values


def _build_webhook_url(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if not base_url:
        return normalized_path
    return f"{base_url.rstrip('/')}{normalized_path}"


def _normalize_public_base_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    if not normalized:
        return ""
    if "://" not in normalized:
        return f"https://{normalized}"
    return normalized


APP_ENV: Final[str] = _get_env("LAVA_API", "production")
DEBUG: Final[bool] = _get_bool("DEBUG", False)

DB_URL: Final[str] = _get_env("DB_URL")
BOT_TOKEN: Final[str] = _get_env("BOT_TOKEN")

LOG_LEVEL: Final[str] = _get_env("LOG_LEVEL", "INFO").upper()
LOG_JSON: Final[bool] = _get_bool("LOG_JSON", True)

LAVA_API: Final[str] = _get_env("LAVA_API")
LAVA_ENV: Final[str] = _get_env("LAVA_ENV", "production")
LAVA_API_URL: Final[str] = _get_env("LAVA_API_URL", "https://gate.lava.top").rstrip("/")
LAVA_TIMEOUT_SEC: Final[float] = _get_float("LAVA_TIMEOUT_SEC", 10.0)
LAVA_MAX_RETRIES: Final[int] = _get_int("LAVA_MAX_RETRIES", 2)
LAVA_WEBHOOK_SECRET: Final[str] = _get_env("LAVA_WEBHOOK_SECRET")
LAVA_WEBHOOK_SIGNATURE_HEADER: Final[str] = _get_env(
    "LAVA_WEBHOOK_SIGNATURE_HEADER", "signature"
)


LAVA_OFFER_ID_MONTHLY: Final[str] = _get_env("OFFER_ID_1")
LAVA_OFFER_ID_3_MONTHS: Final[str] = _get_env("OFFER_ID_3")
LAVA_OFFER_ID_6_MONTHS: Final[str] = _get_env("OFFER_ID_6")
LAVA_OFFER_ID_12_MONTHS: Final[str] = _get_env("OFFER_ID_12")

WEBHOOK_BASE_URL: Final[str] = _normalize_public_base_url(
    _get_env("WEBHOOK_URL") or _get_env("BASIK_WEEB_HOOK")
)
WEBHOOK_HOST: Final[str] = _get_env("WEBHOOK_HOST", "127.0.0.1")
WEBHOOK_PORT: Final[int] = _get_int("WEBHOOK_PORT", 7998)
WEBHOOK_PATH: Final[str] = _get_env("WEBHOOK_PATH", "/lava/webhook")
WEBHOOK_URL: Final[str] = _build_webhook_url(WEBHOOK_BASE_URL, WEBHOOK_PATH)
WEBHOOK_QUEUE_MAXSIZE: Final[int] = _get_int("WEBHOOK_QUEUE_MAXSIZE", 1000)
WEBHOOK_WORKERS: Final[int] = _get_int("WEBHOOK_WORKERS", 4)
ADMIN_IDS: Final[list[int]] = _get_int_list("ADMIN_IDS")
