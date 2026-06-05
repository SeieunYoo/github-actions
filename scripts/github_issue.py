"""GitHub Issue 생성 헬퍼.

REST API v3 를 직접 호출한다. Actions 환경의 GITHUB_TOKEN 만 있으면
별도 의존성 없이 동작한다.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import urllib.request

log = logging.getLogger(__name__)

ISSUE_LABEL = "job-scan"


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    token = os.environ["GITHUB_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]  # "owner/name"
    url = f"https://api.github.com/repos/{repo}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode() or "{}")


def render_body(jobs: list[dict]) -> str:
    lines = [
        "오늘 새로 올라온 채용 공고입니다.",
        "지원하고 싶은 공고 옆 체크박스를 체크해 주세요.",
        "",
        "체크된 공고는 다음 자동 지원 워크플로우에서 처리됩니다.",
        "",
        "---",
        "",
    ]
    for job in jobs:
        skills = ", ".join(job.get("skills") or [])
        years = _format_years(job.get("min_years"), job.get("max_years"))
        meta = " · ".join(filter(None, [job.get("location"), years, skills]))
        lines.append(
            f"- [ ] **[{job['company']}]** [{job['title']}]({job['url']}) "
            f"<sub>({job['source']})</sub>"
        )
        if meta:
            lines.append(f"  - {meta}")
    lines += ["", "<!-- generated-by: job-scan -->"]
    return "\n".join(lines)


def _format_years(lo, hi) -> str:
    if lo is None and hi is None:
        return ""
    if lo == 0 and (hi is None or hi == 0):
        return "신입"
    if lo is None:
        return f"~{hi}년"
    if hi is None:
        return f"{lo}년~"
    return f"{lo}~{hi}년"


def create_issue(jobs: list[dict]) -> dict:
    today = dt.date.today().isoformat()
    title = f"[Job Scan] {today} — 새 공고 {len(jobs)}건"
    body = render_body(jobs)
    return _api(
        "/issues",
        method="POST",
        body={"title": title, "body": body, "labels": [ISSUE_LABEL]},
    )


def post_comment(issue_number: int, body: str) -> dict:
    return _api(
        f"/issues/{issue_number}/comments",
        method="POST",
        body={"body": body},
    )


def remove_label(issue_number: int, label: str) -> None:
    try:
        _api(f"/issues/{issue_number}/labels/{label}", method="DELETE")
    except Exception as e:  # noqa: BLE001
        log.warning("could not remove label %s: %s", label, e)
