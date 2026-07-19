from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from utils.funcs.db import check_exists
from utils.i18n import get as get_translation

router = Router()


@router.message(CommandStart())
async def start_handler(message: Message, session):
    lang = (await check_exists(session, message.from_user)).lang

    await message.answer(f"""<tg-emoji emoji-id="5462910521739063094">👋</tg-emoji> <b>{get_translation('start.greetings', lang)}</b>
{get_translation('start.what_bot_do', lang)}

<tg-emoji emoji-id="5397916757333654639">➕</tg-emoji> {get_translation('start.adding_tags', lang)}
<tg-emoji emoji-id="5447644880824181073">⚠️</tg-emoji> <b>{get_translation('start.warn', lang)}</b> {get_translation('start.meta_tags', lang)}

<tg-emoji emoji-id="5210956306952758910">👀</tg-emoji> {get_translation('start.help', lang)}""")