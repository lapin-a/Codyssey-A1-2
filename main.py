#!/usr/bin/env python3
"""
main.py
-------
여행 리포트 생성 CLI 프로그램.

사용법:
    python main.py -date "2026-08-13"

동작 흐름:
    1) LLM API로 날짜 기반 국내 여행지 1차 추천 (JSON, 실패 시 1회 재시도)
    2) 추천 도시 기준 Kakao Local API로 맛집 검색 (실패해도 프로그램은 계속 진행)
    3) 1차 추천 + 맛집 목록을 종합해 LLM API로 최종 Markdown 리포트 생성
    4) results/ 폴더에 원본 데이터 JSON과 리포트 MD를 저장

동일 날짜로 재실행 시, results/{date}_data.json이 이미 존재하면
API를 재호출하지 않고 저장된 데이터로 리포트만 재생성한다(캐싱).
"""

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

import llm_client
import place_search

RESULTS_DIR = "results"


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
    # 잘못된 인자가 들어오면 argparse가 자동으로 usage를 출력하고 exit(2) 한다.
    return parser.parse_args()


def validate_date(date_str: str):
    """
    날짜 형식(YYYY-MM-DD)이 잘못되면 usage를 출력하고 정상 종료(exit code 0)한다.
    """
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f'[오류] 날짜 형식이 올바르지 않습니다: "{date_str}"')
        print('사용법: python main.py -date "YYYY-MM-DD"')
        print('예시  : python main.py -date "2026-08-13"')
        sys.exit(0)


def check_required_env(errors: list) -> bool:
    """
    필수 API 키가 없으면 즉시 종료 + 설정 방법 안내.
    (OPENAI_API_KEY는 필수, KAKAO_API_KEY는 없어도 프로그램은 동작 가능하므로
     여기서는 필수 키인 OPENAI_API_KEY만 즉시 종료 대상으로 검사한다.)
    """
    if not os.getenv("OPENAI_API_KEY"):
        print("[오류] OPENAI_API_KEY 환경변수가 설정되지 않았습니다.")
        print()
        print("설정 방법:")
        print("  1) 프로젝트 루트에 .env 파일을 만들고 아래처럼 작성하세요:")
        print('     OPENAI_API_KEY="sk-..."')
        print('     KAKAO_API_KEY="your-kakao-rest-api-key"')
        print("  2) 또는 셸에서 환경변수로 직접 지정하세요:")
        print('     export OPENAI_API_KEY="sk-..."')
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
        recommendation = llm_client.get_recommendation(date_str, errors)

        if recommendation is None:
            print("[오류] 1차 추천 생성에 실패했습니다. 프로그램을 종료합니다.")
            # 실패해도 errors를 남긴 결과 파일은 저장한다.
            save_results(
                date_str,
                {"date": date_str, "recommendation": None, "restaurants": [], "errors": errors},
                "# 리포트 생성 실패\n\n1차 추천 단계에서 오류가 발생해 리포트를 생성할 수 없었습니다.\n",
            )
            sys.exit(1)

        city = recommendation.get("recommended_city", "")
        print(f'맛집 검색 중... (기준 도시: "{city}")')
        restaurants = place_search.search_restaurants(city, errors)

    print("리포트 생성 중... (LLM API)")
    report_md = llm_client.generate_report(recommendation, restaurants, date_str, errors)

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
