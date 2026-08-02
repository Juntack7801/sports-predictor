"""
mlb_team_stats_collector.py
MLB Stats API에서 팀별 시즌 승률/홈원정 스플릿/최근10경기/평균 득점·실점을
가져와 team_season_stats 테이블에 저장한다.

predictor_v1이 쓰는 핵심 재료(시즌승률, 최근폼, 평균득실)를 만드는 단계.

사용법:
    python collectors/mlb_team_stats_collector.py --season 2026
"""

import argparse
import sys
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_connection, init_db, upsert_team_season_stats

BASE_URL = "https://statsapi.mlb.com/api/v1"
REQUEST_TIMEOUT = 15


def _get(path: str, params: dict | None = None) -> dict:
    resp = requests.get(f"{BASE_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def fetch_standings(season: int) -> dict:
    """AL(103)/NL(104) 전체 순위 + 홈/원정/최근10경기 스플릿 포함."""
    return _get(
        "/standings",
        params={"leagueId": "103,104", "season": season, "hydrate": "team"},
    )


def fetch_team_runs(team_id: int, season: int) -> dict:
    """팀 시즌 득점(hitting.runs), 실점(pitching.runs), 경기수를 가져와 경기당 평균 계산."""
    hitting = _get(f"/teams/{team_id}/stats", params={"stats": "season", "group": "hitting", "season": season})
    pitching = _get(f"/teams/{team_id}/stats", params={"stats": "season", "group": "pitching", "season": season})

    def _extract(data: dict, key: str) -> tuple[float | None, int | None]:
        try:
            stat = data["stats"][0]["splits"][0]["stat"]
            return float(stat.get(key)), int(stat.get("gamesPlayed", 0))
        except (KeyError, IndexError, ValueError, TypeError):
            return None, None

    runs_scored, games_h = _extract(hitting, "runs")
    runs_allowed, games_p = _extract(pitching, "runs")
    games = games_h or games_p

    runs_scored_avg = round(runs_scored / games, 2) if runs_scored is not None and games else None
    runs_allowed_avg = round(runs_allowed / games, 2) if runs_allowed is not None and games else None

    return {"runs_scored_avg": runs_scored_avg, "runs_allowed_avg": runs_allowed_avg}


def _split_record_pct(records: list[dict], split_type: str) -> float | None:
    """standings의 records.splitRecords 배열에서 특정 타입(home/away/lastTen)의 승률 계산."""
    for r in records:
        if r.get("type") == split_type:
            wins, losses = r.get("wins"), r.get("losses")
            if wins is None or losses is None or (wins + losses) == 0:
                return None
            return round(wins / (wins + losses), 3)
    return None


def collect_and_store(season: int, db_path: str) -> None:
    conn = get_connection(db_path)
    init_db(conn)

    standings = fetch_standings(season)
    team_count = 0

    for record_group in standings.get("records", []):
        for team_record in record_group.get("teamRecords", []):
            team_id = str(team_record["team"]["id"])
            wins = team_record.get("wins")
            losses = team_record.get("losses")
            win_pct = round(wins / (wins + losses), 3) if wins is not None and losses is not None and (wins + losses) else None

            split_records = team_record.get("records", {}).get("splitRecords", [])
            home_win_pct = _split_record_pct(split_records, "home")
            away_win_pct = _split_record_pct(split_records, "away")
            last10_win_pct = _split_record_pct(split_records, "lastTen")

            runs = fetch_team_runs(int(team_id), season)

            upsert_team_season_stats(
                conn,
                team_id=team_id,
                season=season,
                wins=wins,
                losses=losses,
                win_pct=win_pct,
                home_win_pct=home_win_pct,
                away_win_pct=away_win_pct,
                last10_win_pct=last10_win_pct,
                runs_scored_avg=runs["runs_scored_avg"],
                runs_allowed_avg=runs["runs_allowed_avg"],
            )
            team_count += 1

    print(f"[ok] {team_count}개 팀 시즌 스탯 저장 완료 (season={season})")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="MLB 팀 시즌 스탯 수집기")
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--db", default="sports.db")
    args = parser.parse_args()
    collect_and_store(args.season, args.db)


if __name__ == "__main__":
    main()
