from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import update

from models.users import Users
from utils.funcs.bot import get_args
from utils.funcs.db import check_exists
from utils.i18n import get as get_translation, available_languages, display_name

router = Router()


def build_lang_keyboard():
    builder = InlineKeyboardBuilder()

    for code in available_languages():
        builder.button(text=display_name(code), callback_data=f"setlang:{code}")

    builder.adjust(3)
    return builder.as_markup()


@router.message(Command("lang"))
async def lang_handler(message: Message, session):
    user = await check_exists(session, message.from_user)
    args = get_args(message)

    if not args:
        return await message.answer(
            f"""{get_translation('lang.choose', user.lang)}

{get_translation("lang.contribute", user.lang)} https://github.com/kararasenok-gd/e621monitor/blob/master/src/translations/README.md""",
            reply_markup=build_lang_keyboard(),
            disable_notification=True
        )

    code = args.strip()

    if code not in available_languages():
        return await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation("lang.not_found", user.lang)}'
        )

    await session.execute(update(Users).where(Users.user_id == message.from_user.id).values(lang=code))
    await session.commit()

    await message.answer(
        f'<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> {get_translation("lang.changed", code)} {display_name(code)}'
    )


@router.callback_query(F.data.startswith("setlang:"))
async def lang_callback(callback: CallbackQuery, session):
    await check_exists(session, callback.from_user)

    code = callback.data.split(":", 1)[1]

    if code not in available_languages():
        return await callback.answer(get_translation("lang.not_found", "en"), show_alert=True)

    await session.execute(update(Users).where(Users.user_id == callback.from_user.id).values(lang=code))
    await session.commit()

    await callback.answer(f"{get_translation('lang.changed', code)} {display_name(code)}")

    if callback.message:
        await callback.message.edit_text(
            f"{get_translation('lang.changed', code)} {display_name(code)}"
        )