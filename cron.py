from __future__ import annotations

import asyncio
import socket
import sys

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from sqlalchemy.exc import DBAPIError

from bot import BOT_TOKEN, ensure_database_exists
from config import ADMIN_IDS
from logging_config import configure_logging, get_logger
from tg_bot.service.scheduler import SubscriptionReminderService

logger = get_logger(__name__)


async def main() -> None:
    configure_logging()

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN РЅРµ Р·Р°РґР°РЅ")

    await ensure_database_exists()

    from db.db import init_db

    for attempt in range(1, 4):
        try:
            await init_db()
            break
        except (DBAPIError, ConnectionError, OSError) as exc:
            if attempt == 3:
                raise RuntimeError("Database init failed for cron job") from exc
            logger.warning(
                "Database init retry in cron",
                extra={"attempt": attempt, "error": str(exc)},
            )
            await asyncio.sleep(2)

    session = AiohttpSession()
    session._connector_init["family"] = socket.AF_INET
    bot = Bot(token=BOT_TOKEN, session=session)

    try:
        result = await SubscriptionReminderService(bot).notify_last_subscription_day()

        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    chat_id=admin_id,
                    text=(
                        "Проверка подписок завершена.\n"
                        f"Дата проверки: {result.target_date}\n"
                        f"Заканчивается подписка у {result.expiring_count} человек.\n"
                        f"Уведомление отправлено {result.notified_count} человек."
                    ),
                )
            except Exception:
                logger.exception("Cron admin notification failed", extra={"admin_id": admin_id})
    finally:
        await bot.session.close()


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
