import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image

import httpx
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from e621api import E621API
from e621api.models.post import FileInfo
from loguru import logger
from sqlalchemy import select, delete

from models.arts import Art
from utils.funcs.txt import clear_hashtags
from utils.loops import loop
from utils.shared import shared_data

ART_RETENTION = timedelta(hours=12)

_CONVERT_TO_MP4 = {"webm", "gif"}
_CONVERT_TO_PNG = {"webp"}


def _build_markup(post, base_url: str) -> InlineKeyboardMarkup:
    post_url = f"{base_url}/posts/{post.id}"
    file_url = post.file.url or post_url

    kboard = InlineKeyboardBuilder()

    kboard.button(
        text="View post",
        url=post_url,
        icon_custom_emoji_id="5282843764451195532",
    )

    kboard.button(
        text="View file",
        url=file_url,
        icon_custom_emoji_id="5271604874419647061",
    )

    adjust = [2, 1]

    if post.tags.artist:
        kboard.button(
            text="Artists",
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

    return kboard.as_markup()

def _build_caption(post) -> str:
    blacklisted_tags = []
    blacklisted_tags.extend(post.tags.meta)
    blacklisted_tags.extend(post.tags.invalid)
    blacklisted_tags.extend(post.tags.lore)

    category_order = [
        ("artist", "Artists"),
        ("contributor", "Contributors"),
        ("copyright", "Copyright"),
        ("character", "Characters"),
        ("species", "Species"),
        ("general", "General"),
    ]

    def _build_tags_text(post) -> str:
        lines = []
        for field, label in category_order:
            tags = [f"#{clear_hashtags(tag)}" for tag in getattr(post.tags, field) if tag not in blacklisted_tags]
            if tags:
                lines.append(f"<b>{label}:</b> " + ", ".join(tags))

        body = "\n".join(lines)
        return f"<tg-emoji emoji-id=\"5390854796011906616\">#️⃣</tg-emoji> Tags:\n<blockquote expandable>{body}</blockquote>"

    text = _build_tags_text(post)

    if len(text) > 1024:
        blacklisted_tags.extend(post.tags.general)

        to_remove = ["male", "female", "male/male", "male/female", "female/female", "intersex", "solo", "duo", "sex", "cum", "group", "sound_warning"]

        for tag in to_remove:
            if tag in blacklisted_tags:
                blacklisted_tags.remove(tag)

        text = _build_tags_text(post)

    return text + f"\n\n<tg-emoji emoji-id=\"5210956306952758910\">👀</tg-emoji> Rating: {'#explicit' if post.rating == 'e' else '#questionable' if post.rating == 'q' else '#safe'}"


async def _download(file: FileInfo) -> Path | None:
    logger.debug("_download begin")
    async with httpx.AsyncClient() as client:
        types = {
            "jpg": "photo",
            "png": "photo",
            "gif": "animation",
            "mp4": "video",
            "webm": "video",
        }

        if file.size >= 10*1024*1024 and types.get(file.ext) == "photo":
            return None
        elif file.size >= 50*1024*1024 and types.get(file.ext) != "photo":
            return None

        logger.debug("Downloading file...")
        response = await client.get(file.url, headers={"User-Agent": shared_data.require("e621useragent")})
        response.raise_for_status()
        logger.debug("Got content")

        save_path = "data/" + file.md5 + "." + file.ext
        with open(save_path, "wb") as f:
            f.write(response.content)
            logger.debug("Saved file")
        return Path(save_path)


async def _run_ffmpeg(args: list[str]) -> bool:
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        logger.warning(f"ffmpeg failed: {stderr.decode(errors='ignore')}")
        return False

    return True


async def _convert_to_mp4(path: Path) -> Path | None:
    output_path = path.with_suffix(".mp4")

    ok = await _run_ffmpeg([
        "-y", "-i", str(path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "faststart",
        str(output_path),
    ])

    path.unlink(missing_ok=True)

    if not ok:
        output_path.unlink(missing_ok=True)
        return None

    return output_path

async def _convert_to_png(path: Path) -> Path | None:
    output_path = path.with_suffix(".png")

    with Image.open(path) as img:
        img.save(output_path)

    return output_path



async def _send_to_channel(bot: Bot, channel_id: int, file_path: Path, ext: str, caption: str, markup: InlineKeyboardMarkup):
    file = FSInputFile(file_path)

    if ext in ("jpg", "png"):
        await bot.send_photo(channel_id, file, caption=caption, reply_markup=markup)
    else:
        await bot.send_video(channel_id, file, caption=caption, reply_markup=markup)


async def _process_file(bot: Bot, channel_id: int, file: FileInfo, caption: str, markup: InlineKeyboardMarkup) -> bool:
    path_to_file = await _download(file)
    if path_to_file is None:
        return False

    send_path = path_to_file
    ext = file.ext

    if ext in _CONVERT_TO_MP4:
        converted = await _convert_to_mp4(path_to_file)
        if converted is None:
            return False
        send_path = converted
        ext = "mp4"

    if ext in _CONVERT_TO_PNG:
        converted = await _convert_to_png(path_to_file)
        if converted is None:
            return False
        send_path = converted
        ext = "png"

    try:
        await _send_to_channel(bot, channel_id, send_path, ext, caption, markup)
        return True
    finally:
        send_path.unlink(missing_ok=True)


@loop(seconds=shared_data.require("cfg")["autoposting"].getint("check_every_seconds"), name="autoposting")
async def loop_handler(bot: Bot):
    try:
        cfg = shared_data.require("cfg")
        e621: E621API = shared_data.require("e621client")
        session_local = shared_data.require("session_local")
        base_url = e621.endpoint.rstrip("/")

        posts = await e621.posts.search("score:>=" + str(cfg["autoposting"].getint("score_limit")) + " -fart -feces -foot_fetish -vore -young -urine -diaper", limit=cfg["autoposting"].getint("post_limit"))

        async with session_local() as session:
            await session.execute(
                delete(Art).where(
                    (Art.sent.is_(True) | Art.sent_to_channel.is_(True)),
                    Art.created_at < datetime.now(timezone.utc) - ART_RETENTION,
                )
            )
            await session.commit()

            for post in posts:
                source_id = str(post.id)

                art = (await session.execute(
                    select(Art).where(Art.source_id == source_id)
                )).scalar_one_or_none()

                if art and art.sent_to_channel:
                    continue

                channel_key = {"s": "channel_id_safe", "q": "channel_id_questionable", "e": "channel_id_explicit"}[post.rating]
                channel_id = cfg["autoposting"].getint(channel_key)

                if channel_id == -100:
                    continue

                markup = _build_markup(post, base_url)
                caption = _build_caption(post)

                sent_ok = False
                try:
                    sent_ok = await _process_file(bot, channel_id, post.file, caption, markup)
                except Exception as e:
                    logger.warning(f"Failed to send post {source_id} to channel {channel_id}: {e}")

                if art:
                    art.sent_to_channel = True
                    if sent_ok and channel_id not in art.sent_to:
                        art.sent_to = [*art.sent_to, channel_id]
                else:
                    session.add(Art(source_id=source_id, url=post.file.url or "", sent_to_channel=True, sent_to=[channel_id] if sent_ok else []))

                await session.commit()
    except:
        logger.exception("Failed to process loop...")