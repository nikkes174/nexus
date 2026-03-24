from __future__ import annotations

import asyncio
import os
import re
import socket
import sys

import asyncpg
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand, MenuButtonCommands
from aiogram.types.bot_command_scope_default import BotCommandScopeDefault
from sqlalchemy.exc import DBAPIError

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    DB_URL,
    DEBUG,
    LAVA_WEBHOOK_SIGNATURE_HEADER,
    WEBHOOK_HOST,
    WEBHOOK_PATH,
    WEBHOOK_PORT,
    WEBHOOK_QUEUE_MAXSIZE,
    WEBHOOK_URL,
    WEBHOOK_WORKERS,
)
from logging_config import configure_logging, get_logger
from tg_bot.handlers.user import router as user_router
from tg_bot.service.webhook_worker import LavaWebhookWorkerService

logger = get_logger(__name__)
DB_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TELEGRAM_API_TIMEOUT_SEC = 15


def build_db_url() -> str:
    if DB_URL:
        return DB_URL

    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "nexus")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{database}"


def parse_db_settings(db_url: str) -> dict[str, str]:
    prefix = "postgresql+asyncpg://"
    if not db_url.startswith(prefix):
        raise ValueError("DB_URL должен начинаться с postgresql+asyncpg://")

    raw = db_url.removeprefix(prefix)
    credentials, address = raw.split("@", maxsplit=1)
    user, password = credentials.split(":", maxsplit=1)
    host_port, database = address.rsplit("/", maxsplit=1)
    host, port = host_port.split(":", maxsplit=1)

    if not DB_NAME_PATTERN.fullmatch(database):
        raise ValueError("Имя базы данных должно содержать только буквы, цифры и underscore")

    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "database": database,
    }


async def ensure_database_exists() -> None:
    db_url = build_db_url()
    settings = parse_db_settings(db_url)

    try:
        connection = await asyncpg.connect(
            user=settings["user"],
            password=settings["password"],
            host=settings["host"],
            port=int(settings["port"]),
            database=settings["database"],
            ssl=False,
        )
    except asyncpg.InvalidCatalogNameError:
        connection = await asyncpg.connect(
            user=settings["user"],
            password=settings["password"],
            host=settings["host"],
            port=int(settings["port"]),
            database="postgres",
            ssl=False,
        )
    else:
        await connection.close()
        os.environ["DB_URL"] = db_url
        return

    try:
        exists = await connection.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            settings["database"],
        )
        if not exists:
            await connection.execute(f'CREATE DATABASE "{settings["database"]}"')
            logger.info("Database created", extra={"database": settings["database"]})
    finally:
        await connection.close()

    os.environ["DB_URL"] = db_url


async def on_startup(bot: Bot, admin_ids: list[int]) -> None:
    commands = [
        BotCommand(command="start", description="Перезапуск бота"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())

    for admin_id in admin_ids:
        try:
            await bot.send_message(chat_id=admin_id, text="Бот запущен")
        except Exception:
            logger.exception("Admin startup message failed", extra={"admin_id": admin_id})


async def run_telegram_step(step_name: str, awaitable) -> None:
    logger.info("Telegram startup step", extra={"step": step_name})
    try:
        await asyncio.wait_for(awaitable, timeout=TELEGRAM_API_TIMEOUT_SEC)
    except asyncio.TimeoutError as exc:
        raise RuntimeError(
            f"Telegram API timeout during '{step_name}' after {TELEGRAM_API_TIMEOUT_SEC} seconds. "
            "Check access to api.telegram.org:443, firewall, proxy, or VPN settings."
        ) from exc
    except TelegramNetworkError as exc:
        raise RuntimeError(
            f"Telegram API is unreachable during '{step_name}'. "
            "Check access to api.telegram.org:443, firewall, proxy, or VPN settings."
        ) from exc


async def webhook_handler(request: web.Request) -> web.Response:
    payload = await request.text()
    signature = request.headers.get(LAVA_WEBHOOK_SIGNATURE_HEADER, "").strip() or None
    webhook_worker: LavaWebhookWorkerService = request.app["webhook_worker"]

    if not webhook_worker.enqueue(payload=payload, signature=signature):
        return web.json_response({"status": "busy"}, status=503)

    return web.json_response({"status": "accepted"})


async def start_webhook_server(bot: Bot) -> tuple[web.AppRunner, LavaWebhookWorkerService]:
    app = web.Application()
    webhook_worker = LavaWebhookWorkerService(
        bot=bot,
        worker_count=WEBHOOK_WORKERS,
        queue_maxsize=WEBHOOK_QUEUE_MAXSIZE,
    )
    await webhook_worker.start()
    app["webhook_worker"] = webhook_worker
    app.router.add_post("/", webhook_handler)
    app.router.add_post(WEBHOOK_PATH, webhook_handler)

    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, host=WEBHOOK_HOST, port=WEBHOOK_PORT)
    await site.start()

    logger.info(
        "Webhook server ok",
        extra={
            "webhook_url": WEBHOOK_URL,
            "webhook_workers": WEBHOOK_WORKERS,
            "webhook_queue_maxsize": WEBHOOK_QUEUE_MAXSIZE,
        },
    )
    return runner, webhook_worker


async def main() -> None:
    configure_logging()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан")

    await ensure_database_exists()

    from db.db import init_db

    for attempt in range(1, 4):
        try:
            await init_db()
            break
        except (DBAPIError, ConnectionError, OSError) as exc:
            if attempt == 3:
                logger.warning(
                    "Database init skipped after retries",
                    extra={"attempt": attempt, "error": str(exc)},
                )
                break
            logger.warning(
                "Database init retry",
                extra={"attempt": attempt, "error": str(exc)},
            )
            await asyncio.sleep(2)

    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    bot = Bot(token=BOT_TOKEN, session=session)
    webhook_runner: web.AppRunner | None = None
    webhook_worker: LavaWebhookWorkerService | None = None
    try:
        await run_telegram_step(
            "delete_webhook",
            bot.delete_webhook(drop_pending_updates=False),
        )
        await run_telegram_step(
            "set_commands_and_notify_admins",
            on_startup(bot, ADMIN_IDS),
        )

        dp = Dispatcher()
        dp.include_router(user_router)
        webhook_runner, webhook_worker = await start_webhook_server(bot)

        logger.info("Bot ok", extra={"debug": DEBUG})
        await dp.start_polling(bot)
    finally:
        if webhook_runner is not None:
            await webhook_runner.cleanup()
        if webhook_worker is not None:
            await webhook_worker.stop()
        await bot.session.close()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
