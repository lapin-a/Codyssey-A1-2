# 여행 리포트 생성 CLI 프로그램

날짜를 입력받아 Google Gemini LLM API와 Kakao Local API를 연동하여 맞춤형 국내 여행 리포트(Markdown) 및 원본 데이터(JSON)를 자동 생성하는 CLI 도구입니다.

---

## 주요 기능

* **날짜 기반 여행지 1차 추천**: Gemini LLM API를 활용해 해당 날짜에 방문하기 좋은 국내 여행 도시, 날씨, 행사, 추천 이유를 구조화된 JSON 데이터로 수집합니다.
* **지역 맛집 검색**: 추천된 도시를 기준으로 Kakao Local API를 호출하여 주요 맛집 정보(상호명, 주소, 카테고리, URL 등)를 수집합니다.
* **통합 여행 리포트 생성**: 1차 추천 정보와 맛집 목록을 종합하여 1일 일정(오전/오후/저녁)이 포함된 Markdown 리포트를 작성합니다.
* **결과 캐싱**: 동일한 날짜로 재실행 시 기존에 저장된 원본 데이터 JSON이 존재하면 외부 API 재호출 없이 리포트만 재생성합니다.
* **예외 처리 및 내결함성**: 맛집 검색 API 실패 시에도 프로그램이 중단되지 않고 '데이터 없음'으로 처리하여 리포트 생성을 완료합니다.

---

## 디렉토리 구조

```text
.
├── main.py              # CLI 프로그램 메인 실행 파일
├── .env                 # 환경변수 설정 파일 (API Key 저장)
├── .env.example         # 환경변수 설정 예시 파일
├── requirements.txt     # 의존성 패키지 목록
└── results/             # 생성된 데이터 및 리포트 저장 디렉토리
    ├── {YYYY-MM-DD}_data.json
    └── {YYYY-MM-DD}_report.md
```

---

## 사전 준비 사항

* **Python 버전**: Python 3.9 이상 권장
* **필요 API Key**:
  * **Gemini API Key** (필수): Google AI Studio에서 발급
  * **Kakao REST API Key** (선택): Kakao Developers에서 발급 (미설정 시 맛집 검색 기능이 건너뛰어집니다.)

---

## 설치 및 설정 방법

### 1. 프로젝트 저장소 클론 및 이동
```bash
git clone <repository-url>
cd <repository-folder>
```

### 2. 가상환경 생성 및 활성화 (선택 사항)
```bash
python -m venv venv
# macOS / Linux
source venv/bin/activate
# Windows
venv\Scripts\activate
```

### 3. 필요 패키지 설치
```bash
pip install -r requirements.txt
```

> **참고**: `requirements.txt` 예시
> ```text
> google-genai
> requests
> python-dotenv
> ```

### 4. 환경변수(.env) 설정
프로젝트 루트 디렉토리에 `.env` 파일을 생성하고 발급받은 API 키를 입력합니다.

```env
GEMINI_API_KEY="your_gemini_api_key_here"
KAKAO_API_KEY="your_kakao_rest_api_key_here"
```

---

## 사용법

`-date` 옵션과 함께 `YYYY-MM-DD` 형식의 날짜를 전달하여 실행합니다.

### 실행 명령어
```bash
python main.py -date "2026-08-13"
```

### 날짜 형식이 잘못된 경우
날짜 형식이 `YYYY-MM-DD`와 일치하지 않을 경우 올바른 사용법 안내와 함께 종료됩니다.
```bash
python main.py -date "20260813"
# 출력: [오류] 날짜 형식이 올바르지 않습니다: "20260813"
```

---

## 동작 흐름

1. **입력 값 및 환경 검증**: 입력된 날짜 형식 및 `GEMINI_API_KEY` 설정 여부를 확인합니다.
2. **캐시 확인**: `results/{date}_data.json` 파일 존재 여부를 확인합니다.
   * 캐시 있음: 저장된 로컬 데이터를 불러옵니다.
   * 캐시 없음: 아래 3~4 단계를 진행합니다.
3. **1차 추천 (Gemini API)**: 입력 날짜 기준 국내 여행지 1곳을 추천받아 JSON 형식으로 파싱합니다. (실패 시 최대 1회 재시도)
4. **맛집 검색 (Kakao Local API)**: 추천된 도시를 키워드로 상위 5개 맛집을 검색합니다.
5. **최종 리포트 생성 (Gemini API)**: 추천 정보와 맛집 데이터를 종합하여 Markdown 리포트를 작성합니다.
6. **결과 저장**: `results/` 디렉토리에 JSON 데이터와 Markdown 리포트를 저장합니다.

---

## 출력 파일 예시

실행 완료 시 `results/` 폴더에 2개의 파일이 생성됩니다.

### 1. 원본 데이터 (`results/2026-08-13_data.json`)
```json
{
  "date": "2026-08-13",
  "recommendation": {
    "recommended_city": "강릉시",
    "weather": "맑음, 최고기온 28도",
    "events": [
      "강릉 해변 축제"
    ],
    "reason": "여름철 시원한 바다와 다양한 문화 행사를 즐기기 좋습니다."
  },
  "restaurants": [
    {
      "name": "동화가든",
      "address": "강원 강릉시 초당순두부길 77m",
      "category": "음식점 > 한식 > 두부요리",
      "url": "http://place.map.kakao.com/12345678",
      "x": "128.91...",
      "y": "37.79..."
    }
  ],
  "errors": []
}
```

### 2. 여행 리포트 (`results/2026-08-13_report.md`)
```markdown
# 강릉시 여행 리포트

## 추천 지역 & 추천 이유 요약
...

## 날씨 요약
...

## 행사/축제 목록
...

## 맛집 리스트
...

## 1일 일정 제안 (오전 / 오후 / 저녁 구성)
...
```
