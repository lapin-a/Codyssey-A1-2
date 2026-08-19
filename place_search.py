"""
place_search.py
----------------
지도/장소 검색 API(Kakao Local) 호출 담당 모듈.

선택 이유:
- Kakao Local Search API는 키워드 검색(`/v2/local/search/keyword.json`)으로
  '도시 + 맛집' 형태의 자연어 쿼리를 그대로 사용할 수 있고,
  응답에 place_name/address_name/x,y/place_url 등 필요한 필드가 모두 포함되어 있다.
- 인증은 REST API 키 1개(Authorization: KakaoAK {key})만으로 간단히 처리 가능하다.

실패 정책:
- 네트워크 오류, 401/403 인증 오류, 쿼터 초과 등 어떤 이유로든 실패하면
  프로그램을 중단시키지 않고 빈 리스트를 반환한다. (errors 리스트에 기록)
"""

import os
from typing import List, Dict

import requests

KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


def search_restaurants(city: str, errors: list, size: int = 5) -> List[Dict]:
    """
    지정한 도시 기준 맛집을 검색한다.
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
            errors.append(f"Kakao Local API 인증 실패 (status={resp.status_code}). 맛집 섹션은 '데이터 없음'으로 처리됩니다.")
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
