from typing import Any

import httpx


class E621Client:
    def __init__(
        self,
        username: str,
        api_key: str,
        endpoint: str,
        user_agent: str,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self._auth = {}
        if username or api_key:
            self._auth = {"login": username, "api_key": api_key}
        self._client = httpx.AsyncClient(
            headers={"User-Agent": user_agent},
            timeout=30.0,
        )

    async def search_posts(self, tags: str, limit: int) -> list[dict[str, Any]]:
        response = await self._client.get(
            f"{self.endpoint}/posts.json",
            params={"tags": tags, "limit": limit, **self._auth},
        )
        response.raise_for_status()
        return response.json()

    async def aclose(self) -> None:
        await self._client.aclose()
