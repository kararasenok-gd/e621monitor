import random
import string

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.exc import IntegrityError

from utils.funcs.db import check_exists
from utils.funcs.bot import get_args
from utils.funcs.tag_aliases import find_alias
from utils.funcs.txt import pluralize
from utils.i18n import get as get_translation

from sqlalchemy import func, insert, select
from models.tags import Tags

router = Router()

@router.message(Command("add"))
async def start_handler(message: Message, session):
    lang = (await check_exists(session, message.from_user)).lang
    args = get_args(message)

    if not args:
        return await message.answer(f"""<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation('add.missing_args', lang)}

{get_translation('add.usage', lang)}""")

    original_tags = args.split()
    resolved_tags = []
    display_tags = []
    for tag in original_tags:
        resolved_tag = tag if tag.startswith("rating:") else await find_alias(tag)
        resolved_tags.append(resolved_tag)
        display_tags.append(f"{tag} -> {resolved_tag}" if resolved_tag != tag else tag)

    args = " ".join(resolved_tags)
    display_args = " ".join(display_tags)
    plur = pluralize(min(len(original_tags), 2), "one", "few", "many", "other")

    tags = get_translation('add.tags.'  + plur, lang)
    succ = get_translation('add.success.' + plur, lang)

    isAlreadyAdded = (await session.execute(
        select(Tags).where(
            Tags.user_id == message.from_user.id,
            func.lower(Tags.tags) == args.lower(),
        )
    )).scalars().first()

    if not isAlreadyAdded:
        await session.execute(
            insert(Tags).values(
                user_id=message.from_user.id,
                tags=args,
                unique_id="".join(random.choices(string.ascii_letters + string.digits, k=16))
            )
        )
    else:
        return await message.answer(f"""<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {tags} <b>{display_args}</b> {get_translation('add.already_exists', lang)}""")

    await session.commit()

    await message.answer(f"""<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> {tags} <b>{display_args}</b> {succ}""")
