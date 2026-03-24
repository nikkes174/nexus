from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

import requests
from lava_top_sdk import Currency, InvoicePaymentParamsResponse, Periodicity
from lava_top_sdk.types_custom import ClientUtm, InvoiceRequestDto

from config import (
    LAVA_API,
    LAVA_API_URL,
    LAVA_ENV,
    LAVA_OFFER_ID_12_MONTHS,
    LAVA_OFFER_ID_3_MONTHS,
    LAVA_OFFER_ID_6_MONTHS,
    LAVA_OFFER_ID_MONTHLY,
    LAVA_TIMEOUT_SEC,
)
from logging_config import get_logger


class PaymentError(Exception):
    pass


class PaymentConfigError(PaymentError):
    pass


class PaymentRequestError(PaymentError):
    pass


class TariffCode(str, Enum):
    MONTH_1 = "one_month"
    MONTH_3 = "three_month"
    MONTH_6 = "six_month"
    MONTH_12 = "twelveteen_month"


@dataclass(frozen=True)
class TariffPlan:
    code: TariffCode
    title: str
    amount_rub: int
    offer_id: str


@dataclass(frozen=True)
class InvoiceResult:
    payment_url: str
    invoice_id: str | None = None


@dataclass(frozen=True)
class RequestPlan:
    selected_tariff: TariffPlan
    request_offer_id: str
    request_periodicity: Periodicity


class PaymentService:
    logger = get_logger(__name__)

    _tariffs: dict[TariffCode, TariffPlan] = {
        TariffCode.MONTH_1: TariffPlan(
            code=TariffCode.MONTH_1,
            title="1 месяц",
            amount_rub=250,
            offer_id=LAVA_OFFER_ID_MONTHLY,
        ),
        TariffCode.MONTH_3: TariffPlan(
            code=TariffCode.MONTH_3,
            title="3 месяца",
            amount_rub=600,
            offer_id=LAVA_OFFER_ID_3_MONTHS,
        ),
        TariffCode.MONTH_6: TariffPlan(
            code=TariffCode.MONTH_6,
            title="6 месяцев",
            amount_rub=1300,
            offer_id=LAVA_OFFER_ID_6_MONTHS,
        ),
        TariffCode.MONTH_12: TariffPlan(
            code=TariffCode.MONTH_12,
            title="12 месяцев",
            amount_rub=2500,
            offer_id=LAVA_OFFER_ID_12_MONTHS,
        ),
    }

    @classmethod
    def get_tariff(cls, tariff_code: str) -> TariffPlan:
        try:
            return cls._tariffs[TariffCode(tariff_code)]
        except (ValueError, KeyError) as exc:
            raise PaymentRequestError("Неизвестный тариф для оплаты") from exc

    @classmethod
    def validate_config(cls) -> None:
        if not LAVA_API:
            raise PaymentConfigError("Не задан LAVA_API")

    @classmethod
    def _build_request_plan(cls, tariff_code: str) -> RequestPlan:
        selected_tariff = cls.get_tariff(tariff_code)
        if not selected_tariff.offer_id:
            raise PaymentConfigError(f"Не задан offer_id для тарифа {selected_tariff.code.value}")

        return RequestPlan(
            selected_tariff=selected_tariff,
            request_offer_id=selected_tariff.offer_id,
            request_periodicity=Periodicity.ONE_TIME,
        )

    @staticmethod
    def _post_invoice(payload: dict) -> InvoicePaymentParamsResponse:
        response = requests.post(
            f"{LAVA_API_URL}/api/v2/invoice",
            json=payload,
            headers={
                "X-Api-Key": LAVA_API,
                "Content-Type": "application/json",
            },
            timeout=int(LAVA_TIMEOUT_SEC),
        )

        if response.status_code >= 400:
            raise PaymentRequestError(f"Lava HTTP {response.status_code}: {response.text[:1000]}")

        return InvoicePaymentParamsResponse(**response.json())

    @classmethod
    async def create_invoice(
        cls,
        *,
        email: str,
        tariff_code: str,
        telegram_user_id: int,
        username: str | None,
    ) -> InvoiceResult:
        cls.validate_config()
        request_plan = cls._build_request_plan(tariff_code)
        tariff = request_plan.selected_tariff

        payload = InvoiceRequestDto(
            email=email,
            offerId=request_plan.request_offer_id,
            currency=Currency.RUB,
            periodicity=request_plan.request_periodicity,
            clientUtm=ClientUtm(
                utm_source="telegram_bot",
                utm_medium="telegram",
                utm_campaign=tariff.code.value,
                utm_term=username or "",
                utm_content=f"tg_user_id:{telegram_user_id}",
            ),
        ).model_dump(exclude_none=True)

        cls.logger.info(
            "Creating payment invoice",
            extra={
                "email": email,
                "telegram_user_id": telegram_user_id,
                "username": username,
                "selected_tariff_code": tariff.code.value,
                "selected_tariff_title": tariff.title,
                "selected_tariff_amount_rub": tariff.amount_rub,
                "request_offer_id": request_plan.request_offer_id,
                "request_periodicity": request_plan.request_periodicity.value,
                "lava_env": LAVA_ENV,
                "lava_api_url": LAVA_API_URL,
            },
        )

        try:
            response = await asyncio.to_thread(cls._post_invoice, payload)
        except PaymentRequestError:
            cls.logger.exception(
                "Lava invoice creation failed with raw response",
                extra={
                    "email": email,
                    "telegram_user_id": telegram_user_id,
                    "selected_tariff_code": tariff.code.value,
                    "request_offer_id": request_plan.request_offer_id,
                    "request_periodicity": request_plan.request_periodicity.value,
                },
            )
            raise
        except Exception as exc:
            cls.logger.exception(
                "Unexpected Lava invoice creation error",
                extra={
                    "email": email,
                    "telegram_user_id": telegram_user_id,
                    "selected_tariff_code": tariff.code.value,
                    "request_offer_id": request_plan.request_offer_id,
                    "request_periodicity": request_plan.request_periodicity.value,
                },
            )
            raise PaymentRequestError(
                f"Не удалось создать ссылку на оплату через Lava.top: {exc}"
            ) from exc

        if not response.paymentUrl:
            cls.logger.error(
                "Lava returned invoice without payment url",
                extra={
                    "invoice_id": response.id,
                    "selected_tariff_code": tariff.code.value,
                    "request_offer_id": request_plan.request_offer_id,
                },
            )
            raise PaymentRequestError("Lava.top не вернул ссылку на оплату")

        cls.logger.info(
            "Payment invoice created",
            extra={
                "invoice_id": response.id,
                "payment_url": response.paymentUrl,
                "telegram_user_id": telegram_user_id,
                "selected_tariff_code": tariff.code.value,
                "request_offer_id": request_plan.request_offer_id,
                "request_periodicity": request_plan.request_periodicity.value,
            },
        )

        return InvoiceResult(
            payment_url=response.paymentUrl,
            invoice_id=response.id,
        )
