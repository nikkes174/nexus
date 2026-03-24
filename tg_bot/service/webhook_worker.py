from __future__ import annotations

import asyncio
from dataclasses import dataclass

from aiogram import Bot

from db.db import AsyncSessionLocal
from logging_config import get_logger
from tg_bot.service.payment import PaymentConfigError
from tg_bot.service.webhook import LavaWebhookService, WebhookError, WebhookProcessResult


@dataclass(frozen=True)
class WebhookTask:
    payload: str
    signature: str | None


class LavaWebhookWorkerService:
    def __init__(
        self,
        *,
        bot: Bot,
        worker_count: int,
        queue_maxsize: int,
    ) -> None:
        self.bot = bot
        self.logger = get_logger(__name__)
        self.queue: asyncio.Queue[WebhookTask] = asyncio.Queue(maxsize=max(1, queue_maxsize))
        self.worker_count = max(1, worker_count)
        self._worker_tasks: list[asyncio.Task] = []

    async def start(self) -> None:
        if self._worker_tasks:
            return

        for index in range(self.worker_count):
            task = asyncio.create_task(
                self._worker_loop(index + 1),
                name=f"lava-webhook-worker-{index + 1}",
            )
            self._worker_tasks.append(task)

        self.logger.info(
            "Webhook workers started",
            extra={
                "worker_count": self.worker_count,
                "queue_maxsize": self.queue.maxsize,
            },
        )

    async def stop(self) -> None:
        for task in self._worker_tasks:
            task.cancel()

        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._worker_tasks.clear()
        self.logger.info("Webhook workers stopped")

    def enqueue(self, *, payload: str, signature: str | None) -> bool:
        try:
            self.queue.put_nowait(WebhookTask(payload=payload, signature=signature))
        except asyncio.QueueFull:
            self.logger.error(
                "Webhook queue is full",
                extra={
                    "queue_size": self.queue.qsize(),
                    "queue_maxsize": self.queue.maxsize,
                },
            )
            return False

        self.logger.info(
            "Webhook accepted",
            extra={
                "queue_size": self.queue.qsize(),
                "queue_maxsize": self.queue.maxsize,
            },
        )
        return True

    async def _worker_loop(self, worker_id: int) -> None:
        while True:
            task = await self.queue.get()
            try:
                await self._process_task(task, worker_id)
            finally:
                self.queue.task_done()

    async def _process_task(self, task: WebhookTask, worker_id: int) -> None:
        async with AsyncSessionLocal() as session:
            try:
                result = await LavaWebhookService.process_webhook(
                    payload=task.payload,
                    signature=task.signature,
                    session=session,
                )
            except PaymentConfigError as exc:
                await session.rollback()
                self.logger.error(
                    "Webhook config error",
                    extra={"worker_id": worker_id, "error": str(exc)},
                )
                return
            except WebhookError as exc:
                await session.rollback()
                self.logger.warning(
                    "Webhook rejected",
                    extra={"worker_id": worker_id, "error": str(exc)},
                )
                return
            except Exception:
                await session.rollback()
                self.logger.exception(
                    "Webhook failed",
                    extra={"worker_id": worker_id},
                )
                return

        await self._handle_result(result, worker_id)

    async def _handle_result(self, result: WebhookProcessResult, worker_id: int) -> None:
        if result.status == "processed":
            self.logger.info(
                "Webhook processed",
                extra={
                    "worker_id": worker_id,
                    "contract_id": result.contract_id,
                    "user_id": result.user_id,
                },
            )
        else:
            self.logger.info(
                "Webhook ignored",
                extra={"worker_id": worker_id, "contract_id": result.contract_id},
            )

        if result.status == "processed" and result.telegram_user_id:
            if result.subscription_extended:
                message_text = (
                    "🥳 Ваша подписка продлена.\n"
                    "️️❗️ Ключ для подключения остается прежней."
                )
            else:
                message_text = (
                    "✅Оплата прошла успешно.\n"
                    "❗️Перейдите в раздел 🔑Инструкция по подключению🔑.\n"

                )

            try:
                await self.bot.send_message(chat_id=result.telegram_user_id, text=message_text)
                self.logger.info(
                    "Payment message sent",
                    extra={
                        "worker_id": worker_id,
                        "telegram_user_id": result.telegram_user_id,
                    },
                )
            except Exception:
                self.logger.exception(
                    "Payment message failed",
                    extra={"worker_id": worker_id},
                )

        if result.status == "processed" and result.referral_inviter_telegram_id and result.referral_bonus_days:
            try:
                await self.bot.send_message(
                    chat_id=result.referral_inviter_telegram_id,
                    text=(
                        "По вашей ссылке пришел новый пользователь. "
                        f"Вам начислено {result.referral_bonus_days} дней."
                    ),
                )
                self.logger.info(
                    "Referral message sent",
                    extra={
                        "worker_id": worker_id,
                        "telegram_user_id": result.referral_inviter_telegram_id,
                    },
                )
            except Exception:
                self.logger.exception(
                    "Referral message failed",
                    extra={"worker_id": worker_id},
                )
