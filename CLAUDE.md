# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bottom-up recipe knowledge graph. Every day, 3 YouTube cooking recipe videos are automatically collected → classified by Case → saved to Notion Raw Video DB. Case A/B videos are additionally processed by Claude API to extract structured recipe data → saved to Recipe DB. Ingredients are eventually classified by **functional role**, not identity. Ontology structure emerges from data — never designed top-down.

## Running the Pipeline

```bash
# 수동 실행 (환경변수 필요)
YOUTUBE_API_KEY=... NOTION_TOKEN=... ANTHROPIC_API_KEY=... python collect.py

# GitHub Actions 수동 트리거: Actions 탭 → Daily Recipe Collection → Run workflow
```

Logs are written to `logs/run_YYYYMMDD.log` and stdout simultaneously.

## Architecture

```
Search Keywords DB (Notion)
        ↓ Active 키워드 조회 + Priority 가중치 랜덤 선택
   collect.py  ──  GitHub Actions cron UTC 03:00 (KST 12:00)
        ↓ YouTube Data API v3 검색 (Howto&Style 카테고리, relevanceLanguage)
   youtube_client.py  →  자막 추출 (youtube-transcript-api)
        ↓ Case 분류 + 중복 URL 체크
   notion_client.py  →  Raw Video DB 저장
        ↓ Case A (description 재료목록) 또는 B (자막 있음)
   claude_client.py  →  레시피 정보 추출 (Claude Haiku)
        ↓
   notion_client.py  →  Recipe DB 저장
```

## Notion DB Structure

세 개의 DB가 핵심:

**Search Keywords DB** (`612628cbef474ec089336969c19d66fd`)
- `Active` checkbox로 활성 여부 제어
- `Priority`: `0` (override — 0이 있으면 그것만 선택), `1`/`2`/`3` (가중치 3:2:1 랜덤)
- 검색어 우선순위: `Native keyword` → `EN keyword` → `KO keyword`
- `Native language` select로 YouTube `relevanceLanguage` 파라미터 결정

**Raw Video DB** (`370275ea061b804eae24ea782c1f6e62`)
- Case/Status로 처리 흐름 추적
- Notion 속성명에 `date:` prefix 붙는 날짜 필드 주의 (`date:Collected date:start`)

**Recipe DB** (`363275ea061b80a38181ec76c5e90592`)
- `Dish name` (Title), `Country of origin` (Select), `Key ingredients` (Rich Text, 콤마 구분)
- `Cooking techniques` / `Main category` / `Meal context` (Multi-select) — 허용값 목록은 `claude_client.py` 프롬프트 참고
- `Source URL` (Rich Text — URL 타입 아님 주의), `날짜` (Date)
- Classification Guidelines v9.0에 따라 7가지 Ingredient Role Tags 사용

## Case Classification Logic

`collect.py:classify_case()` — 수집 시 자동 결정:

| Case | 조건 | Status | Recipe DB |
|---|---|---|---|
| A (Auto) | Description에 재료+단위 패턴 3개↑ | 자동처리중 | ✅ 자동 저장 |
| B (Semi) | 자막 있음 | 자막대기 | ✅ 자동 저장 |
| C (Manual) | 자막도 재료목록도 없음 | 수동대기 | ❌ |
| D (Skip) | Duration ≤ 60초 | 제외 | ❌ |

재료 감지 정규식(`INGREDIENT_UNIT_PATTERN`)은 다국어 단위 지원: `g`, `gr` (이탈리아어), `grams`, `ml`, `cl`, `oz`, `½`/`¼` 등 유니코드 분수 포함.

## Key Constraints

- **DAILY_LIMIT = 3 고정** — 절대 변경 금지
- **top-down 온톨로지 설계 금지** — 실제 데이터 관찰 후 확장
- **누락 데이터 추론 금지** — 불명확한 정보는 빈 값으로 처리
- Notion 속성명/타입 변경 시 `notion_client.py`의 해당 payload도 함께 수정
- `claude_client.py` 프롬프트의 허용값 목록은 Notion DB 실제 Select 옵션과 항상 일치해야 함

## Required Secrets (GitHub Actions)

| Secret | 용도 |
|---|---|
| `YOUTUBE_API_KEY` | YouTube Data API v3 |
| `ANTHROPIC_API_KEY` | Claude API — Case A/B 레시피 추출 |
| `NOTION_TOKEN` | Notion Integration Token |
