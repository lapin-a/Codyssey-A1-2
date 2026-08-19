# 여행 리포트 생성 CLI

날짜 하나만 입력하면, LLM이 그 시기에 어울리는 국내 여행지를 추천하고,
해당 도시의 맛집을 검색한 뒤, 두 결과를 종합해 Markdown 여행 리포트를 만들어주는
순수 CLI 프로그램입니다.

## 1. 동작 흐름

```
-date "YYYY-MM-DD" 입력
        │
        ▼
[1] LLM API(Google Gemini, gemini-2.5-flash)로 1차 추천 생성
    -> { recommended_city, weather, events, reason } JSON
    -> JSON 파싱 실패 시 프롬프트를 수정해 최대 1회만 재시도
        │
        ▼
[2] recommended_city 기준으로 Kakao Local API 맛집 검색 (최대 5곳)
    -> 인증 실패 / 네트워크 오류 / 0건이어도 프로그램은 중단하지 않고
       '데이터 없음'으로 처리 후 다음 단계 진행
        │
        ▼
[3] LLM API로 1차 추천 + 맛집 목록을 종합해 최종 Markdown 리포트 생성
        │
        ▼
results/{date}_data.json  (1차 추천 + 맛집 목록 + errors)
results/{date}_report.md  (최종 여행 리포트)
```

### 사용 기술
- **LLM API**: Google Gemini (`gemini-2.5-flash`, `google-genai` SDK)
  - 선택 이유: `response_mime_type="application/json"` 옵션으로 API 레벨에서
    JSON 출력 강제가 가능해, 1차 추천 단계의 구조화 출력 요구사항을 안정적으로
    만족시킬 수 있습니다.
- **지도/장소 검색 API**: Kakao Local (키워드 검색 API)
  - 선택 이유: REST API 키 하나로 인증이 간단하고, 응답에 `place_name`,
    `address_name`, `x`/`y`(경도/위도), `place_url` 등 요구 필드가 모두 포함됩니다.
- Python 3.10+, `argparse`, `python-dotenv` 사용. 웹 UI 없음.

## 2. 설치 및 실행 방법

```bash
# 1) (권장) 가상환경 생성
python3 -m venv .venv
source .venv/bin/activate     # Windows: .venv\Scripts\activate

# 2) 의존성 설치
pip install -r requirements.txt

# 3) API 키 설정 (아래 3번 항목 참고)
cp .env.example .env
# .env 파일을 열어 실제 키 값을 입력

# 4) 실행
python main.py -date "2026-08-13"
```

날짜 형식이 잘못된 경우(`YYYY-MM-DD`가 아닌 경우) 사용법 안내를 출력하고 정상 종료합니다.

```bash
python main.py -date "2026/08/13"
# [오류] 날짜 형식이 올바르지 않습니다: "2026/08/13"
# 사용법: python main.py -date "YYYY-MM-DD"
```

### 재실행(캐싱)
동일한 `-date`로 다시 실행하면, `results/{date}_data.json`이 이미 존재할 경우
LLM/맛집 검색 API를 재호출하지 않고 저장된 데이터를 그대로 사용해 리포트만
재생성합니다. 처음부터 다시 API를 호출하고 싶다면 해당 결과 파일을 삭제한 뒤
재실행하세요.

## 3. API 키 설정 방법

`.env.example` 파일을 복사해 `.env` 파일을 만들고, 아래와 같은 형식으로
실제 키 값을 채워 넣으세요 (아래는 예시 템플릿이며 실제 키가 아닙니다).

```env
GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
KAKAO_API_KEY="YOUR_KAKAO_REST_API_KEY"
```

- `GEMINI_API_KEY`: 필수. 없으면 프로그램이 즉시 종료되며 설정 방법을 안내합니다.
  [Google AI Studio](https://aistudio.google.com/apikey)에서 발급받을 수 있습니다.
- `KAKAO_API_KEY`: 선택. 없거나 인증에 실패해도 프로그램은 중단되지 않고
  맛집 섹션이 "데이터 없음"으로 표시됩니다.

환경변수로 직접 지정할 수도 있습니다.

```bash
export GEMINI_API_KEY="YOUR_GEMINI_API_KEY"
export KAKAO_API_KEY="YOUR_KAKAO_REST_API_KEY"
```

## 4. 결과 확인 방법

실행이 끝나면 `results/` 폴더에 아래 두 파일이 생성됩니다.

```
results/
├── 2026-08-13_data.json   # 1차 추천 JSON + 맛집 검색 결과 + errors 목록
└── 2026-08-13_report.md   # 최종 여행 리포트 (Markdown)
```

- `*_data.json`: 파이프라인 각 단계의 원본 데이터를 그대로 보존합니다.
  실행 중 발생한 경고/오류는 `errors` 배열에 기록되며, 문제가 없었다면
  빈 배열(`[]`)입니다.
- `*_report.md`: 추천 지역/이유, 날씨 요약, 행사 목록, 맛집 리스트,
  1일 일정 제안이 포함된 최종 리포트입니다. 아무 Markdown 뷰어(또는 VS Code,
  GitHub 등)로 열어보면 됩니다.

## 5. API 키 유출 방지 주의사항

- 코드 어디에도 API 키를 직접 작성하지 않았습니다. 모든 키는
  `.env` 파일 또는 환경변수에서 `python-dotenv`로 로드합니다.
- `.env` 파일은 `.gitignore`에 포함되어 있어 실수로 커밋되지 않습니다.
- `.env.example`에는 플레이스홀더 값만 있으며 실제 키는 포함되어 있지 않습니다.
- 로그 출력과 `results/` 산출물(JSON/MD)에는 API 키 값이 절대 포함되지
  않도록 설계했습니다 (에러 메시지에도 키 값 자체는 노출하지 않고
  상태 코드/사유만 기록합니다).
- 만약 실수로 키를 커밋했다면, 즉시 해당 서비스(Google AI Studio/Kakao) 콘솔에서
  키를 폐기(revoke)하고 새 키를 발급받으세요. `git log`에서 이미 커밋된
  히스토리는 `git filter-repo` 등으로 별도로 제거해야 완전히 삭제됩니다.

## 6. 프로젝트 구조

모든 로직(1차 추천 / 맛집 검색 / 리포트 생성 / CLI 오케스트레이션)은
`main.py` 한 파일에 통합되어 있습니다. 파일 내부는 아래 3개 섹션으로 구분됩니다.

```
travel_report_cli/
├── main.py            # 단일 파일: LLM 호출 + Kakao Local 호출 + CLI 오케스트레이션
│                       #  [부분 1] LLM 클라이언트 (1차 추천 / 최종 리포트 생성)
│                       #  [부분 2] 지도/장소 검색 클라이언트 (맛집 검색)
│                       #  [부분 3] CLI 오케스트레이션 (argparse, 저장, 캐싱)
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
└── results/            # 실행 결과 저장 폴더
```

## 7. 향후 확장 아이디어 (미구현)

- 복수 지역 추천(`recommended_cities: [...]`)으로 확장해 지역별 맛집/리포트를
  섹션별로 정리
- 지역별 리포트를 하나의 문서에 묶어서 비교 형태로 제공