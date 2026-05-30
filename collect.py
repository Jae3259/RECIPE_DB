import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import youtube_client
import claude_client
import notion_client


LOG_DIR = Path("logs")
DATA_DIR = Path("data/recipes")
DAILY_LIMIT = 3
SEARCH_QUERY = "cooking recipe"


def setup_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

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


def run():
    logger = setup_logger()
    logger.info("=== 수집 시작 ===")

    try:
        videos = youtube_client.search_recipe_videos(
            query=SEARCH_QUERY, max_results=DAILY_LIMIT
        )
    except Exception as e:
        logger.error(f"YouTube API 오류 — quota 초과 또는 키 문제: {e}")
        logger.info("내일 재시도 예정. 파이프라인 종료.")
        sys.exit(0)

    if not videos:
        logger.warning("조건에 맞는 영상 없음 (조회수 5천↑). 종료.")
        return

    logger.info(f"수집 대상 영상 {len(videos)}개")

    success = 0
    for video in videos:
        vid = video["video_id"]
        logger.info(f"처리 중: {video['title']} ({vid})")

        try:
            recipe = claude_client.extract_recipe(
                title=video["title"],
                channel=video["channel_name"],
                description=video["description"],
            )
        except Exception as e:
            logger.error(f"Claude API 오류 ({vid}): {e}")
            continue

        # 로컬 백업
        backup_path = DATA_DIR / f"{vid}.json"
        backup_path.write_text(
            json.dumps({**video, **recipe}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        try:
            page_id = notion_client.save_recipe(
                dish_name=recipe.get("dish_name", "unknown"),
                origin_country=recipe.get("origin_country", "unknown"),
                ingredients=recipe.get("ingredients", []),
                youtube_url=video["youtube_url"],
                view_count=video["view_count"],
                channel_name=video["channel_name"],
            )
            logger.info(f"Notion 저장 완료: {recipe.get('dish_name')} (page_id={page_id})")
            success += 1
        except Exception as e:
            # Notion 저장 실패 시 로그만 남기고 계속 진행
            logger.error(f"Notion 저장 실패 ({vid}): {e}")

    logger.info(f"=== 수집 완료: {success}/{len(videos)} 성공 ===")


if __name__ == "__main__":
    run()
