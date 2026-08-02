"""
kbo_team_stats_collector.py
KBO 팀별 시즌 승률/평균 득실을 스탯티즈(statiz.co.kr) 팀순위 페이지에서 가져온다.

*** 중요 안내 ***
이 환경은 statiz.co.kr 접속이 막혀 있어 실제 페이지로 테스트하지 못했다.
표(테이블) 구조가 보통 "순위/팀명/경기/승/패/무/승률/득점/실점" 순으로
되어 있다는 일반적인 가정 하에 작성했다. 실행해서 안 맞으면
COLUMN_INDEX 값을 실제 표의 열 순서에 맞게 고치면 된다.

사용법:
    python collectors/kbo_team_stats_collector.py --season 2026
"""

import argparse
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team_season_stats

REQUEST_TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

RANK_URL = "https://statiz.co.kr/team.php?opt=0&sopt=0&year={season}"

# *** 실제 표 열 순서에 맞게 조정 필요 (0부터 시작하는 인덱스) ***
COLUMN_INDEX = {
    "team_name": 1,
    "wins": 3,
    "losses": 4,
    "win_pct": 6,
    "runs_scored": 7,
    "runs_allowed": 8,
}


def fetch_rank_html(season: int) -> str:
    resp = requests.get(RANK_URL.format(season=season), headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_team_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table")
    if not table:
        return []

    rows = []
    for tr in table.select("tr"):
        cells = [td.get_text(strip=True) for td in tr.select("td")]
        if len(cells) < max(COLUMN_INDEX.values()) + 1:
            continue
        try:
            rows.append({
                "team_name": cells[COLUMN_INDEX["team_name"]],
                "wins": int(cells[COLUMN_INDEX["wins"]]),
                "losses": int(cells[COLUMN_INDEX["losses"]]),
                "win_pct": float(cells[COLUMN_INDEX["win_pct"]]),
                "runs_scored_avg": float(cells[COLUMN_INDEX["runs_scored"]]),
                "runs_allowed_avg": float(cells[COLUMN_INDEX["runs_allowed"]]),
            })
        except (ValueError, IndexError):
            continue
    return rows


def _team_id(name: str) -> str:
    return "kbo_" + name.replace(" ", "")


def collect_and_store(season: int, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    try:
        html = fetch_rank_html(season)
    except requests.RequestException as e:
        print(f"[error] KBO 팀순위 페이지 요청 실패: {e}")
        return

    rows = parse_team_rows(html)
    if not rows:
        print("[warn] KBO 팀 순위를 파싱하지 못했습니다. COLUMN_INDEX를 실제 표에 맞게 조정하세요.")
        return

    for r in rows:
        upsert_team_season_stats(
            conn,
            team_id=_team_id(r["team_name"]),
            season=season,
            wins=r["wins"],
            losses=r["losses"],
            win_pct=r["win_pct"],
            runs_scored_avg=r["runs_scored_avg"],
            runs_allowed_avg=r["runs_allowed_avg"],
        )
        print(f"[ok] {r['team_name']} 저장 완료 (승률 {r['win_pct']})")

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="KBO 팀 시즌 스탯 수집기")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.season, args.db)


if __name__ == "__main__":
    main()
