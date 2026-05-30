import os
import random
import requests
from datetime import datetime, timezone


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

SEARCH_KEYWORDS_DB_ID = "612628cbef474ec089336969c19d66fd"
RAW_VIDEO_DB_ID = "370275ea061b804eae24ea782c1f6e62"

PRIORITY_WEIGHTS = {"1": 3, "2": 2, "3": 1}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def get_active_keywords() -> list[dict]:
    """Active 키워드 목록 반환. Priority 가중치 포함."""
    url = f"{NOTION_API_BASE}/databases/{SEARCH_KEYWORDS_DB_ID}/query"
    payload = {
        "filter": {
            "property": "Active",
            "checkbox": {"equals": True},
        }
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=10)
    resp.raise_for_status()

    keywords = []
    for page in resp.json().get("results", []):
        props = page["properties"]
        en_kw = _get_text(props, "EN keyword")
        ko_kw = _get_text(props, "KO keyword")
        keyword = en_kw or ko_kw
        if not keyword:
            continue
        priority = _get_select(props, "Priority") or "낮음"
        last_searched = _get_date(props, "date:Last searched:start")
        lang = _get_select(props, "Native language") or "en"
        keywords.append({
            "page_id": page["id"],
            "keyword": keyword,
            "priority": priority,
            "weight": PRIORITY_WEIGHTS.get(priority, 1),
            "last_searched": last_searched,
            "lang": lang,
        })

    return keywords


def pick_keyword(keywords: list[dict]) -> dict:
    """Priority 가중치 반영 랜덤 선택."""
    weights = [k["weight"] for k in keywords]
    return random.choices(keywords, weights=weights, k=1)[0]


def is_duplicate_url(youtube_url: str) -> bool:
    """Raw Video DB에 같은 URL이 이미 있는지 확인."""
    url = f"{NOTION_API_BASE}/databases/{RAW_VIDEO_DB_ID}/query"
    payload = {
        "filter": {
            "property": "URL",
            "url": {"equals": youtube_url},
        },
        "page_size": 1,
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=10)
    if resp.status_code == 400:
        # URL 속성이 아직 없으면 중복 체크 생략하고 저장 진행
        return False
    resp.raise_for_status()
    return len(resp.json().get("results", [])) > 0


def save_video(
    title: str,
    youtube_url: str,
    channel_name: str,
    source_type: str,
    description: str,
    has_subtitle: bool,
    subtitle_text: str | None,
    thumbnail_url: str,
    tags: str,
    duration_seconds: int,
    view_count: int,
    published_at: str,
    case: str,
    status: str,
) -> str:
    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    properties = {
        "Title": {"title": [{"text": {"content": title}}]},
        "Channel name": {"rich_text": [{"text": {"content": channel_name}}]},
        "Source type": {"select": {"name": source_type}},
        "Description": {"rich_text": [{"text": {"content": description[:2000]}}]},
        "Has subtitle": {"checkbox": has_subtitle},
        "Thumbnail URL": {"url": thumbnail_url or None},
        "Tags": {"rich_text": [{"text": {"content": tags[:2000]}}]},
        "Duration": {"number": duration_seconds},
        "View count": {"number": view_count},
        "Case": {"select": {"name": case}},
        "Status": {"select": {"name": status}},
        "date:Collected date:start": {"date": {"start": collected_at}},
    }

    # URL 필드
    if youtube_url:
        properties["URL"] = {"url": youtube_url}

    # Subtitle text
    if subtitle_text:
        properties["Subtitle text"] = {"rich_text": [{"text": {"content": subtitle_text[:2000]}}]}

    # Published date
    if published_at:
        properties["date:Published date:start"] = {"date": {"start": published_at}}

    payload = {
        "parent": {"database_id": RAW_VIDEO_DB_ID},
        "properties": properties,
    }

    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["id"]


def update_keyword_searched(page_id: str, current_count: int | None) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # current_count가 None이면 Notion에서 현재 값 읽어와서 누적
    if current_count is None:
        resp = requests.get(
            f"{NOTION_API_BASE}/pages/{page_id}",
            headers=_headers(),
            timeout=10,
        )
        if resp.ok:
            props = resp.json().get("properties", {})
            sc = props.get("Search count", {}).get("number")
            current_count = sc if sc is not None else 0
        else:
            current_count = 0
    new_count = current_count + 1

    payload = {
        "properties": {
            "date:Last searched:start": {"date": {"start": today}},
            "Search count": {"number": new_count},
        }
    }
    resp = requests.patch(
        f"{NOTION_API_BASE}/pages/{page_id}",
        headers=_headers(),
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()


# --- helpers ---

def _get_text(props: dict, name: str) -> str:
    field = props.get(name, {})
    rich = field.get("rich_text", [])
    return rich[0]["plain_text"] if rich else ""


def _get_select(props: dict, name: str) -> str | None:
    sel = props.get(name, {}).get("select")
    return sel["name"] if sel else None


def _get_date(props: dict, name: str) -> str | None:
    date = props.get(name, {}).get("date")
    return date["start"] if date else None
