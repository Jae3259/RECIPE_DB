#!/usr/bin/env python3
"""
Recipe DB Filler
사용법: python3 recipe_filler.py "https://youtu.be/..."
"""

import sys
import json
import re
import os
import subprocess

# ── 설정 ──────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NOTION_TOKEN      = os.environ.get("NOTION_TOKEN", "")
NOTION_DB_ID      = "363275ea061b80a38181ec76c5e90592"
COOKIE_FILE       = "/root/.claude/uploads/1d406006-bc34-4317-8ac3-0bdf4b362976/2aaf88ed-cookies.txt"

CLASSIFICATION_PROMPT = """
You are a culinary data specialist. Extract structured recipe data from a YouTube video.
You will receive: video title, channel name, description (which often contains ingredients), and transcript.

Return ONLY valid JSON with this exact structure (no markdown, no explanation):
{
  "dish_name": "English dish name",
  "local_name": "local language name (Korean/Japanese/etc)",
  "country_of_origin": "country",
  "region": "specific region if known, else empty string",
  "main_category": ["category1"],
  "cooking_techniques": ["technique1", "technique2"],
  "main_protein": "ingredients or empty string",
  "main_carb_base": "ingredients or empty string",
  "sauce_seasoning": "comma-separated ingredients or empty string",
  "aromatics": "comma-separated ingredients or empty string",
  "body": "comma-separated ingredients or empty string",
  "fat": "comma-separated ingredients or empty string",
  "garnish": "comma-separated ingredients or empty string",
  "serving_temperature": "Hot or Cold or Room-temp",
  "meal_context": ["context1"],
  "dish_group": "local language group name or empty string",
  "variant_notes": "protein variants or substitutions mentioned",
  "design_notes": "ambiguous classifications, boundary cases, interesting cooking science notes"
}

INGREDIENT ROLE RULES:
- Main Protein: primary protein (meat/seafood/tofu/egg)
- Main Carb & Base: carbohydrate backbone (rice/noodle/bread/dough)
- Sauce & Seasoning: sauces/condiments that determine flavor (gochujang, fish sauce, soy sauce)
- Aromatics: flavor base added early in cooking (garlic, ginger, kombu, dried scallop)
- Body: texture/volume ingredients added during cooking (mushrooms, vegetables)
- Fat: oils and fats
- Garnish: finishing ingredients added AFTER cooking

NAMING RULES:
- Well-known: standard English (garlic, olive oil)
- Asian/regional specific: romanized + descriptor
  Examples: gochujang (Korean fermented chili paste), doenjang (Korean fermented soybean paste)
  jin-ganjang (Korean dark soy sauce), guk-ganjang (Korean soup soy sauce)
  kombu (Japanese kelp), mirin (Japanese sweet rice wine), sake (Japanese rice wine)
  menma (seasoned bamboo shoots), hotate (dried scallop), ajitsuke tamago (soft-boiled marinated egg)
- Never use broad "soy sauce" alone — specify type

COOKING TECHNIQUES (use only these):
Moist: Boiling, Simmering, Steaming, Poaching, Stewing, Braising, Blanching
Dry: Stir-frying, Sautéing, Grilling, Roasting, Baking, Deep-frying, Pan-frying, Broiling, Smoking
Combination: Sous vide
Preservation: Fermenting, Curing, Kneading, Raw preparation

MAIN CATEGORY options:
Soup & Stew, Grilled, Stir-fried, Fried, Raw dish, Fermented, Noodle, Rice dish, Bread & Dough

MEAL CONTEXT options:
Everyday meal, Festive, Street food, Bar snack, Late night, Brunch, Fine dining, Comfort food, Packed lunch
"""

# ── 의존성 확인 및 설치 ────────────────────────────
def ensure_deps():
    try:
        import yt_dlp
        import anthropic
        import requests
    except ImportError:
        print("📦 필요한 패키지 설치 중...")
        subprocess.run([
            sys.executable, "-m", "pip", "install",
            "yt-dlp", "anthropic", "requests", "-q"
        ])

# ── YouTube 데이터 추출 ────────────────────────────
def fetch_youtube_data(url: str) -> dict:
    import yt_dlp

    print(f"🎬 YouTube 데이터 추출 중...")

    ydl_opts = {
        "skip_download": True,
        "quiet": True,
        "writeautomaticsub": False,
        "subtitleslangs": ["ko", "en", "ja"],
        "writesubtitles": True,
        "nocheckcertificate": True,
        "cookiefile": COOKIE_FILE,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False)

    title       = info.get("title", "")
    channel     = info.get("channel", "")
    description = info.get("description", "")

    # 자막 추출 (자동 자막 포함)
    transcript = ""
    for lang in ["ko", "en", "ja"]:
        # 수동 자막 우선
        subs = info.get("subtitles", {}).get(lang, [])
        if not subs:
            subs = info.get("automatic_captions", {}).get(lang, [])
        if subs:
            # json3 포맷 선호
            sub_url = next(
                (s["url"] for s in subs if s.get("ext") in ["json3", "vtt", "srv3"]),
                subs[0].get("url", "") if subs else ""
            )
            if sub_url:
                transcript = _fetch_subtitle_text(sub_url)
                if transcript:
                    print(f"   ✅ 자막 언어: {lang} ({len(transcript)}자)")
                    break

    print(f"   제목: {title}")
    print(f"   채널: {channel}")
    print(f"   설명란: {len(description)}자")
    print(f"   자막: {len(transcript)}자")

    return {
        "url": url,
        "title": title,
        "channel": channel,
        "description": description,
        "transcript": transcript,
    }

def _fetch_subtitle_text(sub_url: str) -> str:
    import requests
    try:
        r = requests.get(sub_url, timeout=10)
        content = r.text

        # json3 포맷 파싱
        if sub_url.endswith("json3") or "json3" in sub_url:
            data = json.loads(content)
            texts = []
            for event in data.get("events", []):
                for seg in event.get("segs", []):
                    t = seg.get("utf8", "").strip()
                    if t and t != "\n":
                        texts.append(t)
            return " ".join(texts)

        # VTT 포맷 파싱
        lines = content.split("\n")
        texts = []
        for line in lines:
            line = line.strip()
            if (line and
                not line.startswith("WEBVTT") and
                not line.startswith("NOTE") and
                not re.match(r"^\d{2}:\d{2}", line) and
                not re.match(r"^[\d]+$", line) and
                "<" not in line):
                texts.append(line)
        return " ".join(texts)

    except Exception as e:
        print(f"   ⚠️  자막 파싱 실패: {e}")
        return ""

# ── Claude API로 필드 분류 ─────────────────────────
def extract_fields(video_data: dict) -> dict:
    import anthropic

    print("\n🤖 Claude가 레시피 필드 분류 중...")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    user_content = f"""
Video Title: {video_data['title']}
Channel: {video_data['channel']}
URL: {video_data['url']}

=== DESCRIPTION (ingredients often listed here) ===
{video_data['description'][:3000]}

=== TRANSCRIPT (first 6000 chars) ===
{video_data['transcript'][:6000]}
"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=CLASSIFICATION_PROMPT,
        messages=[{"role": "user", "content": user_content}]
    )

    raw = message.content[0].text.strip()

    # JSON 추출
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if not json_match:
        raise ValueError("JSON 추출 실패")

    return json.loads(json_match.group())

# ── 검토 화면 ──────────────────────────────────────
def review_and_edit(fields: dict) -> dict:
    print("\n" + "="*60)
    print("📋 추출 결과 — 수정하려면 값을 입력, 유지하려면 Enter")
    print("="*60)

    editable = [
        ("dish_name",         "Dish name"),
        ("local_name",        "Local name"),
        ("country_of_origin", "Country of origin"),
        ("region",            "Region"),
        ("main_category",     "Main category (쉼표 구분)"),
        ("cooking_techniques","Cooking techniques (쉼표 구분)"),
        ("main_protein",      "Main Protein"),
        ("main_carb_base",    "Main Carb & Base"),
        ("sauce_seasoning",   "Sauce & Seasoning"),
        ("aromatics",         "Aromatics"),
        ("body",              "Body"),
        ("fat",               "Fat"),
        ("garnish",           "Garnish"),
        ("serving_temperature","Serving temperature"),
        ("meal_context",      "Meal context (쉼표 구분)"),
        ("dish_group",        "Dish group"),
        ("variant_notes",     "Variant notes"),
        ("design_notes",      "Design notes"),
    ]

    for key, label in editable:
        current = fields.get(key, "")
        if isinstance(current, list):
            display = ", ".join(current)
        else:
            display = str(current)

        print(f"\n  [{label}]")
        print(f"  현재: {display[:120]}")
        user_input = input("  수정: ").strip()

        if user_input:
            if key in ("main_category", "cooking_techniques", "meal_context"):
                fields[key] = [x.strip() for x in user_input.split(",") if x.strip()]
            else:
                fields[key] = user_input

    return fields

# ── Notion 저장 ────────────────────────────────────
def save_to_notion(fields: dict, url: str):
    import requests

    print("\n💾 Notion에 저장 중...")

    # Key ingredients를 하나의 텍스트 필드로 합치기
    ingredient_parts = []
    for role, key in [
        ("Main Protein",      "main_protein"),
        ("Main Carb & Base",  "main_carb_base"),
        ("Sauce & Seasoning", "sauce_seasoning"),
        ("Aromatics",         "aromatics"),
        ("Body",              "body"),
        ("Fat",               "fat"),
        ("Garnish",           "garnish"),
    ]:
        val = fields.get(key, "").strip()
        if val:
            ingredient_parts.append(f"{role}: {val}")
    key_ingredients = "\n".join(ingredient_parts)

    def multi_select(lst):
        if isinstance(lst, str):
            lst = [x.strip() for x in lst.split(",") if x.strip()]
        return [{"name": n} for n in lst if n]

    def text(val):
        return [{"text": {"content": str(val)[:2000]}}]

    props = {
        "Dish name":          {"title": text(fields.get("dish_name", ""))},
        "Local name":         {"rich_text": text(fields.get("local_name", ""))},
        "Country of origin":  {"select": {"name": fields.get("country_of_origin", "")}},
        "Region":             {"rich_text": text(fields.get("region", ""))},
        "Main category":      {"multi_select": multi_select(fields.get("main_category", []))},
        "Cooking techniques": {"multi_select": multi_select(fields.get("cooking_techniques", []))},
        "Key ingredients":    {"rich_text": text(key_ingredients)},
        "Serving temperature":{"select": {"name": fields.get("serving_temperature", "Hot")}},
        "Meal context":       {"multi_select": multi_select(fields.get("meal_context", []))},
        "Dish group":         {"rich_text": text(fields.get("dish_group", ""))},
        "Variant notes":      {"rich_text": text(fields.get("variant_notes", ""))},
        "Source URL":         {"url": url},
        "Design notes":       {"rich_text": text(fields.get("design_notes", ""))},
    }

    res = requests.post(
        "https://api.notion.com/v1/pages",
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Content-Type": "application/json",
            "Notion-Version": "2022-06-28",
        },
        json={
            "parent": {"database_id": NOTION_DB_ID},
            "properties": props,
        },
        timeout=15,
    )

    if res.status_code == 200:
        data = res.json()
        page_url = data.get("url", "")
        print(f"\n✅ 저장 완료!")
        print(f"   Notion 페이지: {page_url}")
    else:
        print(f"\n❌ 저장 실패 (HTTP {res.status_code})")
        print(res.text[:500])

# ── 메인 ──────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        print("사용법: python3 recipe_filler.py 'YouTube URL'")
        print("예시:   python3 recipe_filler.py 'https://youtu.be/t_PUFBP2FQw'")
        sys.exit(1)

    url = sys.argv[1]

    # 환경변수 확인
    if not ANTHROPIC_API_KEY:
        print("❌ ANTHROPIC_API_KEY 환경변수가 없어.")
        print("   export ANTHROPIC_API_KEY='sk-ant-...'")
        sys.exit(1)
    if not NOTION_TOKEN:
        print("❌ NOTION_TOKEN 환경변수가 없어.")
        print("   export NOTION_TOKEN='secret_...'")
        sys.exit(1)

    ensure_deps()

    try:
        # 1. YouTube 데이터 추출
        video_data = fetch_youtube_data(url)

        # 2. Claude로 필드 분류
        fields = extract_fields(video_data)

        # 3. 검토 및 수정
        fields = review_and_edit(fields)

        # 4. Notion 저장 확인
        print("\n" + "="*60)
        confirm = input("Notion에 저장할까? (y/n): ").strip().lower()
        if confirm == "y":
            save_to_notion(fields, url)
        else:
            print("저장 취소됨.")
            print("\n추출된 JSON:")
            print(json.dumps(fields, ensure_ascii=False, indent=2))

    except KeyboardInterrupt:
        print("\n\n취소됨.")
    except Exception as e:
        print(f"\n❌ 오류: {e}")
        raise

if __name__ == "__main__":
    main()
