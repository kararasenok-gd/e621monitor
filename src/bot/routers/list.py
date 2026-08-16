import math
from urllib.parse import quote_plus

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select, func

from models.tags import Tags
from utils.cache import get_cache_manager
from utils.funcs.bot import get_url_with_start_params
from utils.funcs.db import check_exists
from utils.i18n import get as get_translation
from utils.shared import shared_data

router = Router()
cache = get_cache_manager()


async def _render_list(tags: list[Tags], bot, lang: str, offset: int = 0) -> str:
    tags_incl = [tag for tag in tags if not tag.is_exclude]
    tags_excl = [tag for tag in tags if tag.is_exclude]

    async def render_tags(tags_group: list[Tags]) -> str:
        lines = []
        for i, tag in enumerate(tags_group):
            remove_url = await get_url_with_start_params(bot, "rem_" + tag.unique_id)
            tag_url = shared_data.require("cfg")['art_source']['base_url'] + "/posts?tags=" + quote_plus(tag.tags)
            lines.append(
                f'{i + 1 + offset}. <a href="{tag_url}">{tag.tags}</a> '
                f'<a href="{remove_url}">[{get_translation("list.delete", lang)}]</a>'
            )
        return "\n".join(lines)

    incl = await render_tags(tags_incl)
    excl = await render_tags(tags_excl)

    return ((
        f"<b>{get_translation('list.title', lang)}</b>\n"
        f"{incl}\n\n"
    ) if incl else "") + ((
        f"<b>{get_translation('list.blacklist', lang)}:</b>\n"
        f"{excl}"
    ) if excl else "")

async def _get_kboard(session, user_id: int, page: int = 1):
    allPages = math.ceil((await session.execute(select(func.count(Tags.id)).where(Tags.user_id == user_id))).scalar() / 10)

    kboard = InlineKeyboardBuilder()

    kboard.button(text="⬅️" if page > 1 else "ㅤ", callback_data="list:prev" if page > 1 else "null")
    kboard.button(text=f"{page}/{allPages}", callback_data="null")
    kboard.button(text="➡️" if allPages > 1 else "ㅤ", callback_data="list:next" if allPages > 1 else "null")

    kboard.adjust(3, repeat=True)

    return kboard

async def _get_tags(session, user_id: int, offset: int = 0):
    tags = await session.execute(select(Tags).where(Tags.user_id == user_id).limit(10).offset(offset).order_by(Tags.is_exclude.asc()))
    tags = tags.scalars().all()
    return tags


@router.message(Command("list"))
async def start_handler(message: Message, session):
    lang = (await check_exists(session, message.from_user)).lang

    tags = await _get_tags(session, message.from_user.id)
    await cache.delete(f"list:{message.from_user.id}:offset")

    if not tags:
        return await message.answer(f"""<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation('list.empty', lang)}""")



    await message.answer(
        await _render_list(tags, message.bot, lang),
        reply_markup=(await _get_kboard(session, message.from_user.id)).as_markup(),

        disable_web_page_preview=True
    )

@router.callback_query(F.data.startswith("list:"))
async def list_callback_handler(callback: CallbackQuery, session):
    lang = (await check_exists(session, callback.from_user)).lang

    act = callback.data.split(":")[1]
    cache_key = f"list:{callback.from_user.id}:offset"

    offset = await cache.get(cache_key, 0)
    offset += 10 if act == "next" else -10

    await cache.set(cache_key, offset)

    tags = await _get_tags(session, callback.from_user.id, offset)

    if not tags:
        return await callback.answer(f"""❌ {get_translation('list.empty', lang)}""")

    await callback.message.edit_text(
        await _render_list(tags, callback.bot, lang, offset),
        reply_markup=(await _get_kboard(session, callback.from_user.id, offset // 10 + 1)).as_markup(),

        disable_web_page_preview=True
    )
