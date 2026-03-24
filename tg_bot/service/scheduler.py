from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot

from db.crud import SubscriptionRepository
from db.db import AsyncSessionLocal
from logging_config import get_logger

try:
    MOSCOW_TZ = ZoneInfo("Europe/Moscow")
except ZoneInfoNotFoundError:
    MOSCOW_TZ = timezone(timedelta(hours=3))


@dataclass(frozen=True)
class SubscriptionReminderResult:
    target_date: str
    expiring_count: int
    notified_count: int


class SubscriptionReminderService:
    logger = get_logger(__name__)

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def notify_last_subscription_day(self) -> SubscriptionReminderResult:
        today_moscow = datetime.now(MOSCOW_TZ).date()

        async with AsyncSessionLocal() as session:
            subscriptions = await SubscriptionRepository(session).list_by_end_date(today_moscow)

        notified = 0
        expiring_count = len(subscriptions)
        for subscription in subscriptions:
            if subscription.user is None:
                continue

            try:
                await self.bot.send_message(
                    chat_id=subscription.user.telegram_id,
                    text="⚡️Здравствуйте, сегодня последний день подписки\n"
                         "Для продолжения пользования сервисом продлите подписку",
                )
                notified += 1
            except Exception:
                self.logger.exception(
                    "Subscription reminder failed",
                    extra={"telegram_user_id": subscription.user.telegram_id},
                )

        self.logger.info(
            "Subscription reminder run completed",
            extra={"target_date": today_moscow.isoformat(), "notified": notified},
        )
        return SubscriptionReminderResult(
            target_date=today_moscow.isoformat(),
            expiring_count=expiring_count,
            notified_count=notified,
        )
