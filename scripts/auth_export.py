"""로컬에서 1회 실행하는 로그인 세션 캡처 도구.

사용법:
    pip install playwright && playwright install chromium
    python scripts/auth_export.py wanted
    python scripts/auth_export.py jumpit

브라우저가 열리면 직접 로그인한 뒤 터미널에서 ENTER 를 누른다.
storage_state 가 secrets/<source>_state.json 으로 저장되고,
base64 문자열도 같이 출력된다. 그 base64 값을 GitHub repo Secret 으로
등록한다:
    wanted -> WANTED_STORAGE_STATE
    jumpit -> JUMPIT_STORAGE_STATE
"""
from __future__ import annotations

import base64
import pathlib
import sys

LOGIN_URL = {
    "wanted": "https://www.wanted.co.kr/login",
    "jumpit": "https://www.jumpit.co.kr/login",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in LOGIN_URL:
        print("usage: python scripts/auth_export.py <wanted|jumpit>")
        return 2
    source = sys.argv[1]

    from playwright.sync_api import sync_playwright

    out_dir = pathlib.Path("secrets")
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{source}_state.json"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(LOGIN_URL[source])
        print(f"\n[{source}] 브라우저에서 로그인하세요.")
        input("로그인 완료 후 이 터미널에서 ENTER 를 누르세요... ")
        context.storage_state(path=str(out_path))
        browser.close()

    raw = out_path.read_bytes()
    b64 = base64.b64encode(raw).decode()
    print(f"\n저장됨: {out_path}")
    print(f"\n아래 값을 GitHub Secret 으로 등록하세요 "
          f"({source.upper()}_STORAGE_STATE):\n")
    print(b64)
    print("\n주의: secrets/ 폴더는 .gitignore 에 포함되어 커밋되지 않습니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
