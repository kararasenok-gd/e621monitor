import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from PIL import Image

import httpx
from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from loguru import logger
from sqlalchemy import select, delete

from models.arts import Art
from utils.e621 import E621Client, get_post_file, get_post_tag_categories
from utils.funcs.txt import clear_hashtags
from utils.loops import loop
from utils.shared import shared_data

ART_RETENTION = timedelta(hours=shared_data.require("cfg")["watch"].getint("art_retention_hours"))

_CONVERT_TO_MP4 = {"webm"}
_CONVERT_TO_PNG = {"webp"}


def _build_markup(post, base_url: str) -> InlineKeyboardMarkup:
    post_url = f"{base_url}/posts/{post['id']}"
    post_file = get_post_file(post)
    artists = get_post_tag_categories(post).get("artist", [])
    file_url = post_file["url"] or post_url
    logger.debug(f"Building markup for post {post['id']}; file URL available: {bool(post_file['url'])}")

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

    if artists:
        logger.debug(f"Adding {len(artists)} artist buttons for post {post['id']}")
        kboard.button(
            text="Artists",
            url="https://t.me/e621monitorbot",
            icon_custom_emoji_id="5395444784611480792",
            style="primary"
        )

        _btns = 0

        for artist in artists:
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
    logger.debug(f"Built markup for post {post['id']} with row layout {adjust}")

    return kboard.as_markup()

def _build_caption(post, keep: str | None = None) -> str:
    tag_categories = get_post_tag_categories(post)
    blacklisted_tags = []
    blacklisted_tags.extend(tag_categories.get("meta", []))
    blacklisted_tags.extend(tag_categories.get("invalid", []))
    blacklisted_tags.extend(tag_categories.get("lore", []))
    logger.debug(
        f"Building caption for post {post['id']}; initially excluding {len(blacklisted_tags)} tags"
    )

    category_order = [
        ("artist", "Artists"),
        ("contributor", "Contributors"),
        ("copyright", "Copyright"),
        ("character", "Characters"),
        ("species", "Species"),
        ("general", "General"),
        ("other", "Tags"),
    ]

    def _build_tags_text(post) -> str:
        lines = []
        for field, label in category_order:
            tags = [f"#{clear_hashtags(tag)}" for tag in tag_categories.get(field, []) if tag not in blacklisted_tags]
            if tags:
                lines.append(f"<b>{label}:</b> " + ", ".join(tags))

        body = "\n".join(lines)
        return f"<tg-emoji emoji-id=\"5390854796011906616\">#️⃣</tg-emoji> Tags:\n<blockquote expandable>{body}</blockquote>"

    text = _build_tags_text(post)
    logger.debug(f"Built initial caption for post {post['id']}; length: {len(text)}")

    if len(text) > 1024:
        logger.debug(f"Caption for post {post['id']} exceeds Telegram limit; removing general tags")
        blacklisted_tags.extend(tag_categories.get("general", []))
        blacklisted_tags.extend(tag_categories.get("other", []))

        if keep:
            to_remove = keep.split()

            for tag in to_remove:
                if tag in blacklisted_tags:
                    blacklisted_tags.remove(tag)

        text = _build_tags_text(post)
        logger.debug(f"Rebuilt shortened caption for post {post['id']}; length: {len(text)}")

    return text + f"\n\n<tg-emoji emoji-id=\"5210956306952758910\">👀</tg-emoji> Rating: {'#explicit' if post['rating'] == 'e' else '#questionable' if post['rating'] == 'q' else '#safe'}"


async def _download(file: dict[str, Any]) -> Path | None:
    logger.debug(f"Starting download: md5={file['md5']}, ext={file['ext']}, size={file['size']}")

    if not file["url"]:
        logger.warning(f"Skipping file without a download URL: md5={file['md5']}")
        return None

    async with httpx.AsyncClient() as client:
        types = {
            "jpg": "photo",
            "png": "photo",
            "gif": "animation",
            "mp4": "video",
            "webm": "video",
        }

        if file["size"] >= 10*1024*1024 and types.get(file["ext"]) == "photo":
            logger.debug(f"Skipping oversized photo download: {file['size']} bytes")
            return None
        elif file["size"] >= 50*1024*1024 and types.get(file["ext"]) != "photo":
            logger.debug(f"Skipping oversized non-photo download: {file['size']} bytes")
            return None

        logger.debug(f"Downloading file from {file['url']}")
        response = await client.get(file["url"], headers={"User-Agent": shared_data.require("e621useragent")})
        response.raise_for_status()
        logger.debug(f"Downloaded {len(response.content)} bytes with status {response.status_code}")

        save_path = "data/temp/" + file["md5"] + "." + file["ext"]

        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Saving downloaded file to {save_path}")

        with open(save_path, "wb") as f:
            f.write(response.content)
            logger.debug(f"Saved downloaded file to {save_path}")
        return Path(save_path)


def _ffmpeg_memory_limiter(memory_limit_mb: int):
    """Returns a preexec_fn that caps the ffmpeg child's address space, so a
    malformed/huge input can't OOM-kill the whole bot process. POSIX only."""
    if memory_limit_mb <= 0 or sys.platform == "win32":
        logger.debug(
            f"ffmpeg memory limiter disabled; limit={memory_limit_mb} MB, platform={sys.platform}"
        )
        return None

    import resource

    def _limit():
        limit_bytes = memory_limit_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))

    return _limit


async def _run_ffmpeg(args: list[str]) -> bool:
    cfg = shared_data.require("cfg")
    threads = cfg.getint("ffmpeg", "threads", fallback=0)
    memory_limit_mb = cfg.getint("ffmpeg", "memory_limit_mb", fallback=0)

    full_args = ["-threads", str(threads), *args] if threads > 0 else args
    logger.debug(
        f"Starting ffmpeg; threads={threads}, memory_limit_mb={memory_limit_mb}, args={full_args}"
    )

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", *full_args,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
        preexec_fn=_ffmpeg_memory_limiter(memory_limit_mb),
    )
    _, stderr = await proc.communicate()
    logger.debug(f"ffmpeg finished with return code {proc.returncode}")

    if proc.returncode != 0:
        logger.warning(f"ffmpeg failed: {stderr.decode(errors='ignore')}")
        return False

    return True


async def _convert_to_mp4(path: Path) -> Path | None:
    output_path = path.with_suffix(".mp4")
    logger.debug(f"Converting {path} to MP4 at {output_path}")

    ok = await _run_ffmpeg([
        "-y", "-i", str(path),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-movflags", "faststart",
        str(output_path),
    ])

    path.unlink(missing_ok=True)
    logger.debug(f"Removed original WebM file after conversion attempt: {path}")

    if not ok:
        logger.debug(f"MP4 conversion failed; removing partial output {output_path}")
        output_path.unlink(missing_ok=True)
        return None

    logger.debug(f"MP4 conversion completed: {output_path}")
    return output_path

async def _convert_to_png(path: Path) -> Path | None:
    output_path = path.with_suffix(".png")
    logger.debug(f"Converting {path} to PNG at {output_path}")

    with Image.open(path) as img:
        img.save(output_path)

    logger.debug(f"PNG conversion completed: {output_path}")
    return output_path



async def _send_to_channel(bot: Bot, channel_id: int, file_path: Path, ext: str, caption: str, markup: InlineKeyboardMarkup):
    file = FSInputFile(file_path)
    logger.debug(
        f"Sending {file_path} to channel {channel_id}; ext={ext}, caption_length={len(caption)}"
    )

    if ext in ("jpg", "png"):
        logger.debug(f"Sending {file_path} as photo")
        await bot.send_photo(channel_id, file, caption=caption, reply_markup=markup)
    elif ext == "gif":
        logger.debug(f"Sending {file_path} as animation")
        await bot.send_animation(channel_id, file, caption=caption, reply_markup=markup)
    else:
        logger.debug(f"Sending {file_path} as video")
        await bot.send_video(channel_id, file, caption=caption, reply_markup=markup)
    logger.debug(f"Sent {file_path} to channel {channel_id}")


async def _process_file(bot: Bot, channel_id: int, file: dict[str, Any], caption: str, markup: InlineKeyboardMarkup) -> bool:
    logger.debug(f"Processing file {file['md5']} for channel {channel_id}; ext={file['ext']}")
    path_to_file = await _download(file)
    if path_to_file is None:
        logger.debug(f"File {file['md5']} was not downloaded; skipping channel send")
        return False

    send_path = path_to_file
    ext = file["ext"]

    if ext in _CONVERT_TO_MP4:
        logger.debug(f"File {file['md5']} requires MP4 conversion")
        converted = await _convert_to_mp4(path_to_file)
        if converted is None:
            logger.debug(f"MP4 conversion failed for file {file['md5']}")
            return False
        send_path = converted
        ext = "mp4"

    if ext in _CONVERT_TO_PNG:
        logger.debug(f"File {file['md5']} requires PNG conversion")
        converted = await _convert_to_png(path_to_file)
        if converted is None:
            logger.debug(f"PNG conversion failed for file {file['md5']}")
            return False
        send_path = converted
        ext = "png"

    try:
        await _send_to_channel(bot, channel_id, send_path, ext, caption, markup)
        logger.debug(f"Successfully processed file {file['md5']} for channel {channel_id}")
        return True
    finally:
        send_path.unlink(missing_ok=True)
        logger.debug(f"Removed temporary file {send_path}")


@loop(seconds=shared_data.require("cfg")["autoposting"].getint("check_every_seconds"), name="autoposting")
async def loop_handler(bot: Bot):
    try:
        cfg = shared_data.require("cfg")
        if not cfg['autoposting'].getboolean("enabled"): return

        logger.debug("Starting autoposting loop iteration")
        e621: E621Client = shared_data.require("e621client")
        session_local = shared_data.require("session_local")
        base_url = e621.endpoint.rstrip("/")
        score_limit = cfg["autoposting"].getint("score_limit")
        post_limit = cfg["autoposting"].getint("post_limit")
        blacklisted = cfg["autoposting"].get("blacklisted")
        keep = cfg["autoposting"].get("keep")
        logger.debug(
            f"Searching e621 posts; endpoint={base_url}, score_limit={score_limit}, post_limit={post_limit}"
        )

        blacklisted_formatted = ""
        for tag in blacklisted.split():
            blacklisted_formatted += f" -{tag}"

        posts = await e621.search_posts(
            "score:>=" + str(score_limit) + blacklisted_formatted,
            limit=post_limit,
        )
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

            for post in posts:
                source_id = str(post["id"])
                post_file = get_post_file(post)
                logger.debug(f"Processing post {source_id}; rating={post['rating']}, file_ext={post_file['ext']}")

                art = (await session.execute(
                    select(Art).where(Art.source_id == source_id)
                )).scalar_one_or_none()
                logger.debug(f"Database record for post {source_id} exists: {art is not None}")

                if art and art.sent_to_channel:
                    logger.debug(f"Skipping post {source_id}; already marked sent to channel")
                    continue

                channel_key = {"s": "channel_id_safe", "q": "channel_id_questionable", "e": "channel_id_explicit"}[post["rating"]]
                channel_id = cfg["autoposting"].getint(channel_key)
                logger.debug(f"Selected channel {channel_id} for post {source_id} with rating {post['rating']}")

                if channel_id == -100:
                    logger.debug(f"Skipping post {source_id}; channel for rating {post['rating']} is disabled")
                    continue

                markup = _build_markup(post, base_url)
                caption = _build_caption(post, keep)

                sent_ok = False
                try:
                    sent_ok = await _process_file(bot, channel_id, post_file, caption, markup)
                except Exception as e:
                    logger.warning(f"Failed to send post {source_id} to channel {channel_id}: {e}")
                logger.debug(f"Post {source_id} send result for channel {channel_id}: {sent_ok}")

                if art:
                    art.sent_to_channel = True
                    if sent_ok and channel_id not in art.sent_to:
                        art.sent_to = [*art.sent_to, channel_id]
                        logger.debug(f"Added channel {channel_id} to sent destinations for post {source_id}")
                    else:
                        logger.debug(f"Updated existing record for post {source_id}")
                else:
                    session.add(Art(source_id=source_id, url=post_file["url"] or "", sent_to_channel=True, sent_to=[channel_id] if sent_ok else []))
                    logger.debug(f"Created database record for post {source_id}; sent_ok={sent_ok}")

                await session.commit()
                logger.debug(f"Committed database changes for post {source_id}")
        logger.debug("Finished autoposting loop iteration")
    except:
        logger.exception("Failed to process loop...")
