import json
import os
import re
import anthropic


_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def extract_recipe(title: str, channel: str, text: str) -> dict:
    """
    text: description (Case A) 또는 subtitle_text (Case B)
    반환: Recipe DB 저장용 dict
    """
    prompt = f"""다음 YouTube 요리 영상 정보를 분석해서 JSON으로 반환해줘.

영상 제목: {title}
채널명: {channel}
영상 내용: {text[:3000]}

반환 형식:
{{
  "dish_name": "영문 표준 음식명",
  "local_name": "현지어 음식명 (없으면 빈 문자열)",
  "country_of_origin": "기원 국가 (아래 허용값 중 하나, 없으면 빈 문자열)",
  "key_ingredients": "재료1, 재료2, 재료3 (콤마 구분 텍스트, 불명확하면 빈 문자열)",
  "cooking_techniques": ["기법1", "기법2"],
  "main_category": ["카테고리1"],
  "meal_context": ["컨텍스트1"],
  "serving_temperature": "Hot 또는 Cold 또는 Room-temp (불명확하면 빈 문자열)"
}}

country_of_origin 허용값: Republic of Korea, Thailand, Italy, Spain, Japan, USA, China
cooking_techniques 허용값: Boiling, Simmering, Stewing, Braising, Stir-frying, Sautéing, Grilling, Roasting, Baking, Deep-frying, Pan-frying, Broiling, Smoking, Fermenting, Curing, Kneading, Raw preparation, Sous vide, Steaming, Poaching, Blanching
main_category 허용값: Bread & Dough, Rice dish, Fermented, Raw dish, Noodle, Fried, Stir-fry, Grilled, Soup & Stew
meal_context 허용값: Everyday meal, Fine dining, Festive, Street food, Brunch, Late night, Bar snack, Comfort food, Packed lunch

규칙:
- dish_name은 영문 요리 표준명 사용
- 허용값 목록에 없는 값은 절대 사용하지 말 것
- 불명확한 정보는 빈 문자열 또는 빈 배열로 반환 (추론 금지)
- JSON만 반환, 다른 텍스트 없이"""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "dish_name": "unknown", "local_name": "", "country_of_origin": "",
            "key_ingredients": "", "cooking_techniques": [], "main_category": [],
            "meal_context": [], "serving_temperature": "",
        }


def _preprocess_description(text: str) -> str:
    """regex로 확실한 노이즈 제거 (URL, 해시태그, 타임스탬프 줄)."""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'#+\S+', '', text)
    text = re.sub(r'^\s*\d{1,2}:\d{2}.*$', '', text, flags=re.MULTILINE)  # 00:00 타임스탬프
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def clean_description(description: str) -> str:
    """
    YouTube description에서 레시피 관련 내용만 추출. 언어는 원어 유지.
    실패 시 원본 반환.
    """
    if not description or len(description) < 50:
        return description

    preprocessed = _preprocess_description(description)
    if not preprocessed:
        return description

    prompt = f"""Extract only the recipe-relevant content from this YouTube cooking video description.
Keep the original language as-is (do not translate).

KEEP:
- Ingredient list with quantities and units
- Cooking steps and instructions
- Timing information (temperatures, durations)
- Dish description or background

REMOVE:
- Social media handles and promotion (Instagram, Facebook, TikTok, subscribe prompts)
- Music credits (Track:, Music by:, Audio Library, etc.)
- Sponsorship or advertisement text
- Channel promotion text
- Any remaining URLs

If there is no recipe-relevant content at all, return an empty string.
Return only the extracted text with no additional commentary.

---
{preprocessed[:4000]}
---"""

    try:
        client = _get_client()
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception:
        return description
