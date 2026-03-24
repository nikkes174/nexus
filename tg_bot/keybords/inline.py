from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tg_bot.keybords.replay import BUY_SUBSCRIPTION_TEXT


def start_keyboard():
    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text="🚀Активировать пробный период", callback_data="trial"))
    kb.add(InlineKeyboardButton(text=BUY_SUBSCRIPTION_TEXT, callback_data="buy_subscription"))
    kb.add(InlineKeyboardButton(text="🤝Пригласить друга", callback_data="invite_friend"))

    kb.adjust(1)
    return kb.as_markup()

def tariff_keyboard():

    kb = InlineKeyboardBuilder()

    kb.add(InlineKeyboardButton(text="🖤 1 месяц - 250₽", callback_data="one_month"))
    kb.add(InlineKeyboardButton(text="💫 3 месяца - 600₽", callback_data="three_month"))
    kb.add(InlineKeyboardButton(text="💎 6 месяцев - 1300₽", callback_data="six_month"))
    kb.add(InlineKeyboardButton(text="👑 12 месяцев - 2500₽", callback_data="twelveteen_month"))

    kb.adjust(1)
    return kb.as_markup()
