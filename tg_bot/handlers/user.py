from __future__ import annotations

import re
from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

try:
    from aiogram.types import CopyTextButton
except ImportError:
    CopyTextButton = None

from config import ADMIN_IDS
from db.crud import UserRepository
from db.db import AsyncSessionLocal
from db.service import TrialActivationService
from tg_bot.keybords.inline import start_keyboard as inline_start_keyboard, tariff_keyboard
from tg_bot.keybords.replay import (
    BUY_SUBSCRIPTION_TEXT,
    INSTRUCTION_TEXT,
    INVITE_FRIEND_TEXT,
    PROFILE_TEXT,
    SUPPORT_TEXT,
    start_keyboard as reply_start_keyboard,
)
from tg_bot.service.payment import PaymentConfigError, PaymentRequestError, PaymentService
from tg_bot.service.blogger_referral import BloggerReferralService
from tg_bot.service.referal_system import ReferralRewardService

router = Router()
START_IMAGE_PATH = Path("files/1.jpg")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
TARIFF_CALLBACKS = {"one_month", "three_month", "six_month", "twelveteen_month"}
START_PARAM_PATTERN = re.compile(
    r"^/start(?:\s+(?:ref_(?P<ref_telegram_id>\d+)|blog_(?P<blogger_code>[A-Za-z0-9_-]+)))?$"
)


class PaymentStates(StatesGroup):
    waiting_email = State()


class AdminStates(StatesGroup):
    waiting_blogger_name = State()


def is_admin(telegram_user_id: int) -> bool:
    return telegram_user_id in ADMIN_IDS


def admin_panel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Панель админа", callback_data="admin_panel"))
    return builder.as_markup()


def admin_actions_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Сгенерировать ссылку для блогера", callback_data="admin_create_blogger_link"))
    builder.adjust(1)
    return builder.as_markup()


@router.message(CommandStart())
async def start(message: types.Message) -> None:
    inviter_telegram_id = None
    blogger_code = None
    match = START_PARAM_PATTERN.fullmatch((message.text or "").strip())
    if match is not None and match.group("ref_telegram_id"):
        inviter_telegram_id = int(match.group("ref_telegram_id"))
    if match is not None and match.group("blogger_code"):
        blogger_code = match.group("blogger_code")

    async with AsyncSessionLocal() as session:
        if blogger_code is not None:
            await BloggerReferralService(session).register_blogger_start(
                blogger_code=blogger_code,
                telegram_user_id=message.from_user.id,
                username=message.from_user.username,
            )
        else:
            await ReferralRewardService(session).register_referral_start(
                inviter_telegram_id=inviter_telegram_id,
                invited_telegram_id=message.from_user.id,
                invited_username=message.from_user.username,
            )

    first_text = (
        "👋 Nexus\n\n"
        "Премиальный VPN на собственной инфраструктуре.\n\n"

        "⚙️ ИНФРАСТРУКТУРА\n"
        "Выделенные серверы в дата-центрах и каналы до 50 Гбит/с на ключевых локациях."
        "Без перегрузок, без деления ресурсов – стабильная скорость в любое время.\n\n"


        "🔐 БЕЗОПАСНОСТЬ\n"
        "• TLS-шифрование\n"
        "• Политика No-Logs\n"
        "• Double VPN\n"
        "• Работа через белые списки\n"
        "• Свободный доступ к YouTube, стримингам и онлайн-сервисам.\n\n"
        "Nexus – когда важны стабильность, скорость и приватность без компромиссов."

    )

    await message.answer_photo(
        photo=FSInputFile(START_IMAGE_PATH),
        caption=first_text,
        reply_markup=inline_start_keyboard(),
    )
    await message.answer(
        "Главное меню.",
        reply_markup=reply_start_keyboard(),
    )


async def send_tariff_menu(message: Message) -> None:
    await message.answer(
        "⚡️Выберите подписку\n"
        "❗️Перед оплатой у вас запросит вашу почту для того, чтобы пришел чек",
        reply_markup=tariff_keyboard(),
    )


async def send_invite_friend_info(message: Message, telegram_user_id: int) -> None:
    bot_info = await message.bot.get_me()
    async with AsyncSessionLocal() as session:
        result = await ReferralRewardService(session).get_personal_referral_link(
            telegram_user_id=telegram_user_id,
            bot_username=bot_info.username,
        )

    if not result.available or not result.referral_link:
        await message.answer("Реферальная ссылка доступна только при действующей подписке.")
        return

    await message.answer(
        "🎁Получайте дни к подписке за каждого преведенного друга🎁\n\n"
        "❗️Условия начиссления:\nПриглашенный человек ранее не пользовался ботом.\n"
        "Приглашенный человек приобрел подписку.\n\n"
        f"🔗Ваша личная реферальная ссылка:\n{result.referral_link}"

    )


@router.message(F.text == BUY_SUBSCRIPTION_TEXT)
async def buy_subscription_from_reply(message: Message) -> None:
    await send_tariff_menu(message)


@router.message(F.text == PROFILE_TEXT)
async def profile_info(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(message.from_user.id)

    subscription_end = "-"
    referrals_count = 0
    telegram_id = message.from_user.id

    if user is not None:
        telegram_id = user.telegram_id
        referrals_count = user.referrals_count
        if user.subscription is not None and user.subscription.end_subscriptions is not None:
            subscription_end = user.subscription.end_subscriptions.isoformat()

    await message.answer(
        "📈Личный кабинет пользователя\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔{telegram_id}\n\n"
        f"⏳ Подписка активна до : {subscription_end}\n\n"
        f"👥Приглашенных друзей: {referrals_count}"
    )


@router.message(F.text == INVITE_FRIEND_TEXT)
async def invite_friend_from_reply(message: Message) -> None:
    await send_invite_friend_info(message, message.from_user.id)


@router.message(F.text == SUPPORT_TEXT)
async def support_from_reply(message: Message) -> None:
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text=SUPPORT_TEXT, url="https://t.me/nex_supports"))
    await message.answer("https://t.me/nex_supports", reply_markup=builder.as_markup())


@router.callback_query(F.data == "admin_panel")
async def open_admin_panel(callback: CallbackQuery) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    if callback.message is not None:
        await callback.message.answer(
            "Панель администратора",
            reply_markup=admin_actions_keyboard(),
        )


@router.message(Command("admin_panel"))
async def open_admin_panel_command(message: Message) -> None:
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer(
        "Панель администратора",
        reply_markup=admin_actions_keyboard(),
    )


@router.callback_query(F.data == "admin_create_blogger_link")
async def admin_create_blogger_link(callback: CallbackQuery, state: FSMContext) -> None:
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    await callback.answer()
    await state.set_state(AdminStates.waiting_blogger_name)
    if callback.message is not None:
        await callback.message.answer("Отправьте имя блогера, для которого нужно создать ссылку.")


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription_from_inline(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await send_tariff_menu(callback.message)


@router.callback_query(F.data == "invite_friend")
async def invite_friend(callback: CallbackQuery) -> None:
    await callback.answer()
    if callback.message is not None:
        await send_invite_friend_info(callback.message, callback.from_user.id)


@router.callback_query(F.data == "trial")
async def activate_trial(callback: CallbackQuery) -> None:
    await callback.answer()

    async with AsyncSessionLocal() as session:
        result = await TrialActivationService(session).activate_trial(
            telegram_user_id=callback.from_user.id,
            username=callback.from_user.username,
        )

    if callback.message is None:
        return

    if result.activated:
        await callback.message.answer(
            "🔥Пробный период активирован.\n"
            "❗️Перейдите в раздел 🔑Инструкция по подключению🔑.\n",

        )
        return

    await callback.message.answer("⛔️Вы уже использовали пробный период⛔️")

@router.callback_query(F.data.in_(TARIFF_CALLBACKS))
async def select_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()

    tariff = PaymentService.get_tariff(callback.data)
    await state.update_data(selected_tariff=tariff.code.value)
    await state.set_state(PaymentStates.waiting_email)

    if callback.message is not None:
        await callback.message.answer(
            f"✅Вы выбрали тариф: {tariff.title} за {tariff.amount_rub}₽.\n"
            "📩Отправьте email, на который будет создана ссылка для оплаты.\n"
            "☝️Приобретая подписку вы соглашаетесь с "
            "<a href='https://telegra.ph/Polzovatelskoe-soglashenie-03-25-15'>офертой</a>\n"
            "🙏🏽Не переживайте, у нас нет авто-списаний, все платежи разовые",
            parse_mode="HTML"
        )


@router.message(PaymentStates.waiting_email)
async def create_payment_link(message: Message, state: FSMContext) -> None:
    email = (message.text or "").strip()
    if not EMAIL_PATTERN.fullmatch(email):
        await message.answer("Введите корректный email в формате name@example.com")
        return

    data = await state.get_data()
    tariff_code = data.get("selected_tariff")
    if not tariff_code:
        await state.clear()
        await message.answer("Тариф не найден. Выберите подписку заново.")
        return

    try:
        invoice = await PaymentService.create_invoice(
            email=email,
            tariff_code=tariff_code,
            telegram_user_id=message.from_user.id,
            username=message.from_user.username,
        )
    except PaymentConfigError as exc:
        await message.answer(f"Оплата временно недоступна: {exc}")
        return
    except PaymentRequestError as exc:
        await message.answer(str(exc))
        return

    await state.clear()

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Перейти к оплате", url=invoice.payment_url))

    tariff = PaymentService.get_tariff(tariff_code)
    text = (
        f"✅Ссылка на оплату для тарифа {tariff.title} готова.\n"
        f"Сумма: {tariff.amount_rub}₽"
    )

    await message.answer(text, reply_markup=builder.as_markup())


@router.message(AdminStates.waiting_blogger_name)
async def save_blogger_link(message: Message, state: FSMContext) -> None:
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    blogger_name = (message.text or "").strip()
    if not blogger_name:
        await message.answer("Имя блогера не должно быть пустым.")
        return

    bot_info = await message.bot.get_me()
    async with AsyncSessionLocal() as session:
        result = await BloggerReferralService(session).create_blogger_link(blogger_name=blogger_name)

    await state.clear()

    if not result.created or not result.code:
        await message.answer("Не удалось создать ссылку для блогера.")
        return

    blogger_link = f"https://t.me/{bot_info.username}?start=blog_{result.code}"
    await message.answer(
        f"Ссылка для блогера создана.\n\n"
        f"Блогер: {result.blogger_name}\n"
        f"Код: {result.code}\n"
        f"Ссылка: {blogger_link}"
    )


@router.message(F.text == INSTRUCTION_TEXT)
async def connect_info(message: Message) -> None:
    async with AsyncSessionLocal() as session:
        user = await UserRepository(session).get_by_telegram_id(message.from_user.id)

    user_link = None
    if user is not None and user.links:
        user_link = user.links[0].link

    connect_text = (
        "📱 ПОДКЛЮЧЕНИЕ:\n\n"
        "1. Скачайте одно из приложений\n"
        "📍IOS:\n"
        '<a href="https://apps.apple.com/app/id6476628951">Happ</a> или '
        '<a href="https://apps.apple.com/app/id6746188973">V2Raytun</a>\n'
        "📍Android:\n"
        '<a href="https://play.google.com/store/apps/details?id=in.happyplus&pcampaignid=web_share">Happ</a> или '
        '<a href="https://play.google.com/store/apps/details?id=com.v2raytun.android&pcampaignid=web_share">V2Raytun</a>\n'
        "2. Нажмите на вашу ссылку для подключения, она будет скопирована\n"
        "3. Зайдите в приложение нажмите ➕ для подключения, далее «Вставить из буфера обмена»\n\n"
        "❗️Ребята, вы сами видите, что происходит.\n"
        "Из российского App Store убрали часть приложений для доступа (Happ, v2raytun).\n"
        "☝С другим регионом они доступны. Мы уже нашли альтернативы – ссылки ниже.\n"
        '<a href="https://apps.apple.com/app/id6756558545">VPNET</a> или '
        '<a href="https://apps.apple.com/ru/app/npv-tunnel/id1629465476">V2rayu</a>\n\n'
        "Если снова удалят – пишите в поддержку: @nex_supports\n"
        "Либо меняйте регион или создавайте новый аккаунт.\n"
        "🛜<a href='https://telegra.ph/INSTRUKCIYA-PO-PODKLYUCHENIYU-03-23'>Подробное описание установки</a>"
    )

    if user_link:
        if CopyTextButton is not None:
            builder = InlineKeyboardBuilder()
            builder.add(
                InlineKeyboardButton(
                    text="Ваша ссылка",
                    copy_text=CopyTextButton(text=user_link),
                )
            )
            await message.answer(
                connect_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=builder.as_markup(),
            )
            return

        await message.answer(
            f"{connect_text}\n\nВаша ссылка:\n{user_link}",
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return

    await message.answer(
        connect_text,
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
