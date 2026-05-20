"""체크된 공고에 대해 간편지원 자동 제출.

트리거: 이슈에 'ready-to-apply' 라벨이 붙으면 (apply-approved.yml).
이슈 본문에서 체크([x])된 항목을 파싱해, 아직 지원하지 않은 공고에 대해
사이트별 storage_state 로 로그인한 Playwright 세션으로 간편지원을 시도한다.

자소서/추가 입력이 필요한 공고는 자동 제출하지 않고 이슈 코멘트로 안내한다.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import pathlib
import re
import sys
import tempfile

from applier import jumpit, wanted
import github_issue as gh

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("apply")

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPLIED = ROOT / "state" / "applied.json"

APPLIER_MAP = {"wanted": wanted, "jumpit": jumpit}
STATE_ENV = {"wanted": "WANTED_STORAGE_STATE", "jumpit": "JUMPIT_STORAGE_STATE"}

ITEM_RE = re.compile(
    r"-\s*\[[xX]\]\s+\*\*\[(?P<company>.+?)\]\*\*\s+"
    r"\[(?P<title>.+?)\]\((?P<url>[^)]+)\)\s+<sub>\((?P<source>\w+)\)</sub>"
)


def load_event() -> dict:
    path = os.environ.get("GITHUB_EVENT_PATH")
    if not path:
        raise SystemExit("GITHUB_EVENT_PATH not set (run inside GitHub Actions)")
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def parse_checked(body: str) -> list[dict]:
    jobs = []
    for m in ITEM_RE.finditer(body or ""):
        jobs.append(
            {
                "id": _slug(m.group("url")),
                "company": m.group("company"),
                "title": m.group("title"),
                "url": m.group("url"),
                "source": m.group("source").lower(),
            }
        )
    return jobs


def _slug(url: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", url).strip("-")[-60:]


def load_applied() -> dict:
    if not APPLIED.exists():
        return {}
    return json.loads(APPLIED.read_text(encoding="utf-8") or "{}")


def save_applied(data: dict) -> None:
    APPLIED.parent.mkdir(parents=True, exist_ok=True)
    APPLIED.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_storage_state(source: str) -> str | None:
    b64 = os.environ.get(STATE_ENV[source])
    if not b64:
        return None
    raw = base64.b64decode(b64)
    fd, path = tempfile.mkstemp(suffix=f"-{source}-state.json")
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return path


def run_source(source: str, jobs: list[dict]) -> list[dict]:
    from playwright.sync_api import sync_playwright

    state_path = _write_storage_state(source)
    results = []
    if state_path is None:
        for job in jobs:
            results.append(
                {"job": job, "status": "no_session",
                 "reason": f"{STATE_ENV[source]} secret 미설정"}
            )
        return results

    applier = APPLIER_MAP[source]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=state_path)
        page = context.new_page()
        for job in jobs:
            log.info("applying: [%s] %s", job["company"], job["title"])
            results.append(applier.apply(page, job))
        browser.close()
    return results


STATUS_LABEL = {
    "applied": "✅ 지원 완료",
    "needs_resume": "📝 자소서 필요 (수동)",
    "already_applied": "↩️ 이미 지원함",
    "no_button": "❓ 지원 버튼 없음 (수동)",
    "no_session": "🔑 세션 없음",
    "failed": "⚠️ 실패",
}


def render_comment(results: list[dict]) -> str:
    lines = ["### 자동 지원 결과", ""]
    order = ["applied", "needs_resume", "already_applied", "no_button", "no_session", "failed"]
    by_status: dict[str, list[dict]] = {}
    for r in results:
        by_status.setdefault(r["status"], []).append(r)
    for status in order:
        items = by_status.get(status)
        if not items:
            continue
        lines.append(f"**{STATUS_LABEL.get(status, status)}** ({len(items)})")
        for r in items:
            job = r["job"]
            note = f" — {r['reason']}" if r.get("reason") else ""
            lines.append(f"- [{job['company']}] [{job['title']}]({job['url']}){note}")
        lines.append("")
    lines.append("<!-- generated-by: job-apply -->")
    return "\n".join(lines)


def main() -> int:
    event = load_event()
    issue = event["issue"]
    issue_number = issue["number"]
    body = issue.get("body", "")

    checked = parse_checked(body)
    log.info("checked items: %d", len(checked))

    applied = load_applied()
    todo = [j for j in checked if j["url"] not in applied]
    log.info("not-yet-applied: %d", len(todo))

    if not todo:
        gh.post_comment(issue_number, "체크된 공고 중 새로 지원할 항목이 없습니다.")
        gh.remove_label(issue_number, "ready-to-apply")
        return 0

    by_source: dict[str, list[dict]] = {}
    for job in todo:
        by_source.setdefault(job["source"], []).append(job)

    all_results = []
    for source, jobs in by_source.items():
        if source not in APPLIER_MAP:
            for job in jobs:
                all_results.append(
                    {"job": job, "status": "failed", "reason": f"미지원 소스: {source}"}
                )
            continue
        all_results.extend(run_source(source, jobs))

    # applied.json 갱신: 성공/이미지원만 기록 (실패는 재시도 여지 남김)
    import datetime as dt
    now = dt.datetime.utcnow().isoformat() + "Z"
    for r in all_results:
        if r["status"] in ("applied", "already_applied"):
            applied[r["job"]["url"]] = {"status": r["status"], "at": now}
    save_applied(applied)

    gh.post_comment(issue_number, render_comment(all_results))
    gh.remove_label(issue_number, "ready-to-apply")
    log.info("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
