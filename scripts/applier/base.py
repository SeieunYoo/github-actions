"""사이트 공통 지원 로직.

간편지원(이력서 첨부 없이 클릭만으로 제출 가능한 공고)만 자동 제출하고,
자소서/추가 질문/파일 업로드가 필요하면 안전하게 스킵한다.

각 사이트 모듈은 SELECTORS dict 를 정의해서 이 함수들에 넘긴다.
실제 DOM 구조는 사이트 업데이트에 따라 바뀌므로, 후보 셀렉터를
여러 개 두고 가장 먼저 잡히는 것을 사용한다.
"""
from __future__ import annotations

import logging
import pathlib

log = logging.getLogger(__name__)

SHOT_DIR = pathlib.Path("apply-screenshots")

# 자소서/추가 입력이 필요하다고 판단할 신호들
ESSAY_SIGNALS = [
    "자기소개",
    "자소서",
    "지원 동기",
    "사전 질문",
    "추가 질문",
    "추가 정보",
    "포트폴리오를 첨부",
]


def _screenshot(page, name: str) -> None:
    try:
        SHOT_DIR.mkdir(exist_ok=True)
        page.screenshot(path=str(SHOT_DIR / f"{name}.png"), full_page=True)
    except Exception as e:  # noqa: BLE001
        log.debug("screenshot failed: %s", e)


def _first_visible(page, selectors: list[str], timeout: int = 4000):
    """후보 셀렉터 중 화면에 보이는 첫 요소를 반환. 없으면 None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:  # noqa: BLE001
            continue
    return None


def _requires_essay(page) -> bool:
    """지원 폼에 자소서/추가 질문/필수 파일 업로드가 있는지 검사."""
    # 1) 텍스트 신호
    body_text = ""
    try:
        body_text = page.inner_text("body", timeout=2000)
    except Exception:  # noqa: BLE001
        pass
    if any(sig in body_text for sig in ESSAY_SIGNALS):
        return True
    # 2) 빈 채로 둘 수 없는 textarea
    try:
        if page.locator("textarea").count() > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    # 3) 파일 업로드 input (이력서 재첨부 요구)
    try:
        if page.locator("input[type=file]").count() > 0:
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def apply_job(page, job: dict, selectors: dict) -> dict:
    """단일 공고 지원 시도. 결과 dict 반환.

    status: applied | needs_resume | already_applied | no_button | failed
    """
    url = job["url"]
    slug = job["id"]
    result = {"job": job, "status": "failed", "reason": ""}

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(1500)
        _screenshot(page, f"{slug}-1-loaded")

        # 이미 지원한 공고인지
        body_text = page.inner_text("body", timeout=3000)
        if any(s in body_text for s in selectors.get("already_applied_text", [])):
            result.update(status="already_applied", reason="이미 지원한 공고")
            return result

        apply_btn = _first_visible(page, selectors["apply_button"])
        if apply_btn is None:
            result.update(status="no_button", reason="지원 버튼을 찾지 못함")
            _screenshot(page, f"{slug}-no-button")
            return result

        apply_btn.click()
        page.wait_for_timeout(2000)
        _screenshot(page, f"{slug}-2-after-apply-click")

        if _requires_essay(page):
            result.update(
                status="needs_resume",
                reason="자소서/추가 입력 필요 — 수동 지원 권장",
            )
            return result

        submit_btn = _first_visible(page, selectors["submit_button"], timeout=4000)
        if submit_btn is None:
            # 버튼 클릭만으로 제출되는 케이스도 있으니, 성공 신호 먼저 확인
            if _success(page, selectors):
                result.update(status="applied", reason="지원 완료")
            else:
                result.update(status="needs_resume", reason="제출 버튼 없음 — 수동 확인 필요")
            return result

        submit_btn.click()
        page.wait_for_timeout(2500)
        _screenshot(page, f"{slug}-3-after-submit")

        if _success(page, selectors):
            result.update(status="applied", reason="지원 완료")
        else:
            result.update(status="failed", reason="제출 후 성공 신호 미확인")
        return result

    except Exception as e:  # noqa: BLE001
        log.warning("apply failed for %s: %s", url, e)
        _screenshot(page, f"{slug}-error")
        result.update(status="failed", reason=f"{type(e).__name__}: {e}")
        return result


def _success(page, selectors: dict) -> bool:
    try:
        body_text = page.inner_text("body", timeout=3000)
    except Exception:  # noqa: BLE001
        return False
    return any(s in body_text for s in selectors.get("success_text", []))
