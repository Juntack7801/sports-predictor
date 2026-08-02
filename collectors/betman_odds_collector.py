"""
betman_odds_collector.py
스포츠토토 배트맨(betman.co.kr) 공개 경기정보 페이지에서
오늘 야구(MLB/KBO/NPB) 경기의 실제 언더/오버 배당 라인을 가져온다.

*** 중요 안내 ***
이 코드를 작성한 환경(샌드박스)은 betman.co.kr 접속이 막혀 있어서
실제 페이지 구조로 테스트하지 못했다. 배트맨은 종목/리그별로 페이지
구성이 다를 수 있고, 로그인 없이 보이는 정보 범위도 다를 수 있다.
아래는 "출발점" 코드이며, 실행해서 경기를 못 찾으면 브라우저 개발자도구로
실제 class명/페이지 구조를 확인해서 SELECTOR_* 값을 조정하면 된다.

배트맨은 공식 스포츠 베팅 사이트이므로 이용약관을 반드시 확인하고,
요청 빈도를 낮게(하루 1~2회) 유지할 것. 개인 참고용으로만 사용할 것.

팀명 매칭: 배트맨에 표기된 팀명(예: "LG트윈스", "NY양키스")이 우리 DB의
팀명(예: "LG 트윈스", "New York Yankees")과 완전히 같지 않을 수 있어서
db.find_market_ou_line()에서 느슨하게(부분 포함) 비교한다. 매칭이 잘 안 되면
_normalize_team_name / find_market_ou_line 쪽 로직을 손보거나, 배트맨 팀명과
우리 팀명을 직접 매핑하는 표를 하나 만드는 게 더 정확할 수 있다.

사용법:
    python collectors/betman_odds_collector.py
    python collectors/betman_odds_collector.py --date 2026-07-29
"""

import argparse
import sys
from datetime import date
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_market_ou_line
from collectors.team_name_map import translate_betman_name

REQUEST_TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 배트맨 경기정보(공개) 페이지. 종목코드는 야구 기준으로 가정 — 실제 값은 사이트에서 확인 필요.
# 종목/리그가 하나의 페이지에 섞여 있을 수 있어, league는 파싱 후 리그명 텍스트로 구분한다.
SCHEDULE_URL = "https://www.betman.co.kr/main/mainPage/gamebuy/gameInfo.do?gmDt={date}"

# *** 아래 선택자들은 실제 페이지에서 확인 후 조정 필요 ***
SELECTOR_GAME_ROW = "tr.game-row"
SELECTOR_LEAGUE_LABEL = "td.league"      # "MLB" / "KBO" / "일본프로야구" 등
SELECTOR_HOME_NAME = "td.home-team"
SELECTOR_AWAY_NAME = "td.away-team"
SELECTOR_OU_LINE = "td.ou-line"          # 예: "8.5" 또는 "언더 8.5/오버 8.5"

LEAGUE_LABEL_MAP = {
    "MLB": "MLB",
    "메이저리그": "MLB",
    "KBO": "KBO",
    "국내프로야구": "KBO",
    "프로야구": "KBO",
    "NPB": "NPB",
    "일본프로야구": "NPB",
}


def fetch_schedule_html(target_date: str) -> str:
    date_str = target_date.replace("-", "")
    resp = requests.get(SCHEDULE_URL.format(date=date_str), headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def _map_league(label: str) -> str | None:
    label = label.strip()
    for key, val in LEAGUE_LABEL_MAP.items():
        if key in label:
            return val
    return None


def _extract_ou_number(text: str) -> float | None:
    """'언더 8.5/오버 8.5' 같은 텍스트에서 숫자만 뽑아낸다."""
    import re
    m = re.search(r"(\d+(\.\d+)?)", text)
    return float(m.group(1)) if m else None


def parse_odds(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    rows = soup.select(SELECTOR_GAME_ROW)

    results = []
    for row in rows:
        league_el = row.select_one(SELECTOR_LEAGUE_LABEL)
        home_el = row.select_one(SELECTOR_HOME_NAME)
        away_el = row.select_one(SELECTOR_AWAY_NAME)
        ou_el = row.select_one(SELECTOR_OU_LINE)

        if not (league_el and home_el and away_el and ou_el):
            continue

        league = _map_league(league_el.get_text(strip=True))
        if league is None:
            continue  # 야구 외 종목이거나 인식 못한 리그 표기

        ou_line = _extract_ou_number(ou_el.get_text(strip=True))
        if ou_line is None:
            continue

        results.append({
            "league": league,
            "home_name": home_el.get_text(strip=True),
            "away_name": away_el.get_text(strip=True),
            "ou_line": ou_line,
        })

    return results


def collect_and_store(target_date: str, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    try:
        html = fetch_schedule_html(target_date)
    except requests.RequestException as e:
        print(f"[error] 배트맨 페이지 요청 실패: {e}")
        print("[hint] URL 구조가 바뀌었거나 로그인이 필요한 페이지일 수 있습니다.")
        return

    odds = parse_odds(html)
    if not odds:
        print(f"[warn] {target_date} 배트맨 야구 배당을 찾지 못했습니다.")
        print("[hint] SELECTOR_* 값을 실제 페이지 구조에 맞게 조정하세요 (F12 개발자도구로 확인).")
        return

    for o in odds:
        home_name = translate_betman_name(o["league"], o["home_name"])
        away_name = translate_betman_name(o["league"], o["away_name"])
        upsert_market_ou_line(
            conn,
            date=target_date,
            league=o["league"],
            home_name=home_name,
            away_name=away_name,
            ou_line=o["ou_line"],
        )
        print(f"[ok] [{o['league']}] {away_name} @ {home_name} 언더/오버 라인 {o['ou_line']} 저장 완료")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="배트맨 실제 언더/오버 배당 수집기")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.date, args.db)


if __name__ == "__main__":
    main()
