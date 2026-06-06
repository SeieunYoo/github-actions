"""Jumpit (jumpit.co.kr) job listing fetcher.

사람인 계열의 점핏 비공식 API를 호출한다. 응답 스키마는 사이트
변경에 따라 자주 바뀌니 None-safe 하게 파싱한다.
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

log = logging.getLogger(__name__)

API = "https://jumpit-api.saramin.co.kr/api/positions"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": "https://www.jumpit.co.kr/",
    "Origin": "https://www.jumpit.co.kr",
}


def fetch(limit: int = 50) -> list[dict]:
    params = {
        "sort": "rsp_rate",
        "page": 1,
        "size": limit,
    }
    resp = requests.get(API, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    payload = resp.json()
    result = payload.get("result") or payload
    positions = result.get("positions") or result.get("list") or []
    return [_normalize(item) for item in positions if item]


def _normalize(item: dict) -> dict:
    job_id = item.get("id") or item.get("positionId")
    company = item.get("companyName") or (item.get("company") or {}).get("name", "")
    title = item.get("title") or item.get("positionName", "")
    locations = item.get("locations") or item.get("workingArea") or []
    if isinstance(locations, str):
        locations = [locations]
    skills = item.get("techStacks") or item.get("jobCategories") or []
    skills = [s if isinstance(s, str) else s.get("name", "") for s in skills]
    return {
        "source": "jumpit",
        "id": f"jumpit-{job_id}",
        "company": company,
        "title": title,
        "location": ", ".join(locations),
        "min_years": item.get("minCareer"),
        "max_years": item.get("maxCareer"),
        "skills": [s for s in skills if s],
        "url": f"https://www.jumpit.co.kr/position/{job_id}" if job_id else "",
        "raw_text": " ".join(filter(None, [title, company, *skills])),
    }


def iter_jobs(limit: int = 50, options: dict | None = None) -> Iterable[dict]:
    try:
        yield from fetch(limit=limit)
    except Exception as e:  # noqa: BLE001
        log.error("jumpit fetch failed: %s", e)
        raise
