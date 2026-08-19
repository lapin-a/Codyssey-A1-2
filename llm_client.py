"""
llm_client.py
-------------
LLM(OpenAI) 호출을 담당하는 모듈.

선택 이유:
- OpenAI API는 `response_format={"type": "json_object"}` 옵션으로
  "JSON만 출력"을 API 레벨에서 강제할 수 있어, 1차 추천 단계의
  스키마 강제 요구사항을 안정적으로 만족시키기 좋다.
- 사용 모델: gpt-4o-mini (비용 효율적이면서 JSON 구조화 출력 품질이 충분함)
"""

import json
import os
from typing import Optional

from openai import OpenAI

MODEL_NAME = "gpt-4o-mini"

REQUIRED_KEYS = ["recommended_city", "weather", "events", "reason"]


def _get_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


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
    client = _get_client()

    for attempt in range(2):  # 최초 1회 + 재시도 1회 = 최대 2회
        prompt = _build_recommendation_prompt(date_str, retry=(attempt == 1))
        try:
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.7,
            )
            raw = resp.choices[0].message.content
            data = json.loads(raw)

            if all(k in data for k in REQUIRED_KEYS):
                # events가 문자열로 왔을 경우 리스트로 보정
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
    client = _get_client()

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
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        return resp.choices[0].message.content
    except Exception as e:
        errors.append(f"리포트 생성 API 호출 실패: {e}")
        # 최소한의 폴백 리포트 (요구사항: 프로그램이 죽지 않고 결과를 남겨야 함)
        return (
            f"# {recommendation.get('recommended_city', '여행지')} 여행 리포트 (생성 실패)\n\n"
            f"리포트 생성 중 오류가 발생했습니다: {e}\n\n"
            f"## 원본 추천 정보\n"
            f"- 날씨: {recommendation.get('weather')}\n"
            f"- 행사: {', '.join(recommendation.get('events', []))}\n"
            f"- 이유: {recommendation.get('reason')}\n\n"
            f"## 맛집 리스트\n{restaurant_text}\n"
        )
