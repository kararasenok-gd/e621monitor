from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis


DEFAULT_CACHE_TTL = 300

redis_client: Redis | None = None


class RedisCacheManager:
    def __init__(self, client: Redis, default_ttl: int = DEFAULT_CACHE_TTL) -> None:
        self.client = client
        self.default_ttl = default_ttl

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        payload = json.dumps(value)
        return await self.client.set(name=key, value=payload, ex=ttl or self.default_ttl)

    async def get(self, key: str, default: Any = None) -> Any:
        value = await self.client.get(key)
        if value is None:
            return default
        return json.loads(value)

    async def require(self, key: str) -> Any:
        value = await self.get(key)
        if value is None:
            raise KeyError(f"Cache key '{key}' is not initialized")
        return value

    async def delete(self, key: str) -> int:
        return await self.client.delete(key)

    async def exists(self, key: str) -> bool:
        return bool(await self.client.exists(key))

    async def expire(self, key: str, ttl: int = DEFAULT_CACHE_TTL) -> bool:
        return await self.client.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        return await self.client.ttl(key)

    async def all(self) -> dict[str, Any]:
        """Получить все ключи и значения из кэша."""
        cursor = 0
        result = {}

        while True:
            cursor, keys = await self.client.scan(cursor, count=100)

            for key in keys:
                value = await self.client.get(key)
                if value is not None:
                    result[key] = json.loads(value)

            if cursor == 0:
                break

        return result

    async def close(self) -> None:
        await self.client.aclose()


async def init_cache(
    host: str = "localhost",
    port: int = 6379,
    username: str | None = None,
    password: str | None = None,
    db: int = 0,
    default_ttl: int = DEFAULT_CACHE_TTL,
    decode_responses: bool = True,
) -> RedisCacheManager:
    global redis_client

    redis_client = Redis(
        host=host,
        port=port,
        username=username,
        password=password,
        db=db,
        decode_responses=decode_responses,
    )
    await redis_client.ping()

    return RedisCacheManager(redis_client, default_ttl=default_ttl)


def get_cache_client() -> Redis:
    if redis_client is None:
        raise Exception("Redis client is not initialized")
    return redis_client


def get_cache_manager(default_ttl: int = DEFAULT_CACHE_TTL) -> RedisCacheManager:
    return RedisCacheManager(get_cache_client(), default_ttl=default_ttl)
