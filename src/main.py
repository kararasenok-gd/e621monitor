import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from e621api import E621API
from loguru import logger

from bot.middlewares.db import DBSessionMiddleware
from utils.cache import init_cache
from utils.database import init_db, init_models
from utils.loader import load_routers, load_loops
from utils.shared import shared_data


class _InterceptHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1
        logger.opt(depth=depth, exception=record.exc_info).log(level, record.getMessage())


def _setup_logging(debug: bool = False):
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level="DEBUG" if debug else "INFO",
        colorize=True,
    )

working_loops = []


async def main():
    os.makedirs("data", exist_ok=True)

    engine, SessionLocal, cfg = init_db()
    _setup_logging(debug=cfg.getboolean("bot", "debug", fallback=False))

    logger.info("Initializing...")
    await init_models(engine)

    redis_cfg = cfg["redis"]
    try:
        cache = await init_cache(
            host=redis_cfg.get("host", "localhost"),
            port=redis_cfg.getint("port", 6379),
            username=redis_cfg.get("username") or None,
            password=redis_cfg.get("pass") or None,
            db=redis_cfg.getint("db", 0),
        )
        logger.info("Redis connected.")
    except Exception as e:
        cache = None
        logger.warning(f"Redis unavailable, cache disabled: {e}")

    shared_data.set("session_local", SessionLocal)
    shared_data.set("e621client", E621API(
        username=cfg["art_source"]["username"],
        key=cfg["art_source"]["api_key"],
        endpoint=cfg['art_source']['base_url']
    ))
    shared_data.set("watcher_loop", cfg["watch"].getint("check_every_seconds"))
    shared_data.set("post_limit", cfg['autoposting'].getint('post_limit'))
    shared_data.set("autoposting_score_limit", cfg['autoposting'].getint('score_limit'))
    shared_data.set("autoposting_channels", (cfg['autoposting'].getint('channel_id_safe'), cfg['autoposting'].getint('channel_id_questionable'), cfg['autoposting'].getint('channel_id_explicit')))

    bot = Bot(
        token=cfg["bot"]["token"],
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    dp.update.middleware(DBSessionMiddleware(SessionLocal))

    routers = load_routers("bot/routers")
    for router in routers:
        dp.include_router(router)

    loops = load_loops("bot/loops")
    for loop in loops:
        if loop.name == "autoposting" and not cfg['autoposting'].getboolean("enabled"): continue
        await loop.start(bot)
        working_loops.append(loop)

    logger.info("Starting bot...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        if cache is not None:
            await cache.close()
        await engine.dispose()

        if working_loops:
            for loop in working_loops:
                await loop.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down. Bye!")