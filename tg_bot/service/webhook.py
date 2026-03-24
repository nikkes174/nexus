from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date

from lava_top_sdk import LavaClient, LavaClientConfig, WebhookEventType
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    LAVA_API,
    LAVA_API_URL,
    LAVA_ENV,
    LAVA_MAX_RETRIES,
    LAVA_TIMEOUT_SEC,
)
from db.crud import SubscriptionRepository, UserRepository
from db.service import LinkAssignmentService
from logging_config import get_logger
from tg_bot.service.payment import PaymentConfigError, TariffCode
from tg_bot.service.referal_system import ReferralRewardService

USER_ID_PATTERN = re.compile(r"^tg_user_id:(?P<telegram_id>\d+)$")
SUCCESS_EVENT_TYPES = {
    WebhookEventType.PAYMENT_SUCCESS,
    WebhookEventType.SUBSCRIPTION_RECURRING_PAYMENT_SUCCESS,
}
TARIFF_MONTHS = {
    TariffCode.MONTH_1: 1,
    TariffCode.MONTH_3: 3,
    TariffCode.MONTH_6: 6,
    TariffCode.MONTH_12: 12,
}


class WebhookError(Exception):
    pass


class WebhookPayloadError(WebhookError):
    pass


@dataclass(frozen=True)
class WebhookProcessResult:
    status: str
    contract_id: str | None = None
    user_id: int | None = None
    telegram_user_id: int | None = None
    subscription_end: date | None = None
    assigned_link: str | None = None
    subscription_extended: bool = False
    referral_bonus_days: int = 0
    referral_inviter_telegram_id: int | None = None


class LavaWebhookService:
    logger = get_logger(__name__)

    @staticmethod
    def _build_client() -> LavaClient:
        if not LAVA_API:
            raise PaymentConfigError("Не задан LAVA_API")

        return LavaClient(
            LavaClientConfig(
                api_key=LAVA_API,
                env=LAVA_ENV,
                base_url=LAVA_API_URL,
                timeout=int(LAVA_TIMEOUT_SEC),
                max_retries=LAVA_MAX_RETRIES,
            )
        )

    @classmethod
    async def process_webhook(
        cls,
        *,
        payload: str,
        signature: str | None,
        session: AsyncSession,
    ) -> WebhookProcessResult:
        try:
            payload_data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise WebhookPayloadError("Webhook содержит невалидный JSON") from exc

        event = cls._build_client().parse_webhook(payload_data)

        if event.eventType not in SUCCESS_EVENT_TYPES:
            return WebhookProcessResult(status="ignored", contract_id=event.contractId)

        tariff_code = cls._extract_tariff_code(event.clientUtm.utm_campaign if event.clientUtm else None)
        telegram_user_id = cls._extract_telegram_user_id(
            event.clientUtm.utm_content if event.clientUtm else None
        )

        user_repo = UserRepository(session)
        subscription_repo = SubscriptionRepository(session)
        link_assignment_service = LinkAssignmentService(session)
        referral_reward_service = ReferralRewardService(session)

        user, _ = await user_repo.get_or_create(telegram_id=telegram_user_id)
        subscription = await subscription_repo.get_by_user_id(user.id)
        had_active_subscription = (
            subscription is not None
            and subscription.end_subscriptions is not None
            and subscription.end_subscriptions >= date.today()
        )

        months = TARIFF_MONTHS[TariffCode(tariff_code)]
        new_end = cls._calculate_subscription_end(
            current_end=subscription.end_subscriptions if subscription is not None else None,
            months=months,
        )

        try:
            if subscription is None:
                await subscription_repo.create(
                    user_id=user.id,
                    subscription_period=months,
                    end_subscriptions=new_end,
                )
            else:
                await subscription_repo.update(
                    user_id=user.id,
                    subscription_period=months,
                    end_subscriptions=new_end,
                )

            link_assignment_result = await link_assignment_service.assign_free_link_to_user(user.id)
            referral_reward_result = await referral_reward_service.apply_reward_for_paid_referral(
                invited_user_id=user.id,
                invited_telegram_id=telegram_user_id,
                tariff_months=months,
            )
            await session.commit()
        except IntegrityError:
            await session.rollback()
            raise

        return WebhookProcessResult(
            status="processed",
            contract_id=event.contractId,
            user_id=user.id,
            telegram_user_id=telegram_user_id,
            subscription_end=new_end,
            assigned_link=link_assignment_result.link_value,
            subscription_extended=had_active_subscription,
            referral_bonus_days=referral_reward_result.bonus_days,
            referral_inviter_telegram_id=referral_reward_result.inviter_telegram_id,
        )

    @staticmethod
    def _extract_tariff_code(utm_campaign: str | None) -> str:
        if not utm_campaign:
            raise WebhookPayloadError("В webhook отсутствует utm_campaign")

        try:
            return TariffCode(utm_campaign).value
        except ValueError as exc:
            raise WebhookPayloadError("В webhook пришёл неизвестный тариф") from exc

    @staticmethod
    def _extract_telegram_user_id(utm_content: str | None) -> int:
        if not utm_content:
            raise WebhookPayloadError("В webhook отсутствует utm_content")

        match = USER_ID_PATTERN.fullmatch(utm_content)
        if match is None:
            raise WebhookPayloadError("Невозможно извлечь telegram_id из utm_content")

        return int(match.group("telegram_id"))

    @staticmethod
    def _calculate_subscription_end(current_end: date | None, months: int) -> date:
        today = date.today()
        base_date = current_end if current_end is not None and current_end >= today else today

        month_index = base_date.month - 1 + months
        year = base_date.year + month_index // 12
        month = month_index % 12 + 1
        day = min(base_date.day, LavaWebhookService._days_in_month(year, month))
        return date(year, month, day)

    @staticmethod
    def _days_in_month(year: int, month: int) -> int:
        if month == 2:
            is_leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
            return 29 if is_leap else 28
        if month in {4, 6, 9, 11}:
            return 30
        return 31
