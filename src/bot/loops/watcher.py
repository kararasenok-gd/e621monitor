from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from e621api import E621API
from loguru import logger
from sqlalchemy import select, delete

from models.arts import Art
from models.tags import Tags
from models.users import Users
from utils.i18n import get as get_translation
from utils.loops import loop
from utils.shared import shared_data

ART_RETENTION = timedelta(hours=12)


def _row_matches(row_tags: str, post_tags: set[str]) -> bool:
    return all(tag in post_tags for tag in row_tags.split())


def _matched_tags(rows: list[Tags], post_tags: set[str]) -> list[str] | None:
    include_rows = [r for r in rows if not r.is_exclude]
    exclude_rows = [r for r in rows if r.is_exclude]

    if not include_rows:
        return None

    if any(_row_matches(r.tags, post_tags) for r in exclude_rows):
        return None

    matched_rows = [r for r in include_rows if _row_matches(r.tags, post_tags)]
    if not matched_rows:
        return None

    matched_tags = []
    for row in matched_rows:
        for tag in row.tags.split():
            if tag not in matched_tags:
                matched_tags.append(tag)

    return matched_tags


def _build_message(post, matched_tags: list[str], lang: str, base_url: str) -> tuple[str, InlineKeyboardMarkup]:
    tags_str = ", ".join(matched_tags)
    post_url = f"{base_url}/posts/{post.id}"
    file_url = post.file.url or post_url

    kboard = InlineKeyboardBuilder()

    kboard.button(
        text=get_translation("new_posts.post_url", lang),
        url=post_url,
        icon_custom_emoji_id="5282843764451195532",
    )

    kboard.button(
        text=get_translation("new_posts.file_url", lang),
        url=file_url,
        icon_custom_emoji_id="5271604874419647061",
    )

    adjust = [2, 1]

    if post.tags.artist:
        kboard.button(
            text="Artists",
            callback_data="null",
            icon_custom_emoji_id="5395444784611480792",
            style="primary"
        )

        _btns = 0

        for artist in post.tags.artist:
            _btns+=1
            kboard.button(
                text=artist,
                url=f"{base_url}/posts?tags={artist}"
            )

            if _btns >= 3:
                adjust.append(3)
                _btns = 0

        if _btns > 0:
            adjust.append(_btns)

    kboard.adjust(*adjust)

    return (
        f'<tg-emoji emoji-id=\"5210956306952758910\">👀</tg-emoji> <b>{get_translation("new_posts.found", lang)}</b><a href="{post_url}">:</a> '
        f'<code>{tags_str}</code>\n\n'
    ), kboard.as_markup()


@loop(seconds=shared_data.require("watcher_loop"), name="post_watcher")
async def loop_handler(bot: Bot):
    try:
        e621: E621API = shared_data.require("e621client")
        session_local = shared_data.require("session_local")
        base_url = e621.endpoint.rstrip("/")

        posts = await e621.posts.search("", limit=shared_data.require("post_limit"))

        async with session_local() as session:
            await session.execute(
                delete(Art).where(Art.sent.is_(True), Art.created_at < datetime.now(timezone.utc) - ART_RETENTION)
            )
            await session.commit()

            users = (await session.execute(select(Users))).scalars().all()
            tags_rows = (await session.execute(select(Tags))).scalars().all()

            tags_by_user: dict[int, list[Tags]] = {}
            for row in tags_rows:
                tags_by_user.setdefault(row.user_id, []).append(row)

            for post in posts:
                source_id = str(post.id)

                art = (await session.execute(
                    select(Art).where(Art.source_id == source_id)
                )).scalar_one_or_none()

                if art and art.sent:
                    continue

                post_tags = {tag for tags in post.tags.model_dump().values() for tag in tags}

                sent_to = []
                for user in users:
                    rows = tags_by_user.get(user.user_id)
                    if not rows:
                        continue

                    matched_tags = _matched_tags(rows, post_tags)
                    if not matched_tags:
                        continue

                    try:
                        msg, markup = _build_message(post, matched_tags, user.lang, base_url)
                        await bot.send_message(
                            user.user_id,
                            msg,
                            reply_markup=markup,
                            disable_web_page_preview=False,
                        )
                        sent_to.append(user.user_id)
                    except Exception as e:
                        logger.warning(f"Failed to send post {source_id} to user {user.user_id}: {e}")

                if art:
                    art.sent = True
                    art.sent_to = sent_to
                else:
                    session.add(Art(source_id=source_id, url=post.file.url or "", sent=True, sent_to=sent_to))

                await session.commit()
    except Exception as e:
        logger.exception("Failed to process loop...")