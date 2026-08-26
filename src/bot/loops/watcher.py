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

ART_RETENTION = timedelta(hours=shared_data.require("cfg")["watch"].getint("art_retention_hours"))


def _token_matches(token: str, post_tags: set[str], post_rating: str) -> bool:
    if token.startswith("rating:"):
        matches = post_rating == token.split(":", 1)[1][0]
        logger.debug(f"Matching rating token {token!r} against rating {post_rating!r}: {matches}")
        return matches
    matches = token in post_tags
    logger.debug(f"Matching tag token {token!r} against post tags: {matches}")
    return matches


def _row_matches(row_tags: str, post_tags: set[str], post_rating: str) -> bool:
    logger.debug(f"Matching tag row {row_tags!r} against post rating {post_rating!r}")
    for token in row_tags.split():
        if token.startswith("-"):
            if _token_matches(token[1:], post_tags, post_rating):
                logger.debug(f"Tag row {row_tags!r} rejected by excluded token {token!r}")
                return False
        elif not _token_matches(token, post_tags, post_rating):
            logger.debug(f"Tag row {row_tags!r} rejected; required token {token!r} is absent")
            return False
    logger.debug(f"Tag row {row_tags!r} matches")
    return True


def _matched_tags(rows: list[Tags], post_tags: set[str], post_rating: str) -> list[str] | None:
    include_rows = [r for r in rows if not r.is_exclude]
    exclude_rows = [r for r in rows if r.is_exclude]
    logger.debug(
        f"Evaluating {len(rows)} tag rows; include={len(include_rows)}, exclude={len(exclude_rows)}, "
        f"post_tags={len(post_tags)}, rating={post_rating}"
    )

    if not include_rows:
        logger.debug("No include rows configured; post does not match")
        return None

    if any(_row_matches(r.tags, post_tags, post_rating) for r in exclude_rows):
        logger.debug("Post matched an exclude row; post does not match")
        return None

    matched_rows = [r for r in include_rows if _row_matches(r.tags, post_tags, post_rating)]
    if not matched_rows:
        logger.debug("Post did not match any include row")
        return None

    matched_tags = []
    for row in matched_rows:
        for tag in row.tags.split():
            if tag.startswith("-"):
                continue
            if tag not in matched_tags:
                matched_tags.append(tag)

    logger.debug(f"Post matched {len(matched_rows)} include rows with tags {matched_tags}")
    return matched_tags


def _build_message(post, matched_tags: list[str], lang: str, base_url: str) -> tuple[str, InlineKeyboardMarkup]:
    tags_str = ", ".join(matched_tags)
    post_url = f"{base_url}/posts/{post.id}"
    file_url = post.file.url or post_url
    logger.debug(
        f"Building notification for post {post.id}; lang={lang}, matched_tags={matched_tags}, "
        f"file URL available: {bool(post.file.url)}"
    )

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
        logger.debug(f"Adding {len(post.tags.artist)} artist buttons for post {post.id}")
        kboard.button(
            text=get_translation("new_posts.artist", lang),
            url="https://t.me/e621monitorbot",
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
    logger.debug(f"Built notification markup for post {post.id} with row layout {adjust}")

    return (
        f'<tg-emoji emoji-id=\"5210956306952758910\">👀</tg-emoji> <b>{get_translation("new_posts.found", lang)}</b><a href="{post_url}">:</a> '
        f'<code>{tags_str}</code>\n\n'
    ), kboard.as_markup()


@loop(seconds=shared_data.require("cfg")["watch"].getint("check_every_seconds"), name="post_watcher")
async def loop_handler(bot: Bot):
    try:
        logger.debug("Starting post watcher loop iteration")
        cfg = shared_data.require("cfg")
        e621: E621API = shared_data.require("e621client")
        session_local = shared_data.require("session_local")
        base_url = e621.endpoint.rstrip("/")
        post_limit = cfg["autoposting"].getint("post_limit")
        logger.debug(f"Searching e621 posts; endpoint={base_url}, post_limit={post_limit}")

        posts = await e621.posts.search("", limit=post_limit)
        logger.debug(f"e621 search returned {len(posts)} posts")

        async with session_local() as session:
            logger.debug(f"Removing sent art older than {ART_RETENTION}")
            await session.execute(
                delete(Art).where(
                    (Art.sent.is_(True) | Art.sent_to_channel.is_(True)),
                    Art.created_at < datetime.now(timezone.utc) - ART_RETENTION,
                )
            )
            await session.commit()
            logger.debug("Committed expired-art cleanup")

            users = (await session.execute(select(Users))).scalars().all()
            tags_rows = (await session.execute(select(Tags))).scalars().all()
            logger.debug(f"Loaded {len(users)} users and {len(tags_rows)} tag rows")

            tags_by_user: dict[int, list[Tags]] = {}
            for row in tags_rows:
                tags_by_user.setdefault(row.user_id, []).append(row)
            logger.debug(f"Grouped tag rows for {len(tags_by_user)} users")

            for post in posts:
                source_id = str(post.id)
                logger.debug(f"Processing post {source_id}; rating={post.rating}, file_ext={post.file.ext}")

                art = (await session.execute(
                    select(Art).where(Art.source_id == source_id)
                )).scalar_one_or_none()
                logger.debug(f"Database record for post {source_id} exists: {art is not None}")

                if art and art.sent:
                    logger.debug(f"Skipping post {source_id}; already marked as sent")
                    continue

                post_tags = {tag for tags in post.tags.model_dump().values() for tag in tags}
                logger.debug(f"Collected {len(post_tags)} unique tags for post {source_id}")

                sent_to = []
                for user in users:
                    rows = tags_by_user.get(user.user_id)
                    if not rows:
                        logger.debug(f"Skipping user {user.user_id}; no tag rows configured")
                        continue

                    logger.debug(f"Evaluating post {source_id} for user {user.user_id} with {len(rows)} tag rows")
                    matched_tags = _matched_tags(rows, post_tags, post.rating)
                    if not matched_tags:
                        logger.debug(f"Post {source_id} does not match subscriptions for user {user.user_id}")
                        continue

                    try:
                        msg, markup = _build_message(post, matched_tags, user.lang, base_url)
                        logger.debug(
                            f"Sending post {source_id} notification to user {user.user_id}; "
                            f"message_length={len(msg)}"
                        )
                        await bot.send_message(
                            user.user_id,
                            msg,
                            reply_markup=markup,
                            disable_web_page_preview=False,
                        )
                        sent_to.append(user.user_id)
                        logger.debug(f"Sent post {source_id} notification to user {user.user_id}")
                    except Exception as e:
                        logger.warning(f"Failed to send post {source_id} to user {user.user_id}: {e}")

                if art:
                    art.sent = True
                    art.sent_to = sent_to
                    logger.debug(f"Updated existing record for post {source_id}; sent_to={sent_to}")
                else:
                    session.add(Art(source_id=source_id, url=post.file.url or "", sent=True, sent_to=sent_to))
                    logger.debug(f"Created database record for post {source_id}; sent_to={sent_to}")

                await session.commit()
                logger.debug(f"Committed database changes for post {source_id}")
        logger.debug("Finished post watcher loop iteration")
    except:
        logger.exception("Failed to process loop...")
