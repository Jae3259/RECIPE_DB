import os
import re
import requests
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled


YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


def search_recipe_videos(keyword: str, max_results: int = 10) -> list[dict]:
    api_key = os.environ["YOUTUBE_API_KEY"]

    params = {
        "part": "snippet",
        "q": keyword,
        "type": "video",
        "order": "relevance",
        "maxResults": max_results,
        "key": api_key,
    }

    resp = requests.get(f"{YOUTUBE_API_BASE}/search", params=params, timeout=10)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    video_ids = [item["id"]["videoId"] for item in items]
    if not video_ids:
        return []

    details = _get_video_details(video_ids, api_key)

    results = []
    for vid, data in details.items():
        subtitle_info = _get_subtitle_info(vid)
        results.append({
            "video_id": vid,
            "title": data["title"],
            "channel_name": data["channel_name"],
            "description": data["description"],
            "youtube_url": f"https://www.youtube.com/watch?v={vid}",
            "view_count": data["view_count"],
            "thumbnail_url": data["thumbnail_url"],
            "tags": data["tags"],
            "duration_seconds": data["duration_seconds"],
            "published_at": data["published_at"],
            "has_subtitle": subtitle_info["has_subtitle"],
            "subtitle_text": subtitle_info["subtitle_text"],
        })

    return results


def _get_video_details(video_ids: list[str], api_key: str) -> dict[str, dict]:
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    resp = requests.get(f"{YOUTUBE_API_BASE}/videos", params=params, timeout=10)
    resp.raise_for_status()

    details = {}
    for item in resp.json().get("items", []):
        vid = item["id"]
        snippet = item["snippet"]
        stats = item.get("statistics", {})
        content = item.get("contentDetails", {})

        thumbnail = (
            snippet.get("thumbnails", {}).get("maxres")
            or snippet.get("thumbnails", {}).get("high")
            or snippet.get("thumbnails", {}).get("default")
            or {}
        )

        details[vid] = {
            "title": snippet.get("title", ""),
            "channel_name": snippet.get("channelTitle", ""),
            "description": snippet.get("description", ""),
            "published_at": snippet.get("publishedAt", ""),
            "thumbnail_url": thumbnail.get("url", ""),
            "tags": ", ".join(snippet.get("tags", [])),
            "view_count": int(stats.get("viewCount", 0)),
            "duration_seconds": _parse_duration(content.get("duration", "PT0S")),
        }

    return details


def _parse_duration(iso_duration: str) -> int:
    """ISO 8601 duration (PT1H2M3S) -> seconds"""
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match:
        return 0
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _get_subtitle_info(video_id: str) -> dict:
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        try:
            transcript = transcript_list.find_manually_created_transcript()
        except NoTranscriptFound:
            transcript = transcript_list.find_generated_transcript(
                [t.language_code for t in transcript_list]
            )
        text = " ".join(entry["text"] for entry in transcript.fetch())
        return {"has_subtitle": True, "subtitle_text": text}
    except (NoTranscriptFound, TranscriptsDisabled, Exception):
        return {"has_subtitle": False, "subtitle_text": None}
