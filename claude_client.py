import json
import os
import anthropic


_client = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def extract_recipe(title: str, channel: str, description: str) -> dict:
    prompt = f"""다음 YouTube 요리 영상 정보를 분석해서 JSON으로 반환해줘.

영상 제목: {title}
채널명: {channel}
영상 설명: {description}

반환 형식:
{{
  "dish_name": "영문 표준 음식명",
  "origin_country": "기원 국가 (영문)",
  "ingredients": ["재료1", "재료2", ...]
}}

규칙:
- dish_name은 영문 요리 표준명 사용
- 재료가 불명확하면 ingredients를 빈 배열로 반환
- JSON만 반환, 다른 텍스트 없이"""

    client = _get_client()
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # JSON 파싱 실패 시 빈 값 반환 (추론 금지 원칙)
        return {"dish_name": "unknown", "origin_country": "unknown", "ingredients": []}
