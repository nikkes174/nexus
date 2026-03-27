from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from db.crud import BloggerReferralLinkRepository, UserRepository
from logging_config import get_logger

BLOGGER_CODE_CLEAN_PATTERN = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class BloggerReferralStartResult:
    user_id: int | None = None
    blogger_referral_link_id: int | None = None
    linked: bool = False


@dataclass(frozen=True)
class BloggerReferralPaymentResult:
    applied: bool
    blogger_referral_link_id: int | None = None
    payment_amount: int = 0
    total_paid_count: int = 0
    total_paid_amount: int = 0


@dataclass(frozen=True)
class BloggerReferralCreateResult:
    created: bool
    blogger_referral_link_id: int | None = None
    blogger_name: str | None = None
    code: str | None = None


class BloggerReferralService:
    logger = get_logger(__name__)

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.user_repository = UserRepository(session)
        self.blogger_referral_link_repository = BloggerReferralLinkRepository(session)

    async def register_blogger_start(
        self,
        *,
        blogger_code: str | None,
        telegram_user_id: int,
        username: str | None,
    ) -> BloggerReferralStartResult:
        user, _ = await self.user_repository.get_or_create(
            telegram_id=telegram_user_id,
            user_name=username,
        )
        if blogger_code is None:
            await self.session.commit()
            return BloggerReferralStartResult(user_id=user.id)

        if user.blogger_referral_link_id is not None:
            await self.session.commit()
            return BloggerReferralStartResult(
                user_id=user.id,
                blogger_referral_link_id=user.blogger_referral_link_id,
                linked=False,
            )

        blogger_referral_link = await self.blogger_referral_link_repository.get_by_code(blogger_code)
        if blogger_referral_link is None:
            await self.session.commit()
            return BloggerReferralStartResult(user_id=user.id)

        await self.user_repository.set_blogger_referral_link(user.id, blogger_referral_link.id)
        await self.session.commit()

        self.logger.info(
            "Blogger referral link attached to user",
            extra={
                "user_id": user.id,
                "telegram_user_id": telegram_user_id,
                "blogger_referral_link_id": blogger_referral_link.id,
                "blogger_code": blogger_referral_link.code,
            },
        )

        return BloggerReferralStartResult(
            user_id=user.id,
            blogger_referral_link_id=blogger_referral_link.id,
            linked=True,
        )

    async def register_payment(
        self,
        *,
        user_id: int,
        amount_rub: int,
    ) -> BloggerReferralPaymentResult:
        user = await self.user_repository.get_by_id(user_id)
        if user is None or user.blogger_referral_link_id is None:
            return BloggerReferralPaymentResult(applied=False)

        blogger_referral_link = await self.blogger_referral_link_repository.register_payment(
            blogger_referral_link_id=user.blogger_referral_link_id,
            amount_rub=amount_rub,
        )
        if blogger_referral_link is None:
            return BloggerReferralPaymentResult(applied=False)

        self.logger.info(
            "Blogger referral payment registered",
            extra={
                "user_id": user_id,
                "blogger_referral_link_id": blogger_referral_link.id,
                "payment_amount": amount_rub,
                "total_paid_count": blogger_referral_link.total_paid_count,
                "total_paid_amount": blogger_referral_link.total_paid_amount,
            },
        )

        return BloggerReferralPaymentResult(
            applied=True,
            blogger_referral_link_id=blogger_referral_link.id,
            payment_amount=amount_rub,
            total_paid_count=blogger_referral_link.total_paid_count,
            total_paid_amount=blogger_referral_link.total_paid_amount,
        )

    async def create_blogger_link(
        self,
        *,
        blogger_name: str,
    ) -> BloggerReferralCreateResult:
        normalized_name = blogger_name.strip()
        if not normalized_name:
            return BloggerReferralCreateResult(created=False)

        code = await self._generate_unique_code(normalized_name)
        blogger_referral_link = await self.blogger_referral_link_repository.create(
            code=code,
            blogger_name=normalized_name,
        )
        await self.session.commit()

        self.logger.info(
            "Blogger referral link created",
            extra={
                "blogger_referral_link_id": blogger_referral_link.id,
                "blogger_name": blogger_referral_link.blogger_name,
                "blogger_code": blogger_referral_link.code,
            },
        )

        return BloggerReferralCreateResult(
            created=True,
            blogger_referral_link_id=blogger_referral_link.id,
            blogger_name=blogger_referral_link.blogger_name,
            code=blogger_referral_link.code,
        )

    async def _generate_unique_code(self, blogger_name: str) -> str:
        base_code = BLOGGER_CODE_CLEAN_PATTERN.sub("-", blogger_name.lower()).strip("-")
        if not base_code:
            base_code = "blogger"

        code = base_code[:60]
        if await self.blogger_referral_link_repository.get_by_code(code) is None:
            return code

        while True:
            suffix = secrets.token_hex(3)
            candidate = f"{base_code[:53]}-{suffix}".strip("-")
            if await self.blogger_referral_link_repository.get_by_code(candidate) is None:
                return candidate
