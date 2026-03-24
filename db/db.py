from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import DB_URL
from logging_config import get_logger

logger = get_logger(__name__)

if not DB_URL:
    raise ValueError("DB_URL is not set")

engine = create_async_engine(
    DB_URL,
    echo=False,
    pool_pre_ping=True,
    future=True,
    connect_args={"ssl": False},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db() -> None:
    logger.info("Initializing database schema")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.exec_driver_sql(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS referrals_count INTEGER NOT NULL DEFAULT 0"
        )
        await conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                id SERIAL PRIMARY KEY,
                inviter_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                inviter_telegram_id BIGINT NOT NULL,
                invited_user_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
                invited_telegram_id BIGINT NOT NULL UNIQUE,
                is_converted BOOLEAN NOT NULL DEFAULT FALSE
            )
            """
        )
        await conn.exec_driver_sql(
            "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS inviter_telegram_id BIGINT"
        )
        await conn.exec_driver_sql(
            "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS invited_telegram_id BIGINT"
        )
        await conn.exec_driver_sql(
            """
            UPDATE referrals AS r
            SET inviter_telegram_id = u.telegram_id
            FROM users AS u
            WHERE r.inviter_user_id = u.id
              AND r.inviter_telegram_id IS NULL
            """
        )
        await conn.exec_driver_sql(
            """
            UPDATE referrals AS r
            SET invited_telegram_id = u.telegram_id
            FROM users AS u
            WHERE r.invited_user_id = u.id
              AND r.invited_telegram_id IS NULL
            """
        )
        await conn.exec_driver_sql(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'referrals'
                      AND column_name = 'inviter_user_id'
                ) THEN
                    ALTER TABLE referrals ALTER COLUMN inviter_user_id DROP NOT NULL;
                END IF;
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'referrals'
                      AND column_name = 'invited_user_id'
                ) THEN
                    ALTER TABLE referrals ALTER COLUMN invited_user_id DROP NOT NULL;
                END IF;
            END$$
            """
        )
        await conn.exec_driver_sql(
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'referrals_inviter_user_id_fkey'
                ) THEN
                    ALTER TABLE referrals DROP CONSTRAINT referrals_inviter_user_id_fkey;
                END IF;
                IF EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'referrals_invited_user_id_fkey'
                ) THEN
                    ALTER TABLE referrals DROP CONSTRAINT referrals_invited_user_id_fkey;
                END IF;
            END$$
            """
        )
        await conn.exec_driver_sql(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'referrals_inviter_user_id_fkey'
                ) THEN
                    ALTER TABLE referrals
                    ADD CONSTRAINT referrals_inviter_user_id_fkey
                    FOREIGN KEY (inviter_user_id) REFERENCES users(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint WHERE conname = 'referrals_invited_user_id_fkey'
                ) THEN
                    ALTER TABLE referrals
                    ADD CONSTRAINT referrals_invited_user_id_fkey
                    FOREIGN KEY (invited_user_id) REFERENCES users(id) ON DELETE SET NULL;
                END IF;
            END$$
            """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_referrals_inviter_user_id ON referrals (inviter_user_id)"
        )
        await conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_referrals_invited_user_id ON referrals (invited_user_id)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_referrals_inviter_telegram_id ON referrals (inviter_telegram_id)"
        )
        await conn.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_referrals_invited_telegram_id ON referrals (invited_telegram_id)"
        )
    logger.info("Database schema initialized")
