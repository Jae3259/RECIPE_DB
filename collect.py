import logging
import re
import sys
from datetime import datetime
from pathlib import Path

import notion_client
import youtube_client


LOG_DIR = Path("logs")
DAILY_LIMIT = 3
YOUTUBE_SEARCH_POOL = 10  # 키워드당 검색 결과 최대 수

_RECIPE_SUFFIXES_EN = {"recipe", "how to make", "cooking", "homemade"}
_RECIPE_SUFFIXES_KO = {"레시피", "만들기", "요리"}


def _normalize_keyword(keyword: str, lang: str) -> str:
    kw_lower = keyword.lower()
    if lang == "ko":
        if not any(s in kw_lower for s in _RECIPE_SUFFIXES_KO):
            return keyword + " 레시피"
    else:
        if not any(s in kw_lower for s in _RECIPE_SUFFIXES_EN):
            return keyword + " recipe"
    return keyword

INGREDIENT_UNIT_PATTERN = re.compile(
    r"\b\d+[\s./-]*(cups?|tbsp|tsp|tablespoons?|teaspoons?|g|kg|ml|l|oz|lb|lbs|cloves?|slices?|pieces?)\b",
    re.IGNORECASE,
)


def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    log_file = LOG_DIR / f"run_{today}.log"

    logger = logging.getLogger("collect")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    return logger


def classify_case(duration_seconds: int, description: str, has_subtitle: bool) -> tuple[str, str]:
    """(case, status) 반환"""
    if duration_seconds <= 60:
        return "D (Skip)", "제외"
    if _has_ingredient_list(description):
        return "A (Auto)", "자동처리중"
    if has_subtitle:
        return "B (Semi)", "자막대기"
    return "C (Manual)", "수동대기"


def _has_ingredient_list(description: str) -> bool:
    if not description:
        return False
    matches = INGREDIENT_UNIT_PATTERN.findall(description)
    return len(matches) >= 3


def run():
    logger = setup_logger()
    logger.info("=== 수집 시작 ===")

    # 1. 키워드 목록 가져오기
    try:
        keywords = notion_client.get_active_keywords()
    except Exception as e:
        logger.error(f"Notion 키워드 조회 실패: {e}")
        sys.exit(1)

    if not keywords:
        logger.warning("Active 키워드 없음. 종료.")
        return

    # 2. 키워드 선택 — 0순위 있으면 우선, 없으면 가중치 랜덤
    zero_priority = [k for k in keywords if k["priority"] == "0순위"]
    if zero_priority:
        import random as _random
        selected = _random.choice(zero_priority)
        logger.info(f"0순위 키워드 {len(zero_priority)}개 중 선택")
    else:
        selected = notion_client.pick_keyword(keywords)
    raw_kw = selected["keyword"]
    search_kw = _normalize_keyword(raw_kw, selected.get("lang", "en"))
    logger.info(f"선택된 키워드: '{raw_kw}' → 검색어: '{search_kw}' (Priority: {selected['priority']})")

    # 3. YouTube 검색
    try:
        videos = youtube_client.search_recipe_videos(
            keyword=search_kw,
            max_results=YOUTUBE_SEARCH_POOL,
        )
    except Exception as e:
        logger.error(f"YouTube API 오류 (quota 초과 또는 키 문제): {e}")
        logger.info("내일 재시도 예정.")
        sys.exit(0)

    if not videos:
        logger.warning("검색 결과 없음.")
        return

    logger.info(f"YouTube 검색 결과: {len(videos)}개")

    # 4. 영상별 처리
    saved_count = 0
    for video in videos:
        if saved_count >= DAILY_LIMIT:
            break

        vid = video["video_id"]
        url = video["youtube_url"]

        # 중복 체크
        try:
            if notion_client.is_duplicate_url(url):
                logger.info(f"중복 skip: {url}")
                continue
        except Exception as e:
            logger.error(f"중복 체크 실패 ({vid}): {e}")
            continue

        case, status = classify_case(
            video["duration_seconds"],
            video["description"],
            video["has_subtitle"],
        )
        logger.info(f"[{case}] {video['title'][:60]} ({vid})")

        try:
            notion_client.save_video(
                title=video["title"],
                youtube_url=url,
                channel_name=video["channel_name"],
                source_type="Keyword",
                description=video["description"],
                has_subtitle=video["has_subtitle"],
                subtitle_text=video["subtitle_text"],
                thumbnail_url=video["thumbnail_url"],
                tags=video["tags"],
                duration_seconds=video["duration_seconds"],
                view_count=video["view_count"],
                published_at=video["published_at"],
                case=case,
                status=status,
            )
            logger.info(f"Notion 저장 완료: {video['title'][:60]}")
            saved_count += 1
        except Exception as e:
            logger.error(f"Notion 저장 실패 ({vid}): {e}")

    # 5. 키워드 사용 기록 업데이트
    try:
        current_count = None  # Search count는 Notion에서 직접 읽지 않고 누적만 함
        notion_client.update_keyword_searched(selected["page_id"], current_count)
        logger.info(f"키워드 Last searched 업데이트 완료: {selected['keyword']}")
    except Exception as e:
        logger.error(f"키워드 업데이트 실패: {e}")

    logger.info(f"=== 수집 완료: {saved_count}/{DAILY_LIMIT} 저장 ===")


if __name__ == "__main__":
    run()
