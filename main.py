#!/usr/bin/env python3
"""
main.py
-------
여행 리포트 생성 CLI 프로그램 (단일 파일 통합 버전).

사용법:
    python main.py -date "2026-08-13"

동작 흐름:
    1) LLM API(Gemini)로 날짜 기반 국내 여행지 1차 추천 (JSON, 실패 시 1회 재시도)
    2) 추천 도시 기준 Kakao Local API로 맛집 검색 (실패해도 프로그램은 계속 진행)
    3) 1차 추천 + 맛집 목록을 종합해 LLM API로 최종 Markdown 리포트 생성
    4) results/ 폴더에 원본 데이터 JSON과 리포트 MD를 저장

동일 날짜로 재실행 시, results/{date}_data.json이 이미 존재하면
API를 재호출하지 않고 저장된 데이터로 리포트만 재생성한다(캐싱).

사용 기술:
    - LLM API: Google Gemini (gemini-2.5-flash, google-genai SDK)
      -> response_mime_type="application/json"으로 API 레벨에서 JSON 출력을
         강제할 수 있어 1차 추천 단계의 구조화 출력 요구사항에 적합.
    - 지도/장소 검색 API: Kakao Local (키워드 검색)
      -> REST API 키 하나로 인증이 간단하고, place_name/address_name/x,y/place_url
         등 필요한 필드가 응답에 모두 포함됨.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Optional

import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ============================================================
# 상수
# ============================================================

MODEL_NAME = "gemini-3.5-flash-lite"
REQUIRED_RECOMMENDATION_KEYS = ["recommended_city", "weather", "events", "reason"]
KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
RESULTS_DIR = "results"


# ============================================================
# [부분 1] LLM 클라이언트 (구 llm_client.py)
# ============================================================

def _get_gemini_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _build_recommendation_prompt(date_str: str, retry: bool = False) -> str:
    base = f"""당신은 국내 여행 추천 전문가입니다.
날짜: {date_str}

이 날짜에 방문하기 좋은 국내(대한민국) 여행 도시 1곳을 추천하세요.
실제 날씨/행사 정보의 사실 정확도는 중요하지 않습니다. 그럴듯한 형태로 생성하면 됩니다.

반드시 아래 JSON 스키마와 정확히 동일한 키만 사용해 JSON 객체 하나만 출력하세요.
다른 설명, 인사말, 코드블록 표시(```) 등은 절대 포함하지 마세요.

{{
  "recommended_city": "string",
  "weather": "string",
  "events": ["string", "..."],
  "reason": "string"
}}
"""
    if retry:
        base += "\n중요: 이전 응답이 JSON 파싱에 실패했습니다. 위 4개의 필수 키만 포함한 순수 JSON 객체만 다시 출력하세요."
    return base


def get_recommendation(date_str: str, errors: list) -> Optional[dict]:
    """
    1차 추천 (도시/날씨/행사/이유)을 JSON으로 받아온다.
    파싱 실패 시 최대 1회만 재시도.
    """
    client = _get_gemini_client()

    for attempt in range(2):  # 최초 1회 + 재시도 1회 = 최대 2회
        prompt = _build_recommendation_prompt(date_str, retry=(attempt == 1))
        try:
            resp = client.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            raw = resp.text
            data = json.loads(raw)

            if all(k in data for k in REQUIRED_RECOMMENDATION_KEYS):
                if isinstance(data["events"], str):
                    data["events"] = [data["events"]]
                return data
            else:
                errors.append(
                    f"1차 추천 응답에 필수 키 누락 (attempt={attempt + 1}): {list(data.keys())}"
                )
        except json.JSONDecodeError as e:
            errors.append(f"1차 추천 JSON 파싱 실패 (attempt={attempt + 1}): {e}")
        except Exception as e:
            errors.append(f"1차 추천 API 호출 실패 (attempt={attempt + 1}): {e}")
            break  # API 자체 오류는 재시도해도 동일할 가능성이 높으므로 즉시 중단

    return None


def generate_report(recommendation: dict, restaurants: list, date_str: str, errors: list) -> str:
    """
    1차 추천 + 맛집 목록을 종합해 최종 Markdown 리포트를 생성한다.
    """
    client = _get_gemini_client()

    if restaurants:
        restaurant_text = "\n".join(
            f"- {r.get('name', '이름없음')} | {r.get('category', '카테고리 정보없음')} | "
            f"{r.get('address', '주소정보없음')} | {r.get('url', '')}"
            for r in restaurants
        )
    else:
        restaurant_text = "데이터 없음 (맛집 검색 결과가 없거나 API 호출에 실패했습니다.)"

    prompt = f"""당신은 여행 리포트 작가입니다. 아래 정보를 바탕으로 한국어 Markdown 여행 리포트를 작성하세요.

[여행 날짜]
{date_str}

[1차 추천 정보]
- 추천 도시: {recommendation.get('recommended_city')}
- 날씨: {recommendation.get('weather')}
- 행사/축제: {', '.join(recommendation.get('events', [])) or '없음'}
- 추천 이유: {recommendation.get('reason')}

[맛집 검색 결과]
{restaurant_text}

다음 항목을 모두 포함한 Markdown 문서를 작성하세요 (다른 설명 없이 Markdown 본문만 출력):
1. # 제목 (추천 지역 이름 포함)
2. ## 추천 지역 & 추천 이유 요약
3. ## 날씨 요약
4. ## 행사/축제 목록
5. ## 맛집 리스트 (검색 결과가 "데이터 없음"이면 그대로 "데이터 없음"이라고 표기)
6. ## 1일 일정 제안 (오전 / 오후 / 저녁 구성)
"""

    try:
        resp = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7),
        )
        return resp.text
    except Exception as e:
        errors.append(f"리포트 생성 API 호출 실패: {e}")
        return (
            f"# {recommendation.get('recommended_city', '여행지')} 여행 리포트 (생성 실패)\n\n"
            f"리포트 생성 중 오류가 발생했습니다: {e}\n\n"
            f"## 원본 추천 정보\n"
            f"- 날씨: {recommendation.get('weather')}\n"
            f"- 행사: {', '.join(recommendation.get('events', []))}\n"
            f"- 이유: {recommendation.get('reason')}\n\n"
            f"## 맛집 리스트\n{restaurant_text}\n"
        )


# ============================================================
# [부분 2] 지도/장소 검색 클라이언트 (구 place_search.py)
# ============================================================

def search_restaurants(city: str, errors: list, size: int = 5) -> list:
    """
    지정한 도시 기준 맛집을 검색한다 (Kakao Local API).
    실패 시(키 없음/401/403/네트워크 오류/0건) 빈 리스트를 반환하고
    errors 리스트에 사유를 기록한다.
    """
    api_key = os.getenv("KAKAO_API_KEY")
    if not api_key:
        errors.append("KAKAO_API_KEY가 설정되지 않아 맛집 검색을 건너뜁니다.")
        return []

    headers = {"Authorization": f"KakaoAK {api_key}"}
    params = {"query": f"{city} 맛집", "size": size, "sort": "accuracy"}

    try:
        resp = requests.get(KAKAO_LOCAL_URL, headers=headers, params=params, timeout=10)

        if resp.status_code in (401, 403):
            errors.append(
                f"Kakao Local API 인증 실패 (status={resp.status_code}). 맛집 섹션은 '데이터 없음'으로 처리됩니다."
            )
            return []

        resp.raise_for_status()
        data = resp.json()
        documents = data.get("documents", [])

        if not documents:
            errors.append(f"'{city}' 맛집 검색 결과 0건입니다.")
            return []

        restaurants = []
        for doc in documents[:size]:
            restaurants.append(
                {
                    "name": doc.get("place_name", ""),
                    "address": doc.get("road_address_name") or doc.get("address_name", ""),
                    "category": doc.get("category_name", ""),
                    "url": doc.get("place_url", ""),
                    "x": doc.get("x", ""),  # 경도
                    "y": doc.get("y", ""),  # 위도
                }
            )
        return restaurants

    except requests.exceptions.RequestException as e:
        errors.append(f"Kakao Local API 호출 중 네트워크 오류: {e}. 맛집 섹션은 '데이터 없음'으로 처리됩니다.")
        return []
    except Exception as e:
        errors.append(f"Kakao Local API 처리 중 알 수 없는 오류: {e}. 맛집 섹션은 '데이터 없음'으로 처리됩니다.")
        return []


# ============================================================
# [부분 3] CLI 오케스트레이션 (구 main.py)
# ============================================================

def parse_args():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="날짜를 입력받아 국내 여행지 추천 + 맛집 검색 + 여행 리포트를 생성합니다.",
    )
    parser.add_argument(
        "-date",
        required=True,
        metavar='"YYYY-MM-DD"',
        help='여행 기준 날짜. 예: -date "2026-08-13"',
    )
    return parser.parse_args()


def validate_date(date_str: str):
    """날짜 형식(YYYY-MM-DD)이 잘못되면 usage를 출력하고 정상 종료(exit code 0)한다."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f'[오류] 날짜 형식이 올바르지 않습니다: "{date_str}"')
        print('사용법: python main.py -date "YYYY-MM-DD"')
        print('예시  : python main.py -date "2026-08-13"')
        sys.exit(0)


def check_required_env(errors: list) -> bool:
    """
    필수 API 키(GEMINI_API_KEY)가 없으면 즉시 종료 대상으로 안내한다.
    KAKAO_API_KEY는 없어도 프로그램은 동작 가능하므로 경고만 기록한다.
    """
    if not os.getenv("GEMINI_API_KEY"):
        print("[오류] GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
        print()
        print("설정 방법:")
        print("  1) 프로젝트 루트에 .env 파일을 만들고 아래처럼 작성하세요:")
        print('     GEMINI_API_KEY="your-gemini-api-key"')
        print('     KAKAO_API_KEY="your-kakao-rest-api-key"')
        print("  2) 또는 셸에서 환경변수로 직접 지정하세요:")
        print('     export GEMINI_API_KEY="your-gemini-api-key"')
        print()
        print("자세한 내용은 .env.example 파일과 README.md를 참고하세요.")
        return False

    if not os.getenv("KAKAO_API_KEY"):
        errors.append("KAKAO_API_KEY가 설정되지 않았습니다. 맛집 검색 단계는 '데이터 없음'으로 처리됩니다.")

    return True


def load_cached_data(date_str: str):
    """동일 날짜의 기존 원본 데이터 JSON이 있으면 로드해서 반환. 없으면 None."""
    cache_path = os.path.join(RESULTS_DIR, f"{date_str}_data.json")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def save_results(date_str: str, result_data: dict, report_md: str):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    data_path = os.path.join(RESULTS_DIR, f"{date_str}_data.json")
    report_path = os.path.join(RESULTS_DIR, f"{date_str}_report.md")

    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(result_data, f, ensure_ascii=False, indent=2)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_md)

    return data_path, report_path


def main():
    load_dotenv()  # .env 파일 로드 (있으면)

    args = parse_args()
    validate_date(args.date)
    date_str = args.date

    errors = []

    if not check_required_env(errors):
        sys.exit(1)

    cached = load_cached_data(date_str)

    if cached and cached.get("recommendation"):
        print(f'[캐시] "{date_str}"에 대한 기존 결과를 발견했습니다. API 재호출 없이 리포트만 재생성합니다...')
        recommendation = cached["recommendation"]
        restaurants = cached.get("restaurants", [])
        errors = cached.get("errors", [])
    else:
        print("1차 추천 요청 중... (LLM API)")
        recommendation = get_recommendation(date_str, errors)

        if recommendation is None:
            print("[오류] 1차 추천 생성에 실패했습니다. 프로그램을 종료합니다.")
            save_results(
                date_str,
                {"date": date_str, "recommendation": None, "restaurants": [], "errors": errors},
                "# 리포트 생성 실패\n\n1차 추천 단계에서 오류가 발생해 리포트를 생성할 수 없었습니다.\n",
            )
            sys.exit(1)

        city = recommendation.get("recommended_city", "")
        print(f'맛집 검색 중... (기준 도시: "{city}")')
        restaurants = search_restaurants(city, errors)

    print("리포트 생성 중... (LLM API)")
    report_md = generate_report(recommendation, restaurants, date_str, errors)

    result_data = {
        "date": date_str,
        "recommendation": recommendation,
        "restaurants": restaurants,
        "errors": errors,
    }

    data_path, report_path = save_results(date_str, result_data, report_md)

    print()
    print("완료되었습니다.")
    print(f"  - 원본 데이터: {data_path}")
    print(f"  - 여행 리포트: {report_path}")
    if errors:
        print(f"  - 경고/오류 {len(errors)}건이 기록되었습니다 (원본 데이터 JSON의 'errors' 참고).")


if __name__ == "__main__":
    main()