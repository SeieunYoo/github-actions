#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wishket_frontend.csv 를 읽어 GitHub 이슈에 신규 프로젝트를 누적 기록.

환경변수:
  GITHUB_TOKEN  - repo 권한 있는 PAT 또는 Actions GITHUB_TOKEN
  GITHUB_REPO   - "owner/repo" 형태 (예: SeieunYoo/github-actions)
"""

import csv
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

import requests

ISSUE_TITLE = "위시켓 프론트엔드 모니터링"
CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wishket_frontend.csv")
TOKEN = os.environ["GITHUB_TOKEN"]
REPO  = os.environ["GITHUB_REPO"]
API   = "https://api.github.com"
KST   = timezone(timedelta(hours=9))

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def gh(method, path, **kwargs):
    resp = requests.request(method, f"{API}{path}", headers=HEADERS, **kwargs)
    resp.raise_for_status()
    return resp.json()


def find_or_create_issue() -> int:
    page = 1
    while True:
        issues = gh("GET", f"/repos/{REPO}/issues",
                    params={"state": "open", "per_page": 50, "page": page})
        if not issues:
            break
        for iss in issues:
            if iss["title"] == ISSUE_TITLE:
                return iss["number"]
        page += 1

    created = gh("POST", f"/repos/{REPO}/issues", json={"title": ISSUE_TITLE, "body": "위시켓 프론트엔드 프로젝트 자동 모니터링 이슈입니다."})
    return created["number"]


def get_seen_ids(issue_num: int) -> set:
    page = 1
    last_seen = None
    while True:
        comments = gh("GET", f"/repos/{REPO}/issues/{issue_num}/comments",
                      params={"per_page": 100, "page": page})
        if not comments:
            break
        for c in comments:
            m = re.search(r"<!-- SEEN_IDS: ([^-]+) -->", c["body"])
            if m:
                last_seen = m.group(1).strip()
        page += 1

    if last_seen:
        return set(x.strip() for x in last_seen.split(",") if x.strip())
    return set()


def read_csv() -> list:
    if not os.path.exists(CSV_PATH):
        return None
    with open(CSV_PATH, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def post_comment(issue_num: int, body: str):
    gh("POST", f"/repos/{REPO}/issues/{issue_num}/comments", json={"body": body})


def main():
    now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")

    rows = read_csv()
    issue_num = find_or_create_issue()

    if rows is None:
        post_comment(issue_num, f"⚠️ {now_kst} — wishket_frontend.csv 파일을 찾을 수 없습니다. 스크립트 실행 오류일 수 있습니다.")
        sys.exit(1)

    if len(rows) == 0:
        post_comment(issue_num, f"⚠️ {now_kst} — 수집 결과 0건. 위시켓 응답 오류(403 등) 가능성 있음. SEEN_IDS 미갱신.")
        sys.exit(1)

    cur_ids = {r["id"] for r in rows}
    prev_ids = get_seen_ids(issue_num)
    new_ids = cur_ids - prev_ids
    new_rows = [r for r in rows if r["id"] in new_ids]

    lines = [f"**{now_kst} — 신규 {len(new_rows)}건 / 전체 {len(rows)}건**", ""]

    if new_rows:
        for r in new_rows:
            lines.append(
                f"- [{r['type']}] {r['title']} · {r['location']} · {r['amount']} · "
                f"https://www.wishket.com/project/{r['id']}/"
            )
    else:
        lines.append("신규 없음")

    lines.append("")
    lines.append(f"<!-- SEEN_IDS: {','.join(sorted(cur_ids))} -->")

    post_comment(issue_num, "\n".join(lines))
    print(f"완료: 신규 {len(new_rows)}건 / 전체 {len(rows)}건")


if __name__ == "__main__":
    main()
