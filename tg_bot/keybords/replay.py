from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

BUY_SUBSCRIPTION_TEXT = "💳Купить Подписку"
PROFILE_TEXT = "📈Личный кабинет"
INVITE_FRIEND_TEXT = "🤝Пригласить друга"
SUPPORT_TEXT = "🆘 Поддержка"
INSTRUCTION_TEXT = "🔑 Инструкция по подключению"


def start_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=BUY_SUBSCRIPTION_TEXT),
                KeyboardButton(text=INSTRUCTION_TEXT),
            ],
            [
                KeyboardButton(text=PROFILE_TEXT),
                KeyboardButton(text=INVITE_FRIEND_TEXT),
            ],
            [
                KeyboardButton(text=SUPPORT_TEXT)
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )
