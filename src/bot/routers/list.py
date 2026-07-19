from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import select

from models.tags import Tags
from utils.funcs.bot import get_url_with_start_params
from utils.funcs.db import check_exists
from utils.i18n import get as get_translation

router = Router()


@router.message(Command("list"))
async def start_handler(message: Message, session):
    lang = (await check_exists(session, message.from_user)).lang

    tags = await session.execute(select(Tags).where(Tags.user_id == message.from_user.id))
    tags = tags.scalars().all()

    if not tags:
        return await message.answer(f"""<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation('list.empty', lang)}""")

    tagsIncl = [[tag.tags, tag.unique_id] for tag in tags if not tag.is_exclude]
    tagsExcl = [[tag.tags, tag.unique_id] for tag in tags if tag.is_exclude]

    linesIncl = []
    linesExcl = []

    for i, tag in enumerate(tagsIncl):
        linesIncl.append(f"{i+1}. {tag[0]} <a href=\"{await get_url_with_start_params(message.bot, 'rem_' + tag[1])}\">[{get_translation('list.delete', lang)}]</a>")

    for i, tag in enumerate(tagsExcl):
        linesExcl.append(f"{i+1}. {tag[0]} <a href=\"{await get_url_with_start_params(message.bot, 'rem_' + tag[1])}\">[{get_translation('list.delete', lang)}]</a>")

    incl = "\n".join(linesIncl)
    excl = "\n".join(linesExcl)

    await message.answer(
        f"<b>{get_translation('list.title', lang)}</b>\n"
        f"{incl}\n\n"
        f"<b>{get_translation('list.blacklist', lang)}:</b>\n"
        f"{excl}",

        disable_web_page_preview=True
    )