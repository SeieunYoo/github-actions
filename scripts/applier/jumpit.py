"""점핏 즉시지원 셀렉터.

DOM 구조는 사이트 개편에 따라 바뀔 수 있으니, 첫 실행 후
apply-screenshots 아티팩트를 보고 셀렉터를 조정한다.
"""
from __future__ import annotations

from . import base

SELECTORS = {
    "apply_button": [
        "button:has-text('즉시지원')",
        "button:has-text('지원하기')",
        "a:has-text('즉시지원')",
    ],
    "submit_button": [
        "button:has-text('지원하기'):not(:has-text('취소'))",
        "button:has-text('제출')",
        "button:has-text('지원 완료')",
    ],
    "success_text": [
        "지원이 완료",
        "지원완료",
        "지원해주셔서",
    ],
    "already_applied_text": [
        "이미 지원",
        "지원완료된",
    ],
}


def apply(page, job: dict) -> dict:
    return base.apply_job(page, job, SELECTORS)
