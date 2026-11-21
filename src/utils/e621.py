from typing import Any

import httpx


TAG_CATEGORIES = {
    "artist",
    "contributor",
    "copyright",
    "character",
    "species",
    "invalid",
    "meta",
    "lore",
    "general",
}


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


def get_post_file(post: dict[str, Any]) -> dict[str, Any]:
    if "files" not in post:
        return post["file"]

    return {
        **post["files"]["meta"],
        "url": (post["files"].get("original") or {}).get("url"),
    }


def get_post_tag_categories(post: dict[str, Any]) -> dict[str, list[str]]:
    raw_tags = post["tags"]
    if isinstance(raw_tags, dict):
        return raw_tags

    categories = {category: [] for category in TAG_CATEGORIES}
    categories["other"] = []
    category_ids = {
        0: "general",
        1: "artist",
        3: "copyright",
        4: "character",
        5: "species",
        6: "invalid",
        7: "meta",
        8: "lore",
        9: "contributor",
    }

    for tag in raw_tags:
        if isinstance(tag, str):
            categories["other"].append(tag)
            continue
        if not isinstance(tag, dict):
            continue

        name = tag.get("name", tag.get("tag"))
        category = tag.get("category", tag.get("type"))
        if isinstance(category, int):
            category = category_ids.get(category)
        if isinstance(name, str):
            categories[category if category in TAG_CATEGORIES else "other"].append(name)

    return categories
