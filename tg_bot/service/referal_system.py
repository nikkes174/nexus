from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import ReferralRepository, SubscriptionRepository, UserRepository
from logging_config import get_logger

REFERRAL_BONUS_DAYS = {
    1: 5,
    3: 10,
    6: 15,
    12: 20,
}


@dataclass(frozen=True)
class ReferralRewardResult:
    applied: bool
    inviter_user_id: int | None = None
    inviter_telegram_id: int | None = None
    subscription_end: date | None = None
    bonus_days: int = 0
    counter_incremented: bool = False


@dataclass(frozen=True)
class ReferralLinkResult:
    available: bool
    referral_link: str | None = None


@dataclass(frozen=True)
class ReferralStartResult:
    user_id: int | None = None
    referral_created: bool = False


class ReferralRewardService:
    logger = get_logger(__name__)

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.referral_repository = ReferralRepository(session)
        self.subscription_repository = SubscriptionRepository(session)
        self.user_repository = UserRepository(session)

    async def get_personal_referral_link(
        self,
        *,
        telegram_user_id: int,
        bot_username: str,
    ) -> ReferralLinkResult:
        user = await self.user_repository.get_by_telegram_id(telegram_user_id)
        if user is None:
            return ReferralLinkResult(available=False)

        subscription = await self.subscription_repository.get_by_user_id(user.id)
        if (
            subscription is None
            or subscription.end_subscriptions is None
            or subscription.end_subscriptions < date.today()
        ):
            return ReferralLinkResult(available=False)

        return ReferralLinkResult(
            available=True,
            referral_link=f"https://t.me/{bot_username}?start=ref_{telegram_user_id}",
        )

    async def register_referral_start(
        self,
        *,
        inviter_telegram_id: int | None,
        invited_telegram_id: int,
        invited_username: str | None,
    ) -> ReferralStartResult:
        existing_referral = await self.referral_repository.get_by_invited_telegram_id(invited_telegram_id)
        if existing_referral is not None:
            return ReferralStartResult(user_id=existing_referral.invited_user_id, referral_created=False)

        existing_user = await self.user_repository.get_by_telegram_id(invited_telegram_id)
        if existing_user is not None:
            return ReferralStartResult(user_id=existing_user.id, referral_created=False)

        invited_user = await self.user_repository.create(
            telegram_id=invited_telegram_id,
            user_name=invited_username,
        )

        if inviter_telegram_id is None or inviter_telegram_id == invited_telegram_id:
            await self.session.commit()
            return ReferralStartResult(user_id=invited_user.id, referral_created=False)

        inviter = await self.user_repository.get_by_telegram_id(inviter_telegram_id)
        if inviter is None:
            await self.session.commit()
            return ReferralStartResult(user_id=invited_user.id, referral_created=False)

        inviter_subscription = await self.subscription_repository.get_by_user_id(inviter.id)
        if (
            inviter_subscription is None
            or inviter_subscription.end_subscriptions is None
            or inviter_subscription.end_subscriptions < date.today()
        ):
            await self.session.commit()
            return ReferralStartResult(user_id=invited_user.id, referral_created=False)

        await self.referral_repository.create(
            inviter_user_id=inviter.id,
            inviter_telegram_id=inviter.telegram_id,
            invited_user_id=invited_user.id,
            invited_telegram_id=invited_telegram_id,
        )
        await self.session.commit()
        return ReferralStartResult(user_id=invited_user.id, referral_created=True)

    async def apply_reward_for_paid_referral(
        self,
        *,
        invited_user_id: int,
        invited_telegram_id: int,
        tariff_months: int,
    ) -> ReferralRewardResult:
        bonus_days = REFERRAL_BONUS_DAYS.get(tariff_months)
        if bonus_days is None:
            return ReferralRewardResult(applied=False)

        referral = await self.referral_repository.get_by_invited_telegram_id(invited_telegram_id)
        if referral is None:
            return ReferralRewardResult(applied=False)

        if referral.is_converted:
            return ReferralRewardResult(applied=False)

        inviter = await self.user_repository.get_by_id(referral.inviter_user_id)
        inviter_subscription = await self.subscription_repository.get_by_user_id(referral.inviter_user_id)
        if inviter_subscription is None:
            self.logger.warning(
                "Referral reward skipped because inviter has no subscription",
                extra={
                    "inviter_user_id": referral.inviter_user_id,
                    "invited_user_id": invited_user_id,
                    "invited_telegram_id": invited_telegram_id,
                },
            )
            return ReferralRewardResult(
                applied=False,
                inviter_user_id=referral.inviter_user_id,
                inviter_telegram_id=inviter.telegram_id if inviter is not None else None,
            )

        today = date.today()
        base_date = (
            inviter_subscription.end_subscriptions
            if inviter_subscription.end_subscriptions is not None and inviter_subscription.end_subscriptions >= today
            else today
        )
        new_end = base_date + timedelta(days=bonus_days)
        await self.subscription_repository.update(
            user_id=referral.inviter_user_id,
            end_subscriptions=new_end,
        )

        counter_incremented = False
        if not referral.is_converted:
            await self.referral_repository.mark_converted(referral.id, True)
            await self.user_repository.increment_referrals_count(referral.inviter_user_id, 1)
            counter_incremented = True

        self.logger.info(
            "Referral reward applied",
            extra={
                "inviter_user_id": referral.inviter_user_id,
                "invited_user_id": invited_user_id,
                "invited_telegram_id": invited_telegram_id,
                "bonus_days": bonus_days,
                "subscription_end": new_end.isoformat(),
                "counter_incremented": counter_incremented,
            },
        )

        return ReferralRewardResult(
            applied=True,
            inviter_user_id=referral.inviter_user_id,
            inviter_telegram_id=inviter.telegram_id if inviter is not None else None,
            subscription_end=new_end,
            bonus_days=bonus_days,
            counter_incremented=counter_incremented,
        )
