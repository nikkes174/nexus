from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import LinkRepository, SubscriptionRepository, TrialRepository, UserRepository
from logging_config import get_logger


@dataclass(frozen=True)
class LinkAssignmentResult:
    assigned: bool
    link_id: int | None = None
    link_value: str | None = None


@dataclass(frozen=True)
class TrialActivationResult:
    activated: bool
    user_id: int | None = None
    subscription_end: date | None = None
    assigned_link: str | None = None


class LinkAssignmentService:
    logger = get_logger(__name__)

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.link_repository = LinkRepository(session)

    async def assign_free_link_to_user(self, user_id: int) -> LinkAssignmentResult:
        existing_link = await self.link_repository.get_first_by_user_id(user_id)
        if existing_link is not None:
            self.logger.info(
                "User already has assigned link",
                extra={
                    "user_id": user_id,
                    "link_id": existing_link.id,
                },
            )
            return LinkAssignmentResult(
                assigned=False,
                link_id=existing_link.id,
                link_value=existing_link.link,
            )

        free_link = await self.link_repository.get_first_unassigned()
        if free_link is None:
            self.logger.warning(
                "No free links available for assignment",
                extra={"user_id": user_id},
            )
            return LinkAssignmentResult(assigned=False)

        assigned_link = await self.link_repository.assign_to_user(
            link_id=free_link.id,
            user_id=user_id,
        )
        if assigned_link is None:
            self.logger.warning(
                "Free link disappeared before assignment",
                extra={"user_id": user_id, "link_id": free_link.id},
            )
            return LinkAssignmentResult(assigned=False)

        self.logger.info(
            "Link assigned to user",
            extra={
                "user_id": user_id,
                "link_id": assigned_link.id,
            },
        )
        return LinkAssignmentResult(
            assigned=True,
            link_id=assigned_link.id,
            link_value=assigned_link.link,
        )


class TrialActivationService:
    logger = get_logger(__name__)

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repository = UserRepository(session)
        self.subscription_repository = SubscriptionRepository(session)
        self.trial_repository = TrialRepository(session)
        self.link_assignment_service = LinkAssignmentService(session)

    async def activate_trial(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
    ) -> TrialActivationResult:
        user, _ = await self.user_repository.get_or_create(
            telegram_id=telegram_user_id,
            user_name=username,
        )

        existing_trial = await self.trial_repository.get_by_user_id(user.id)
        if existing_trial is not None:
            return TrialActivationResult(activated=False, user_id=user.id)

        subscription = await self.subscription_repository.get_by_user_id(user.id)
        new_end = date.today() + timedelta(days=3)

        if subscription is None:
            await self.subscription_repository.create(
                user_id=user.id,
                subscription_period=3,
                end_subscriptions=new_end,
            )
        else:
            await self.subscription_repository.update(
                user_id=user.id,
                subscription_period=3,
                end_subscriptions=new_end,
            )

        link_assignment_result = await self.link_assignment_service.assign_free_link_to_user(user.id)
        await self.trial_repository.create(user_id=user.id, is_active=True)
        await self.session.commit()

        self.logger.info(
            "Trial activated",
            extra={
                "user_id": user.id,
                "telegram_user_id": telegram_user_id,
                "subscription_end": new_end.isoformat(),
                "link_assigned": link_assignment_result.assigned,
            },
        )

        return TrialActivationResult(
            activated=True,
            user_id=user.id,
            subscription_end=new_end,
            assigned_link=link_assignment_result.link_value,
        )
