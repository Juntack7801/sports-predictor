"""
feature_builder.py
DB에 저장된 games / team_season_stats / probable_pitchers 를 조합해
predictor가 바로 쓸 수 있는 피처 dict를 만든다.

사용법:
    from features.feature_builder import build_features
    features = build_features(conn, game_id="746321", season=2026)
"""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
from db.db import get_game, get_team_season_stats, get_probable_pitchers, get_team_name, find_market_ou_line


def build_features(conn, game_id: str, season: int) -> dict:
    game = get_game(conn, game_id)
    if not game:
        raise ValueError(f"game_id={game_id} 가 games 테이블에 없습니다. collector를 먼저 실행하세요.")

    home_id = game["home_team_id"]
    away_id = game["away_team_id"]

    home_stats = get_team_season_stats(conn, home_id, season) or {}
    away_stats = get_team_season_stats(conn, away_id, season) or {}
    pitchers = get_probable_pitchers(conn, game_id)

    home_pitcher = pitchers.get("home", {})
    away_pitcher = pitchers.get("away", {})

    home_name = get_team_name(conn, home_id)
    away_name = get_team_name(conn, away_id)
    market_ou_line = find_market_ou_line(conn, game["date"], game["league"], home_name, away_name)

    return {
        "game_id": game_id,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "venue_name": game.get("venue_name"),
        "series_game_no": game.get("series_game_no"),
        "series_record_before": game.get("series_record_before"),
        "market_ou_line": market_ou_line,   # 배트맨 실제 배당 라인 (없으면 None -> 자체 계산 라인 사용)

        # 팀 단위 피처
        "home_win_pct_season": home_stats.get("win_pct"),
        "away_win_pct_season": away_stats.get("win_pct"),
        "home_win_pct_split": home_stats.get("home_win_pct"),   # 홈 경기에서의 승률
        "away_win_pct_split": away_stats.get("away_win_pct"),   # 원정 경기에서의 승률
        "home_last10_win_pct": home_stats.get("last10_win_pct"),
        "away_last10_win_pct": away_stats.get("last10_win_pct"),
        "home_runs_scored_avg": home_stats.get("runs_scored_avg"),
        "home_runs_allowed_avg": home_stats.get("runs_allowed_avg"),
        "away_runs_scored_avg": away_stats.get("runs_scored_avg"),
        "away_runs_allowed_avg": away_stats.get("runs_allowed_avg"),

        # 선발투수 피처
        "home_pitcher_name": home_pitcher.get("pitcher_name"),
        "home_pitcher_era_last5": home_pitcher.get("era_last5"),
        "home_pitcher_era_season": home_pitcher.get("era_season"),
        "home_pitcher_days_rest": home_pitcher.get("days_rest"),
        "away_pitcher_name": away_pitcher.get("pitcher_name"),
        "away_pitcher_era_last5": away_pitcher.get("era_last5"),
        "away_pitcher_era_season": away_pitcher.get("era_season"),
        "away_pitcher_days_rest": away_pitcher.get("days_rest"),
    }
