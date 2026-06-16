#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
위시켓 프론트엔드 프로젝트 스크래퍼 + 모니터

하는 일
--------
1. 강남구 / 성남시 분당구 / 용인시 수지구 의 개발·웹 프로젝트를 긁어옴 (외주 + 상주)
2. 외주(도급)는 위시켓에 '역할' 필터가 없으므로, 받아온 뒤 프론트엔드 키워드로 후처리
   (상주는 r=frontend_developer 로 서버에서 이미 걸러짐)
3. project id 로 중복 제거 → CSV / JSON 저장
4. 재실행하면 이전 스냅샷과 비교해 "신규로 올라온 프로젝트"만 따로 표시 = 모니터링

필요 패키지
-----------
    pip install requests beautifulsoup4 lzstring

사용
----
    python wishket_frontend_monitor.py          # 1회 수집 + 신규 비교
    (cron / 작업 스케줄러에 걸면 자동 모니터링)

주의
----
- 요청 사이 딜레이(REQUEST_DELAY)를 둬서 서버에 부담을 안 주도록 함. 너무 줄이지 말 것.
- 개인 구직용 수집 수준으로만 사용. 대량/상업적 재배포는 위시켓 약관 위반 소지가 있음.
- 파싱이 빗나가면(필드가 비면) CARD 하나의 HTML을 떠서 셀렉터를 조정하면 됨.
"""

import os
import re
import csv
import json
import time
import sys

import requests
from bs4 import BeautifulSoup
from lzstring import LZString

# ─────────────────────────────────────────────────────────────
# 설정 (여기만 바꾸면 됨)
# ─────────────────────────────────────────────────────────────

# 위시켓 지역 코드: 강남구=1, 성남시 분당구=91, 용인시 수지구=110
LOC_CODES = "1,91,110"

# 필터: 개발 / 웹 / (상주에 한해) 프론트엔드 역할 / 외주·상주 위치 모두 지정
#   asgg = 외주(도급) 클라이언트 위치
#   esgg = 기간제(상주) 근무 위치
#   r    = 역할 (기간제에만 적용됨. 외주는 아래 키워드로 후처리)
BASE_QUERY = f"c=development&ff=web&r=frontend_developer&asgg={LOC_CODES}&esgg={LOC_CODES}"

# 외주 후처리용 프론트엔드 키워드 (제목·기술스택·역할 어디든 걸리면 매치)
FRONTEND_KEYWORDS = [
    "react", "react native", "reactnative", "next", "nextjs", "next.js",
    "typescript", "javascript", "vue", "nuxt", "svelte", "angular",
    "html", "css", "scss", "tailwind", "redux", "zustand",
    "프론트", "프론트엔드", "퍼블리", "퍼블리셔", "퍼블리싱", "리액트", "뷰",
    "ui/ux", "ui 개발", "웹 퍼블", "frontend", "front-end", "front end",
]

EXCLUDE_CLOSED = True          # 모집 마감된 카드 제외
MAX_PAGES = 100                # 안전 상한 (페이지가 더 없으면 자동 종료)
REQUEST_DELAY = 1.5            # 초. 서버 예의상 1초 이상 권장
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(OUT_DIR, "wishket_frontend.csv")
SNAPSHOT_PATH = os.path.join(OUT_DIR, "wishket_seen_ids.json")

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0 Safari/537.36"),
    "Accept-Language": "ko-KR,ko;q=0.9",
}

lz = LZString()


# ─────────────────────────────────────────────────────────────
# URL 생성
# ─────────────────────────────────────────────────────────────
def build_url(page: int) -> str:
    q = re.sub(r"&?page=\d+", "", BASE_QUERY)
    q = f"{q}&page={page}"
    d = lz.compressToEncodedURIComponent(q)
    return f"https://www.wishket.com/project/?d={d}"


# ─────────────────────────────────────────────────────────────
# 파싱
# ─────────────────────────────────────────────────────────────
def parse_card(card) -> dict:
    """프로젝트 카드 한 개에서 필드 추출 (텍스트 기반이라 클래스 변경에 강함)."""
    text = re.sub(r"[ \t]+", " ", card.get_text("\n"))
    link = card.find("a", href=re.compile(r"/project/\d+/?"))
    if not link:
        return {}
    pid = re.search(r"/project/(\d+)", link["href"]).group(1)

    def grab(pattern, default=""):
        m = re.search(pattern, text)
        return m.group(1).strip() if m else default

    is_term = "기간제" in text          # 상주
    amount = grab(r"(?:예상 금액|월 금액)\s*([\d,]+원|협의 후 결정)")
    period = grab(r"예상 기간\s*(\d+\s*일)")
    start = grab(r"근무 시작일\s*([^\n]+)")
    reg_date = grab(r"등록일자\s*(\d{4}\.\d{2}\.\d{2})")
    deadline = grab(r"마감\s*([^\n]+?전)")
    applicants = grab(r"지원자\s*(\d+명|비공개)")
    # 위치: 시/도 + 시군구
    loc = grab(r"(서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
               r"울산광역시|세종특별자치시|경기도|강원도|충청북도|충청남도|전라북도|"
               r"전라남도|경상북도|경상남도|제주특별자치도)\s*([가-힣]+(?:시\s*[가-힣]+구|구|시|군))?"
               r"", )
    # 위 정규식은 시/도만 잡으니, 시군구까지 한 줄로 재추출
    m = re.search(r"((?:서울특별시|부산광역시|대구광역시|인천광역시|광주광역시|대전광역시|"
                  r"울산광역시|세종특별자치시|경기도|강원도|충청북도|충청남도|전라북도|"
                  r"전라남도|경상북도|경상남도|제주특별자치도)\s+[가-힣]+(?:시 [가-힣]+구|구|시|군))", text)
    location = m.group(1).strip() if m else loc

    return {
        "id": pid,
        "title": link.get_text(strip=True),
        "url": f"https://www.wishket.com/project/{pid}/",
        "type": "상주" if is_term else "외주",
        "amount": amount,
        "period": period,
        "start": start if is_term else "",
        "location": location,
        "reg_date": reg_date,
        "deadline": deadline,
        "applicants": applicants,
        "is_open": "모집 중" in text,
        "_text": text,   # 후처리용 (저장 시 제거)
    }


def is_frontend(card: dict) -> bool:
    """상주는 이미 역할 필터됨 → 통과. 외주는 키워드 매치만 통과."""
    if card["type"] == "상주":
        return True
    blob = card["_text"].lower()
    return any(kw in blob for kw in FRONTEND_KEYWORDS)


# ─────────────────────────────────────────────────────────────
# 수집 루프
# ─────────────────────────────────────────────────────────────
def scrape() -> list:
    session = requests.Session()
    session.headers.update(HEADERS)
    results, seen = {}, set()

    for page in range(1, MAX_PAGES + 1):
        url = build_url(page)
        try:
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[page {page}] 요청 실패: {e}", file=sys.stderr)
            break

        soup = BeautifulSoup(resp.text, "html.parser")
        # 카드 컨테이너: /project/{id}/ 링크를 가진 가장 가까운 블록
        links = soup.find_all("a", href=re.compile(r"/project/\d+/?"))
        page_cards, page_ids = [], set()
        for link in links:
            # 카드 루트로 추정되는 상위 요소까지 올라감
            card = link
            for _ in range(6):
                if card.parent is None:
                    break
                card = card.parent
                if card.find("a", href=re.compile(r"/project/\d+/?")) and \
                   re.search(r"(예상 금액|월 금액|등록일자)", card.get_text()):
                    break
            data = parse_card(card)
            if data and data["id"] not in page_ids:
                page_ids.add(data["id"])
                page_cards.append(data)

        # 더 이상 새 id가 없으면(마지막 페이지) 종료
        new_ids = page_ids - seen
        if not new_ids:
            print(f"[page {page}] 신규 카드 없음 → 종료")
            break
        seen |= page_ids

        for d in page_cards:
            if d["id"] in results:
                continue
            if EXCLUDE_CLOSED and not d["is_open"]:
                continue
            if is_frontend(d):
                results[d["id"]] = d

        print(f"[page {page}] 누적 매치 {len(results)}건")
        time.sleep(REQUEST_DELAY)

    return list(results.values())


# ─────────────────────────────────────────────────────────────
# 저장 + 신규 비교(모니터링)
# ─────────────────────────────────────────────────────────────
def load_seen() -> set:
    if os.path.exists(SNAPSHOT_PATH):
        with open(SNAPSHOT_PATH, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(ids: set):
    with open(SNAPSHOT_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, ensure_ascii=False, indent=0)


def save_csv(rows: list):
    cols = ["id", "title", "type", "amount", "period", "start",
            "location", "reg_date", "deadline", "applicants", "url"]
    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    rows = scrape()
    rows.sort(key=lambda r: r.get("reg_date", ""), reverse=True)

    prev = load_seen()
    cur = {r["id"] for r in rows}
    new = [r for r in rows if r["id"] not in prev]

    save_csv(rows)
    save_seen(cur)

    print("\n" + "=" * 60)
    print(f"총 프론트 매치: {len(rows)}건  (외주 {sum(r['type']=='외주' for r in rows)}, "
          f"상주 {sum(r['type']=='상주' for r in rows)})")
    print(f"CSV 저장: {CSV_PATH}")
    if prev:
        print(f"\n🆕 신규 {len(new)}건:")
        for r in new:
            print(f"  - [{r['type']}] {r['title']}  ({r['amount']}, {r['location']})\n    {r['url']}")
    else:
        print("\n(첫 실행 — 다음부터 신규만 따로 표시됩니다)")


if __name__ == "__main__":
    main()
