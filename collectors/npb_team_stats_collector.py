"""
npb_team_stats_collector.py
NPB 팀별 시즌 승률을 npb.jp 공식 순위 페이지(영문판)에서 가져온다.

*** 확인된 사항 ***
npb.jp의 /scores/ 하위 경로는 접속이 막혀있었지만(403), 이 순위 페이지
(/bis/eng/{season}/stats/std_c.html, std_p.html)는 실제로 접속되고 정상적인
표가 나오는 것까지 확인했다 (2026-07-16 기준 실제 순위 데이터로 확인함).

이 표에는 승/패/승률까지만 있고 "최근 10경기 승률"과 "평균 득점/실점"은 없다.
그 두 값은 일단 비워둔다 (predictor_v1이 값이 없으면 중립값으로 처리하므로
예측 자체는 정상 작동하지만, 최근 폼 반영은 못 함 — 나중에 다른 페이지를 찾아
추가하면 더 좋아질 부분).

사용법:
    python collectors/npb_team_stats_collector.py --season 2026
"""

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team_season_stats

REQUEST_TIMEOUT = 15
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

RANK_URLS = [
    "https://npb.jp/bis/eng/{season}/stats/std_c.html",   # 센트럴리그
    "https://npb.jp/bis/eng/{season}/stats/std_p.html",   # 퍼시픽리그
]

# 순위표의 영문 팀명 -> team_name_map.py의 NPB_JP_TO_KR과 맞춘 일본어 정식명칭
ENG_TO_JP = {
    "Hanshin Tigers": "阪神タイガース",
    "Yomiuri Giants": "読売ジャイアンツ",
    "Tokyo Yakult Swallows": "東京ヤクルトスワローズ",
    "YOKOHAMA DeNA BAYSTARS": "横浜DeNAベイスターズ",
    "Hiroshima Toyo Carp": "広島東洋カープ",
    "Chunichi Dragons": "中日ドラゴンズ",
    "Fukuoka SoftBank Hawks": "福岡ソフトバンクホークス",
    "Hokkaido Nippon-Ham Fighters": "北海道日本ハムファイターズ",
    "ORIX Buffaloes": "オリックス・バファローズ",
    "Tohoku Rakuten Golden Eagles": "東北楽天ゴールデンイーグルス",
    "Saitama Seibu Lions": "埼玉西武ライオンズ",
    "Chiba Lotte Marines": "千葉ロッテマリーンズ",
}


def fetch_rank_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_team_rows(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table")
    if not table:
        return []

    rows = []
    for tr in table.select("tr"):
        cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
        if len(cells) < 6:
            continue
        team_name = cells[0]
        if team_name not in ENG_TO_JP:
            continue  # 헤더 행이거나 모르는 팀명
        try:
            wins = int(cells[2])
            losses = int(cells[3])
            win_pct = float(cells[5])
            rows.append({"team_name": team_name, "wins": wins, "losses": losses, "win_pct": win_pct})
        except (ValueError, IndexError):
            continue
    return rows


def _team_id(jp_name: str) -> str:
    return "npb_" + jp_name.replace(" ", "").replace("　", "")


def collect_and_store(season: int, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    total = 0
    for url_template in RANK_URLS:
        url = url_template.format(season=season)
        try:
            html = fetch_rank_html(url)
        except requests.RequestException as e:
            print(f"[error] NPB 순위 페이지 요청 실패 ({url}): {e}")
            continue

        rows = parse_team_rows(html)
        if not rows:
            print(f"[warn] {url} 에서 팀 순위를 파싱하지 못했습니다.")
            continue

        for r in rows:
            jp_name = ENG_TO_JP[r["team_name"]]
            upsert_team_season_stats(
                conn,
                team_id=_team_id(jp_name),
                season=season,
                wins=r["wins"],
                losses=r["losses"],
                win_pct=r["win_pct"],
            )
            print(f"[ok] {r['team_name']} 저장 완료 (승률 {r['win_pct']})")
            total += 1

    print(f"[info] 총 {total}개 팀 저장 완료")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="NPB 팀 시즌 스탯 수집기")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.season, args.db)


if __name__ == "__main__":
    main()
