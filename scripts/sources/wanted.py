"""Wanted (wanted.co.kr) job listing fetcher.

원티드의 내부 검색 API를 호출한다. 비공식 엔드포인트라 응답 구조가
바뀌면 깨질 수 있으니 실패 시 명시적으로 에러를 던진다.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

log = logging.getLogger(__name__)

API = "https://www.wanted.co.kr/api/v4/jobs"
# 518 = 개발 직군 그룹. 다른 직군이 필요하면 keywords.yml 에 옵션으로 빼낸다.
DEV_GROUP_ID = 518
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.wanted.co.kr/wdlist/518",
    "Origin": "https://www.wanted.co.kr",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
}


def fetch(limit: int = 50, options: dict | None = None) -> list[dict]:
    options = options or {}
    params = {
        "job_group_id": options.get("job_group_id", DEV_GROUP_ID),
        "country": options.get("country", "kr"),
        "locations": options.get("locations", "all"),
        # years 가 [min, max] 리스트면 requests 가 years=min&years=max 로 직렬화한다.
        # wdlist URL 의 years=0&years=4 와 동일한 형태. 없으면 -1(전체).
        "years": options.get("years", -1),
        "limit": limit,
        "offset": 0,
        "job_sort": options.get("job_sort", "job.latest_order"),
    }
    # wdlist URL 의 selected=873&selected=669 → API 의 tag_type_ids 파라미터
    tag_type_ids = options.get("tag_type_ids")
    if tag_type_ids:
        params["tag_type_ids"] = tag_type_ids
    resp = requests.get(API, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    raw = payload.get("data") or payload.get("jobs") or []
    return [_normalize(item) for item in raw if item]


def _normalize(item: dict) -> dict:
    job_id = item.get("id")
    company = (item.get("company") or {}).get("name", "")
    title = item.get("position") or item.get("name", "")
    address = item.get("address") or {}
    location = address.get("location") or address.get("country", "")
    skills = [
        (s.get("title") or s.get("name") or "")
        for s in (item.get("skill_tags") or item.get("skills") or [])
    ]
    return {
        "source": "wanted",
        "id": f"wanted-{job_id}",
        "company": company,
        "title": title,
        "location": location,
        "min_years": item.get("annual_from"),
        "max_years": item.get("annual_to"),
        "skills": [s for s in skills if s],
        "url": f"https://www.wanted.co.kr/wd/{job_id}" if job_id else "",
        "raw_text": " ".join(filter(None, [title, company, *skills])),
    }


def iter_jobs(limit: int = 50, options: dict | None = None) -> Iterable[dict]:
    try:
        yield from fetch(limit=limit, options=options)
    except Exception as e:  # noqa: BLE001
        log.error("wanted fetch failed: %s", e)
        raise
