from __future__ import annotations

from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models import LinkModel, ReferralModel, SubscriptionModel, TrialModel, UserModel


class BaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, instance):
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def delete(self, instance) -> None:
        await self.session.delete(instance)
        await self.session.flush()


class UserRepository(BaseRepository):
    async def create(self, telegram_id: int, user_name: str | None = None) -> UserModel:
        user = UserModel(telegram_id=telegram_id, user_name=user_name)
        return await self.add(user)

    async def get_by_id(self, user_id: int) -> UserModel | None:
        stmt = (
            select(UserModel)
            .options(
                selectinload(UserModel.subscription),
                selectinload(UserModel.trial),
                selectinload(UserModel.links),
            )
            .where(UserModel.id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> UserModel | None:
        stmt = (
            select(UserModel)
            .options(
                selectinload(UserModel.subscription),
                selectinload(UserModel.trial),
                selectinload(UserModel.links),
            )
            .where(UserModel.telegram_id == telegram_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[UserModel]:
        stmt = (
            select(UserModel)
            .options(
                selectinload(UserModel.subscription),
                selectinload(UserModel.trial),
                selectinload(UserModel.links),
            )
            .offset(offset)
            .limit(limit)
            .order_by(UserModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_user_name(self, user_id: int, user_name: str | None) -> UserModel | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.user_name = user_name
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def get_or_create(self, telegram_id: int, user_name: str | None = None) -> tuple[UserModel, bool]:
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            return user, False

        user = await self.create(telegram_id=telegram_id, user_name=user_name)
        return user, True

    async def increment_referrals_count(self, user_id: int, value: int = 1) -> UserModel | None:
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.referrals_count += value
        await self.session.flush()
        await self.session.refresh(user)
        return user


class SubscriptionRepository(BaseRepository):
    async def create(
        self,
        user_id: int,
        subscription_period: int,
        end_subscriptions: date | None = None,
    ) -> SubscriptionModel:
        subscription = SubscriptionModel(
            user_id=user_id,
            subscription_period=subscription_period,
            end_subscriptions=end_subscriptions,
        )
        return await self.add(subscription)

    async def get_by_id(self, subscription_id: int) -> SubscriptionModel | None:
        stmt = (
            select(SubscriptionModel)
            .options(selectinload(SubscriptionModel.user))
            .where(SubscriptionModel.id == subscription_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: int) -> SubscriptionModel | None:
        stmt = (
            select(SubscriptionModel)
            .options(selectinload(SubscriptionModel.user))
            .where(SubscriptionModel.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[SubscriptionModel]:
        stmt = (
            select(SubscriptionModel)
            .options(selectinload(SubscriptionModel.user))
            .offset(offset)
            .limit(limit)
            .order_by(SubscriptionModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_end_date(self, target_date: date) -> list[SubscriptionModel]:
        stmt = (
            select(SubscriptionModel)
            .options(selectinload(SubscriptionModel.user))
            .where(SubscriptionModel.end_subscriptions == target_date)
            .order_by(SubscriptionModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        user_id: int,
        subscription_period: int | None = None,
        end_subscriptions: date | None = None,
    ) -> SubscriptionModel | None:
        subscription = await self.get_by_user_id(user_id)
        if subscription is None:
            return None

        if subscription_period is not None:
            subscription.subscription_period = subscription_period
        subscription.end_subscriptions = end_subscriptions

        await self.session.flush()
        await self.session.refresh(subscription)
        return subscription

    async def delete_by_user_id(self, user_id: int) -> bool:
        subscription = await self.get_by_user_id(user_id)
        if subscription is None:
            return False

        await self.delete(subscription)
        return True


class TrialRepository(BaseRepository):
    async def create(self, user_id: int, is_active: bool = False) -> TrialModel:
        trial = TrialModel(user_id=user_id, is_active=is_active)
        return await self.add(trial)

    async def get_by_user_id(self, user_id: int) -> TrialModel | None:
        stmt = (
            select(TrialModel)
            .options(selectinload(TrialModel.user))
            .where(TrialModel.user_id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self, limit: int = 100, offset: int = 0) -> list[TrialModel]:
        stmt = (
            select(TrialModel)
            .options(selectinload(TrialModel.user))
            .offset(offset)
            .limit(limit)
            .order_by(TrialModel.user_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def set_active(self, user_id: int, is_active: bool) -> TrialModel | None:
        trial = await self.get_by_user_id(user_id)
        if trial is None:
            return None

        trial.is_active = is_active
        await self.session.flush()
        await self.session.refresh(trial)
        return trial

    async def delete_by_user_id(self, user_id: int) -> bool:
        stmt = delete(TrialModel).where(TrialModel.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0


class LinkRepository(BaseRepository):
    async def create(self, link: str, user_id: int | None = None) -> LinkModel:
        instance = LinkModel(user_id=user_id, link=link)
        return await self.add(instance)

    async def get_by_id(self, link_id: int) -> LinkModel | None:
        stmt = (
            select(LinkModel)
            .options(selectinload(LinkModel.user))
            .where(LinkModel.id == link_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user_id(self, user_id: int) -> list[LinkModel]:
        stmt = (
            select(LinkModel)
            .options(selectinload(LinkModel.user))
            .where(LinkModel.user_id == user_id)
            .order_by(LinkModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_first_by_user_id(self, user_id: int) -> LinkModel | None:
        stmt = (
            select(LinkModel)
            .options(selectinload(LinkModel.user))
            .where(LinkModel.user_id == user_id)
            .order_by(LinkModel.id)
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_first_unassigned(self) -> LinkModel | None:
        stmt = (
            select(LinkModel)
            .where(LinkModel.user_id.is_(None))
            .order_by(LinkModel.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def assign_to_user(self, link_id: int, user_id: int) -> LinkModel | None:
        link = await self.get_by_id(link_id)
        if link is None:
            return None

        link.user_id = user_id
        await self.session.flush()
        await self.session.refresh(link)
        return link

    async def delete_by_id(self, link_id: int) -> bool:
        link = await self.get_by_id(link_id)
        if link is None:
            return False

        await self.delete(link)
        return True

    async def delete_by_user_id(self, user_id: int) -> int:
        stmt = delete(LinkModel).where(LinkModel.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0


class ReferralRepository(BaseRepository):
    async def create(
        self,
        *,
        inviter_user_id: int | None,
        inviter_telegram_id: int,
        invited_user_id: int | None,
        invited_telegram_id: int,
        is_converted: bool = False,
    ) -> ReferralModel:
        referral = ReferralModel(
            inviter_user_id=inviter_user_id,
            inviter_telegram_id=inviter_telegram_id,
            invited_user_id=invited_user_id,
            invited_telegram_id=invited_telegram_id,
            is_converted=is_converted,
        )
        return await self.add(referral)

    async def get_by_invited_user_id(self, invited_user_id: int) -> ReferralModel | None:
        stmt = (
            select(ReferralModel)
            .options(
                selectinload(ReferralModel.inviter),
                selectinload(ReferralModel.invited),
            )
            .where(ReferralModel.invited_user_id == invited_user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_invited_telegram_id(self, invited_telegram_id: int) -> ReferralModel | None:
        stmt = (
            select(ReferralModel)
            .options(
                selectinload(ReferralModel.inviter),
                selectinload(ReferralModel.invited),
            )
            .where(ReferralModel.invited_telegram_id == invited_telegram_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_inviter_user_id(self, inviter_user_id: int) -> list[ReferralModel]:
        stmt = (
            select(ReferralModel)
            .options(
                selectinload(ReferralModel.inviter),
                selectinload(ReferralModel.invited),
            )
            .where(ReferralModel.inviter_user_id == inviter_user_id)
            .order_by(ReferralModel.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_converted(self, referral_id: int, is_converted: bool = True) -> ReferralModel | None:
        referral = await self.get_by_id(referral_id)
        if referral is None:
            return None

        referral.is_converted = is_converted
        await self.session.flush()
        await self.session.refresh(referral)
        return referral

    async def detach_user_links(self, user_id: int) -> int:
        stmt = select(ReferralModel).where(
            (ReferralModel.inviter_user_id == user_id) | (ReferralModel.invited_user_id == user_id)
        )
        result = await self.session.execute(stmt)
        referrals = list(result.scalars().all())

        for referral in referrals:
            if referral.inviter_user_id == user_id:
                referral.inviter_user_id = None
            if referral.invited_user_id == user_id:
                referral.invited_user_id = None

        await self.session.flush()
        return len(referrals)

    async def get_by_id(self, referral_id: int) -> ReferralModel | None:
        stmt = (
            select(ReferralModel)
            .options(
                selectinload(ReferralModel.inviter),
                selectinload(ReferralModel.invited),
            )
            .where(ReferralModel.id == referral_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
