"""채용 공고 수집 → 필터 → 중복 제거 → GitHub Issue 생성.

GitHub Actions cron 에서 실행된다. 직접 실행할 때는 GITHUB_TOKEN,
GITHUB_REPOSITORY 환경변수가 필요하다 (Actions 에서는 자동 주입).
"""
from __future__ import annotations

import json
import logging
import pathlib
import sys

import yaml

from sources import jumpit, wanted
from github_issue import create_issue

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("scan")

ROOT = pathlib.Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "keywords.yml"
STATE = ROOT / "state" / "seen.json"
SOURCE_MAP = {"wanted": wanted, "jumpit": jumpit}


def load_config() -> dict:
    with CONFIG.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen() -> set[str]:
    if not STATE.exists():
        return set()
    return set(json.loads(STATE.read_text(encoding="utf-8") or "[]"))


def save_seen(ids: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # 무한 증가 방지: 최근 5000개만 유지
    trimmed = sorted(ids)[-5000:]
    STATE.write_text(json.dumps(trimmed, ensure_ascii=False, indent=2), encoding="utf-8")


def matches(job: dict, cfg: dict) -> bool:
    kw = cfg.get("keywords") or {}
    text = (job.get("raw_text") or "").lower()

    includes = [k.lower() for k in (kw.get("include") or [])]
    if includes and not any(k in text for k in includes):
        return False

    excludes = [k.lower() for k in (kw.get("exclude") or [])]
    if any(k in text for k in excludes):
        return False

    locations = cfg.get("locations") or []
    if locations:
        loc = (job.get("location") or "").lower()
        if not any(l.lower() in loc for l in locations):
            return False

    exp = cfg.get("experience") or {}
    job_min = job.get("min_years")
    job_max = job.get("max_years")
    cfg_min = exp.get("min_years")
    cfg_max = exp.get("max_years")
    # 두 구간이 겹치는지 검사
    if job_min is not None and cfg_max is not None and job_min > cfg_max:
        return False
    if job_max is not None and cfg_min is not None and job_max < cfg_min:
        return False

    return True


def collect(cfg: dict) -> list[dict]:
    enabled = (cfg.get("sources") or {})
    options = (cfg.get("source_options") or {})
    jobs: list[dict] = []
    for name, mod in SOURCE_MAP.items():
        if not enabled.get(name):
            continue
        try:
            fetched = list(mod.iter_jobs(limit=100, options=options.get(name) or {}))
            log.info("fetched %d jobs from %s", len(fetched), name)
            jobs.extend(fetched)
        except Exception as e:  # noqa: BLE001
            log.warning("source %s failed, skipping: %s", name, e)
    return jobs


def main() -> int:
    cfg = load_config()
    seen = load_seen()

    all_jobs = collect(cfg)
    log.info("total fetched: %d", len(all_jobs))

    new_matches = []
    for job in all_jobs:
        if job["id"] in seen:
            continue
        if matches(job, cfg):
            new_matches.append(job)

    log.info("new matching jobs: %d", len(new_matches))

    cap = cfg.get("max_per_run") or 30
    new_matches = new_matches[:cap]

    if not new_matches:
        log.info("no new jobs, skipping issue creation")
        # 새 공고가 없어도 seen 은 업데이트 (소스가 우리에게 보여준 모든 id 기록)
        save_seen(seen | {j["id"] for j in all_jobs})
        return 0

    issue = create_issue(new_matches)
    log.info("created issue #%s: %s", issue.get("number"), issue.get("html_url"))

    save_seen(seen | {j["id"] for j in all_jobs})
    return 0


if __name__ == "__main__":
    sys.exit(main())
