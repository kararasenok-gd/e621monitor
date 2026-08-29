import csv
import gzip
import json
import shutil
from pathlib import Path
from loguru import logger

import httpx

from utils.cache import get_cache_manager
from utils.shared import shared_data


async def download():
    cfg = shared_data.require("cfg")
    ua = shared_data.get("e621useragent")

    url = cfg["watch"].get("aliases_url")

    archive = Path("data/temp/tag_aliases.csv.gz")
    archive.parent.mkdir(parents=True, exist_ok=True)

    csv_file = Path("data/tag_aliases.csv")

    async with httpx.AsyncClient(headers={"User-Agent": ua}) as client:
        logger.debug(f"Downloading {url}...")
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()

            with open(archive, "wb") as f:
                async for chunk in resp.aiter_bytes():
                    f.write(chunk)
                    logger.trace(f"Saved chunk. Length: {len(chunk)} bytes")

    logger.debug("Extracting aliases...")

    with gzip.open(archive, "rb") as src:
        with open(csv_file, "wb") as dst:
            shutil.copyfileobj(src, dst)

    archive.unlink(missing_ok=True)
    logger.debug("Done.")

async def load_aliases(path: str = "data/tag_aliases.csv"):
    cache = get_cache_manager()
    cfg = shared_data.require("cfg")
    aliases_refresh = cfg["watch"].getint("aliases_refresh")
    ttl = aliases_refresh * 60 * 60 if aliases_refresh > 0 else 60 * 60 * 24 * 30
    pipeline = cache.client.pipeline(transaction=False)

    with open(path, "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        logger.debug(f"Loading aliases from {path}...")

        for row in reader:
            antecedent = row["antecedent_name"]
            consequent = row["consequent_name"]

            pipeline.set(
                name=f"tag_alias:{antecedent}",
                value=json.dumps(consequent),
                ex=ttl,
            )

            logger.trace(f"Set {antecedent} to {consequent} in cache")

    await pipeline.execute()
    logger.debug("Done.")

async def find_alias(tag: str) -> str:
    cache = get_cache_manager()
    logger.debug(f"Finding {tag}...")

    alias = await cache.get(f"tag_alias:{tag}")

    if alias is not None:
        logger.debug(f"Found {tag} in cache")
        return alias

    logger.debug(f"{tag} not found.")
    return tag
