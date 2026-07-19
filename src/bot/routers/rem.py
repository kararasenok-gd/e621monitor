from aiogram import Router
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message
from sqlalchemy import select, delete

from models.tags import Tags
from utils.funcs.bot import get_args
from utils.funcs.db import check_exists
from utils.i18n import get as get_translation

router = Router()


async def rem_by_unique_id(message: Message, session, unique_id: str):
    lang = (await check_exists(session, message.from_user)).lang

    tag = (await session.execute(
        select(Tags).where(Tags.unique_id == unique_id, Tags.user_id == message.from_user.id)
    )).scalar_one_or_none()

    if not tag:
        return await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation("rem.not_found", lang).capitalize()}'
        )

    await session.execute(delete(Tags).where(Tags.unique_id == unique_id))
    await session.commit()

    await message.answer(
        f'<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> '
        f'{get_translation("rem.tag", lang)} <b>{tag.tags}</b> {get_translation("rem.success", lang)}'
    )


async def rem_by_tags(message: Message, session, tags: str):
    lang = (await check_exists(session, message.from_user)).lang

    tag = (await session.execute(
        select(Tags).where(Tags.tags == tags, Tags.user_id == message.from_user.id)
    )).scalar_one_or_none()

    if not tag:
        return await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> '
            f'{get_translation("rem.tag", lang)} <b>{tags}</b> {get_translation("rem.not_found", lang)}'
        )

    await session.execute(delete(Tags).where(Tags.id == tag.id))
    await session.commit()

    await message.answer(
        f'<tg-emoji emoji-id="5206607081334906820">✅</tg-emoji> '
        f'{get_translation("rem.tag", lang)} <b>{tags}</b> {get_translation("rem.success", lang)}'
    )


@router.message(Command("rem"))
async def rem_handler(message: Message, session):
    lang = (await check_exists(session, message.from_user)).lang
    args = get_args(message)

    if not args:
        return await message.answer(
            f'<tg-emoji emoji-id="5210952531676504517">❌</tg-emoji> {get_translation("rem.missing_args", lang)}\n\n'
            f'{get_translation("rem.usage", lang)}'
        )

    await rem_by_tags(message, session, args)


@router.message(CommandStart(deep_link=True, deep_link_encoded=False))
async def rem_start(message: Message, session, command: CommandObject):
    if not command.args or not command.args.startswith("rem_"):
        return

    unique_id = command.args[4:]
    await rem_by_unique_id(message, session, unique_id)