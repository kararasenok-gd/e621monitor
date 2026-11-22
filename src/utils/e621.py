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

TAG_CATEGORY_IDS = {
    0: "general",
    1: "artist",
    2: "contributor",
    3: "copyright",
    4: "character",
    5: "species",
    6: "invalid",
    7: "meta",
    8: "lore",
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
        self._basic_auth = None
        if username or api_key:
            self._auth = {"login": username, "api_key": api_key}
            self._basic_auth = (username, api_key)
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

    async def preview_tags(self, tags: str) -> list[dict[str, Any]]:
        response = await self._client.post(
            f"{self.endpoint}/tags/preview.json",
            data={"tags": tags},
            auth=self._basic_auth,
        )
        response.raise_for_status()
        result = response.json()
        return result if isinstance(result, list) else []

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
    for tag in raw_tags:
        if isinstance(tag, str):
            categories["other"].append(tag)
            continue
        if not isinstance(tag, dict):
            continue

        name = tag.get("name", tag.get("tag"))
        category = tag.get("category", tag.get("type"))
        if isinstance(category, int):
            category = TAG_CATEGORY_IDS.get(category)
        if isinstance(name, str):
            categories[category if category in TAG_CATEGORIES else "other"].append(name)

    return categories


async def resolve_post_tag_categories(client: E621Client, post: dict[str, Any]) -> dict[str, list[str]]:
    raw_tags = post.get("tags", {})
    if isinstance(raw_tags, dict):
        return get_post_tag_categories(post)

    names = []
    for tag in raw_tags if isinstance(raw_tags, list) else []:
        name = tag if isinstance(tag, str) else tag.get("name", tag.get("tag")) if isinstance(tag, dict) else None
        if isinstance(name, str):
            names.append(name)

    if not names:
        return get_post_tag_categories({"tags": []})

    try:
        preview = await client.preview_tags(" ".join(names))
    except httpx.HTTPError:
        # Keep processing posts if the optional categorization request fails.
        return get_post_tag_categories({"tags": names})

    return get_post_tag_categories({"tags": preview or names})
