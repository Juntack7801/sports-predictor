"""
npb_collector.py
공식 npb.jp는 접속이 막혀있어서(403 Forbidden, 직접 확인함), 대신
Sergei Borisov씨가 운영하는 NPB 일정 사이트(sborisov.brinkster.net)를 사용한다.
이 사이트는 자바스크립트 없이 순수 HTML로 바로 보여주는 예전 방식이라
requests만으로 충분하다 (Selenium 불필요).

*** 중요 안내 ***
이 사이트는 "오늘/어제/내일" 3개 페이지만 제공한다 (임의의 날짜 조회 불가).
그래서 target_date가 오늘/어제/내일이 아니면 수집할 수 없다.
또한 이 사이트는 "일정"만 주고 "최종 스코어"는 안 준다 — 그래서 NPB는
아직 경기 결과(적중여부) 확인이 안 된다. 스코어 소스는 나중에 따로 찾아야 함.

이 collector는 실제 페이지 내용(2026-08-01/08-02 확인)을 기준으로 작성했지만,
원본 HTML의 정확한 태그 구조까지는 못 보고 렌더링된 내용만 보고 정규식으로
짠 것이라, 실제로 돌려서 "경기를 찾지 못했다"고 뜨면 정규식(GAME_PATTERN)을
조정해야 할 수 있다.

사용법:
    python collectors/npb_collector.py
    python collectors/npb_collector.py --date 2026-08-01
"""

import argparse
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team, upsert_game

LEAGUE = "NPB"
REQUEST_TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE_URL = "http://sborisov.brinkster.net"

# 팀 약자 -> npb.jp식 일본어 정식명칭 (team_name_map.py의 NPB_JP_TO_KR과 반드시 맞춰야 함)
ABBR_TO_JP = {
    "YG": "読売ジャイアンツ",
    "HT": "阪神タイガース",
    "CD": "中日ドラゴンズ",
    "YS": "東京ヤクルトスワローズ",
    "YBS": "横浜DeNAベイスターズ",
    "HC": "広島東洋カープ",
    "FSH": "福岡ソフトバンクホークス",
    "NHF": "北海道日本ハムファイターズ",
    "RGE": "東北楽天ゴールデンイーグルス",
    "SL": "埼玉西武ライオンズ",
    "CLM": "千葉ロッテマリーンズ",
    "OB": "オリックス・バファローズ",
}

# 예: '<a href="...">YBS</a> at <a href="...">YG</a>   18:00 Tokyo Dome   <i>...'
GAME_PATTERN = re.compile(
    r'<a[^>]*>([A-Z]{2,3})</a>\s+at\s+<a[^>]*>([A-Z]{2,3})</a>\s+(\d{1,2}:\d{2})\s+([^<]+?)\s*(?:<i>|<br)',
    re.IGNORECASE,
)


def _page_for_date(target_date: str) -> str | None:
    """오늘/어제/내일 중 하나에 해당하면 그 페이지 이름을, 아니면 None을 반환."""
    today = date.today()
    target = date.fromisoformat(target_date)
    diff = (target - today).days
    if diff == 0:
        return "today.asp"
    if diff == -1:
        return "yesterday.asp"
    if diff == 1:
        return "tomorrow.asp"
    return None


def fetch_html(page: str) -> str:
    resp = requests.get(f"{BASE_URL}/{page}", headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def parse_games(html: str) -> list[dict]:
    games = []
    for m in GAME_PATTERN.finditer(html):
        away_abbr, home_abbr, time_text, venue = m.groups()
        away_name = ABBR_TO_JP.get(away_abbr.upper())
        home_name = ABBR_TO_JP.get(home_abbr.upper())
        if not away_name or not home_name:
            continue  # 모르는 약자 (팜리그 등 다른 표일 수 있음) -> 건너뜀
        games.append({
            "away_name": away_name,
            "home_name": home_name,
            "time": time_text.strip(),
            "venue": venue.strip(),
        })
    return games


def _team_id(name: str) -> str:
    return "npb_" + name.replace(" ", "").replace("　", "")


def collect_and_store(target_date: str, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    page = _page_for_date(target_date)
    if page is None:
        print(f"[warn] 이 NPB 소스는 오늘/어제/내일만 지원합니다 (요청한 날짜: {target_date}).")
        return

    try:
        html = fetch_html(page)
    except requests.RequestException as e:
        print(f"[error] NPB 일정 페이지 요청 실패: {e}")
        return

    games = parse_games(html)
    if not games:
        print(f"[warn] {target_date} NPB 경기를 찾지 못했습니다.")
        print("[hint] 사이트 구조가 바뀌었을 수 있습니다. GAME_PATTERN 정규식을 조정해야 할 수 있어요.")
        return

    for i, g in enumerate(games):
        home_id = _team_id(g["home_name"])
        away_id = _team_id(g["away_name"])
        game_id = f"npb_{target_date}_{i}"
        game_datetime = f"{target_date} {g['time']}:00"

        upsert_team(conn, home_id, LEAGUE, g["home_name"])
        upsert_team(conn, away_id, LEAGUE, g["away_name"])
        upsert_game(
            conn,
            game_id=game_id,
            league=LEAGUE,
            date=target_date,
            home_team_id=home_id,
            away_team_id=away_id,
            venue_name=g["venue"],
            status="Scheduled",  # 이 소스는 최종 스코어를 안 줘서 항상 Scheduled로 저장됨
            game_datetime_utc=game_datetime,
        )
        print(f"[ok] {g['away_name']} @ {g['home_name']} ({g['time']}, {g['venue']}) 저장 완료")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="NPB 오늘 경기 수집기")
    parser.add_argument("--date", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.date, args.db)


if __name__ == "__main__":
    main()
