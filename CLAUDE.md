# Recipe Knowledge Graph & Culinary Ontology

## Project Overview

Bottom-up recipe knowledge graph built from real recipe inputs. Ingredients are classified by **functional role in cooking**, not by identity. Ontology structure emerges from observed data patterns — not designed top-down.

---

## Automation Pipeline

### Goal
매일 YouTube에서 요리 레시피 영상 3개를 자동 수집 → Claude API로 분석 → Notion DB에 저장.

### Architecture
```
GitHub Actions (cron, 매일 0–16시 랜덤)
  → collect.py
      → YouTube Data API v3  (조회수 5천↑, 트렌드 영상 3개 검색)
      → Claude API            (음식명 / 기원국가 / 재료 구조화 추출)
      → Notion API            (DB 테이블에 행 추가)
      → 실행 로그 저장
```

### Schedule (GitHub Actions)
```yaml
# .github/workflows/collect.yml
on:
  schedule:
    - cron: '0 3 * * *'   # UTC 03:00 = KST 12:00 (0–16시 이내)
```
- UTC 기준으로 cron 설정 (KST = UTC+9)
- 변경 원할 경우 UTC 기준으로 계산할 것

### Daily Limits
- 수집 영상 수: **3개/일** (고정)
- Claude API 호출: 영상당 1회 (총 3회/일)
- YouTube API quota: 검색 1회 = 100 units (일 할당량 10,000 units 이내)

---

## Required API Keys

GitHub Actions Secrets에 아래 키 등록 필요:

| Secret 이름 | 설명 |
|---|---|
| `YOUTUBE_API_KEY` | Google Cloud Console → YouTube Data API v3 |
| `ANTHROPIC_API_KEY` | Anthropic Console |
| `NOTION_TOKEN` | Notion → Settings → Integrations |
| `NOTION_DATABASE_ID` | 저장할 Notion DB의 ID |

---

## File & Folder Conventions

```
/
├── .github/
│   └── workflows/
│       └── collect.yml       # GitHub Actions 스케줄 정의
├── collect.py                # 메인 파이프라인 스크립트
├── youtube_client.py         # YouTube API 래퍼
├── claude_client.py          # Claude API 래퍼
├── notion_client.py          # Notion API 래퍼
├── data/
│   ├── recipes/              # 수집된 레시피 JSON (백업용)
│   ├── ingredients/          # 재료 레지스트리 CSV
│   └── ontology/             # 기능 분류 매핑
├── logs/
│   └── run_YYYYMMDD.log      # 일별 실행 로그
└── naming_reference.md       # 표준화 재료명 누적 기록
```

---

## Notion DB Schema

Notion DB에 아래 속성(Property) 구성 필요:

| 속성명 | 타입 | 설명 |
|---|---|---|
| `dish_name` | Title | 음식명 (영문 표준명) |
| `origin_country` | Select | 기원 국가 |
| `ingredients` | Rich Text | 재료 목록 (콤마 구분) |
| `youtube_url` | URL | 원본 영상 링크 |
| `view_count` | Number | 조회수 |
| `collected_at` | Date | 수집 일시 |
| `channel_name` | Rich Text | 채널명 |

---

## Data Principles

### Ingredient Naming Standard
- 영문 요리 표준명 사용 (YouTube, 쿡북, 셰프 기준)
  - ✅ `garlic` / `unsalted butter` / `fish sauce`
  - ❌ `마늘` / `버터` / `피쉬 소스`
- 한국 특화 재료: romanized Korean + English descriptor
  - ✅ `guk-ganjang (Korean soup soy sauce)`
  - ✅ `doenjang (Korean fermented soybean paste)`
- 신규 재료명은 반드시 `naming_reference.md`에 추가

### Ingredient Classification
- **기능적 역할** 기준 분류 (재료 정체성 기준 아님)
  - 예: `tofu` → `protein_source` 또는 `texture_filler` (레시피 맥락에 따라)
- 단일 재료에 복수 기능 태그 허용
- 레시피별로 맥락에 따라 판단, 전역 매핑 사용 금지

---

## Claude API Usage

### Prompt Template
```
다음 YouTube 요리 영상 정보를 분석해서 JSON으로 반환해줘.

영상 제목: {title}
채널명: {channel}
영상 설명: {description}

반환 형식:
{
  "dish_name": "영문 표준 음식명",
  "origin_country": "기원 국가 (영문)",
  "ingredients": ["재료1", "재료2", ...]
}

규칙:
- dish_name은 영문 요리 표준명 사용
- 재료가 불명확하면 ingredients를 빈 배열로 반환
- JSON만 반환, 다른 텍스트 없이
```

### Model
- `claude-haiku-*` 사용 권장 (비용 효율, 구조화 추출에 충분)

---

## Key Constraints

- **수집 수 변경 금지** — 하루 3개 제한, 임의 증가 금지
- **top-down 온톨로지 설계 금지** — 실제 데이터 입력 후 패턴 관찰로 확장
- **누락 데이터 추론 금지** — 불명확한 정보는 `"unknown"` 또는 빈 값으로 처리
- **스키마 변경 시** — 정의 업데이트 + 기존 레코드 마이그레이션 스크립트 작성

---

## Common Tasks

### 파이프라인 첫 세팅
1. Google Cloud Console에서 YouTube Data API v3 활성화 → API 키 발급
2. Anthropic Console에서 API 키 발급
3. Notion에서 DB 생성 (위 스키마 기준) + Integration 연결 → 토큰 발급
4. GitHub Secrets에 4개 키 등록
5. `collect.yml` cron 시간 설정 (UTC 기준)
6. 첫 실행은 수동으로 `workflow_dispatch` 트리거해서 검증

### 신규 레시피 수동 추가
1. `collect.py` 직접 실행 또는 GitHub Actions 수동 트리거
2. 결과 확인: Notion DB + `logs/` 디렉토리

### 스키마 수정
1. Notion DB 속성 업데이트
2. `notion_client.py`의 payload 구조 수정
3. 기존 레코드 영향 여부 확인

---

## Notes for Claude Code

- 새 재료명 추가 시 항상 `naming_reference.md` 먼저 확인
- API 키는 절대 코드에 하드코딩 금지 — 항상 환경변수 참조
- YouTube API quota 초과 시 다음날로 수집 미루는 로직 포함할 것
- 에러 발생 시 Notion 저장 건너뛰고 로그에만 기록 (파이프라인 중단 금지)
- 애매한 재료명이나 분류 판단은 `# TODO` 주석으로 플래그
