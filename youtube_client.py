import os
import requests


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def search_recipe_videos(query: str = "recipe", max_results: int = 3) -> list[dict]:
    api_key = os.environ["YOUTUBE_API_KEY"]

    params = {
        "part": "snippet",
        "q": query,
        "type": "video",
        "videoCategoryId": "26",  # Howto & Style
        "order": "viewCount",
        "maxResults": max_results,
        "key": api_key,
    }

    resp = requests.get(f"{YOUTUBE_API_BASE}/search", params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    video_ids = [item["id"]["videoId"] for item in items]
    if not video_ids:
        return []

    stats = _get_video_stats(video_ids, api_key)

    results = []
    for item in items:
        vid = item["id"]["videoId"]
        snippet = item["snippet"]
        view_count = stats.get(vid, 0)
        if view_count < 5000:
            continue
        results.append({
            "video_id": vid,
            "title": snippet["title"],
            "channel_name": snippet["channelTitle"],
            "description": snippet.get("description", ""),
            "youtube_url": f"https://www.youtube.com/watch?v={vid}",
            "view_count": view_count,
        })

    return results[:max_results]


def _get_video_stats(video_ids: list[str], api_key: str) -> dict[str, int]:
    params = {
        "part": "statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=10)
    resp.raise_for_status()
    stats = {}
    for item in resp.json().get("items", []):
        vid = item["id"]
        stats[vid] = int(item["statistics"].get("viewCount", 0))
    return stats
