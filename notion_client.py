import os
from datetime import datetime, timezone
import requests


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def save_recipe(
    dish_name: str,
    origin_country: str,
    ingredients: list[str],
    youtube_url: str,
    view_count: int,
    channel_name: str,
) -> str:
    database_id = os.environ["NOTION_DATABASE_ID"]
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    payload = {
        "parent": {"database_id": database_id},
        "properties": {
            "dish_name": {
                "title": [{"text": {"content": dish_name}}]
            },
            "origin_country": {
                "select": {"name": origin_country}
            },
            "ingredients": {
                "rich_text": [{"text": {"content": ", ".join(ingredients)}}]
            },
            "youtube_url": {
                "url": youtube_url
            },
            "view_count": {
                "number": view_count
            },
            "collected_at": {
                "date": {"start": collected_at}
            },
            "channel_name": {
                "rich_text": [{"text": {"content": channel_name}}]
            },
        },
    }

    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]
