from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from db.db import Base


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    referrals_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    blogger_referral_link_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("blogger_referral_links.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )

    subscription: Mapped[Optional["SubscriptionModel"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    trial: Mapped[Optional["TrialModel"]] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    links: Mapped[list["LinkModel"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    sent_referrals: Mapped[list["ReferralModel"]] = relationship(
        back_populates="inviter",
        foreign_keys="ReferralModel.inviter_user_id",
    )
    received_referral: Mapped[Optional["ReferralModel"]] = relationship(
        back_populates="invited",
        foreign_keys="ReferralModel.invited_user_id",
        uselist=False,
    )
    blogger_referral_link: Mapped[Optional["BloggerReferralLinkModel"]] = relationship(
        back_populates="users",
    )


class SubscriptionModel(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    end_subscriptions: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    subscription_period: Mapped[int] = mapped_column(Integer)

    user: Mapped[UserModel] = relationship(back_populates="subscription")


class TrialModel(Base):
    __tablename__ = "trials"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[UserModel] = relationship(back_populates="trial")


class LinkModel(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    link: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[Optional[UserModel]] = relationship(back_populates="links")


class ReferralModel(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inviter_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    inviter_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        index=True,
        nullable=False,
    )
    invited_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    invited_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    is_converted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, server_default="false")

    inviter: Mapped[Optional[UserModel]] = relationship(
        back_populates="sent_referrals",
        foreign_keys=[inviter_user_id],
    )
    invited: Mapped[Optional[UserModel]] = relationship(
        back_populates="received_referral",
        foreign_keys=[invited_user_id],
    )


class BloggerReferralLinkModel(Base):
    __tablename__ = "blogger_referral_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    blogger_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_paid_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_paid_amount: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_paid_amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    users: Mapped[list[UserModel]] = relationship(back_populates="blogger_referral_link")
