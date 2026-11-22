import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from loguru import logger

from bot.middlewares.db import DBSessionMiddleware
from utils.cache import init_cache
from utils.database import init_db, init_models
from utils.e621 import E621Client
from utils.loader import load_routers, load_loops
from utils.shared import shared_data
from utils.funcs.tag_aliases import download as download_aliases, load_aliases


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


def _setup_logging(log_level: str = "INFO"):
    logging.basicConfig(handlers=[_InterceptHandler()], level=0, force=True)
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=log_level,
        colorize=True,
    )

working_loops = []

current_version = open("VERSION").read().strip()

@logger.catch()
async def main():
    os.makedirs("data", exist_ok=True)

    engine, SessionLocal, cfg = init_db()
    _setup_logging(log_level=cfg.get("bot", "log_level", fallback="INFO"))

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
        logger.error("Can't initialize cache!")
        raise e

    username = cfg["art_source"]["username"]
    user_agent = f"e621monitor/{current_version} (by {username or 'unknown_user'} on e621)"
    e621_client = E621Client(
        username=username,
        api_key=cfg["art_source"]["api_key"],
        endpoint=cfg["art_source"]["base_url"],
        user_agent=user_agent,
    )

    shared_data.set("cfg", cfg)
    shared_data.set("session_local", SessionLocal)
    shared_data.set("e621client", e621_client)
    shared_data.set("e621useragent", user_agent)

    bot = Bot(
        token=cfg["bot"]["token"],
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    try:
        dp.update.middleware(DBSessionMiddleware(SessionLocal))

        if cfg['watch'].getboolean("load_aliases"):
            logger.info("Loading aliases...")
            await download_aliases()
            await load_aliases()

        routers = load_routers("bot/routers")
        for router in routers:
            dp.include_router(router)

        loops = load_loops("bot/loops")
        for loop in loops:
            await loop.start(bot)
            working_loops.append(loop)

        logger.info("Starting bot...")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        logger.info("Stopping background loops...")
        for loop in working_loops:
            await loop.stop()
        working_loops.clear()

        async def close_with_timeout(name, close, timeout: float = 10.0):
            try:
                await asyncio.wait_for(close(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning(f"Timed out while closing {name}; continuing shutdown")
            except Exception:
                logger.exception(f"Failed to close {name}; continuing shutdown")

        await close_with_timeout("Telegram session", bot.session.close)
        if cache is not None:
            await close_with_timeout("Redis", cache.close)
        await close_with_timeout("database engine", engine.dispose)
        await close_with_timeout("e621 HTTP client", e621_client.aclose)
        logger.info("Shutdown complete")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down. Bye!")
