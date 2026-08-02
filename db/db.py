"""
db.py
SQLite 연결 관리 + 공용 upsert 헬퍼.

사용 예:
    from db.db import get_connection, init_db, upsert_team, upsert_game, upsert_probable_pitcher

    conn = get_connection("sports.db")
    init_db(conn)
    upsert_team(conn, team_id="147", league="MLB", name="New York Yankees", abbreviation="NYY")
"""

import sqlite3
import os
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str = "sports.db") -> sqlite3.Connection:
    """DB 파일에 연결. 없으면 새로 생성됨(파일만, 테이블은 init_db에서)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """schema.sql을 읽어 테이블이 없으면 생성. 이미 만들어진 옛날 DB에는
    새로 추가된 컬럼(ou_line_source 등)을 안전하게 덧붙인다."""
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()

    try:
        conn.execute("ALTER TABLE predictions ADD COLUMN ou_line_source TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 있는 경우

    try:
        conn.execute("ALTER TABLE accuracy_log ADD COLUMN analysis_note TEXT")
        conn.commit()
    except sqlite3.OperationalError:
        pass  # 컬럼이 이미 있는 경우


def upsert_team(
    conn: sqlite3.Connection,
    team_id: str,
    league: str,
    name: str,
    abbreviation: str | None = None,
    park_factor: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO teams (team_id, league, name, abbreviation, park_factor, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(team_id) DO UPDATE SET
            league = excluded.league,
            name = excluded.name,
            abbreviation = COALESCE(excluded.abbreviation, teams.abbreviation),
            park_factor = COALESCE(excluded.park_factor, teams.park_factor),
            updated_at = CURRENT_TIMESTAMP
        """,
        (team_id, league, name, abbreviation, park_factor),
    )
    conn.commit()


def upsert_game(
    conn: sqlite3.Connection,
    game_id: str,
    league: str,
    date: str,
    home_team_id: str,
    away_team_id: str,
    home_score: int | None = None,
    away_score: int | None = None,
    venue_name: str | None = None,
    series_game_no: int | None = None,
    series_record_before: str | None = None,
    status: str | None = None,
    game_datetime_utc: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO games (
            game_id, league, date, home_team_id, away_team_id,
            home_score, away_score, venue_name, series_game_no,
            series_record_before, status, game_datetime_utc, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(game_id) DO UPDATE SET
            home_score = COALESCE(excluded.home_score, games.home_score),
            away_score = COALESCE(excluded.away_score, games.away_score),
            venue_name = COALESCE(excluded.venue_name, games.venue_name),
            series_game_no = COALESCE(excluded.series_game_no, games.series_game_no),
            series_record_before = COALESCE(excluded.series_record_before, games.series_record_before),
            status = COALESCE(excluded.status, games.status),
            game_datetime_utc = COALESCE(excluded.game_datetime_utc, games.game_datetime_utc),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            game_id, league, date, home_team_id, away_team_id,
            home_score, away_score, venue_name, series_game_no,
            series_record_before, status, game_datetime_utc,
        ),
    )
    conn.commit()


def upsert_team_season_stats(
    conn: sqlite3.Connection,
    team_id: str,
    season: int,
    wins: int | None = None,
    losses: int | None = None,
    win_pct: float | None = None,
    home_win_pct: float | None = None,
    away_win_pct: float | None = None,
    last10_win_pct: float | None = None,
    runs_scored_avg: float | None = None,
    runs_allowed_avg: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO team_season_stats (
            team_id, season, wins, losses, win_pct, home_win_pct,
            away_win_pct, last10_win_pct, runs_scored_avg, runs_allowed_avg, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(team_id, season) DO UPDATE SET
            wins = excluded.wins,
            losses = excluded.losses,
            win_pct = excluded.win_pct,
            home_win_pct = excluded.home_win_pct,
            away_win_pct = excluded.away_win_pct,
            last10_win_pct = excluded.last10_win_pct,
            runs_scored_avg = excluded.runs_scored_avg,
            runs_allowed_avg = excluded.runs_allowed_avg,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            team_id, season, wins, losses, win_pct, home_win_pct,
            away_win_pct, last10_win_pct, runs_scored_avg, runs_allowed_avg,
        ),
    )
    conn.commit()


def get_team_name(conn: sqlite3.Connection, team_id: str) -> str | None:
    row = conn.execute("SELECT name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    return row["name"] if row else None


def get_team_season_stats(conn: sqlite3.Connection, team_id: str, season: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM team_season_stats WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()
    return dict(row) if row else None


def get_game(conn: sqlite3.Connection, game_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM games WHERE game_id = ?", (game_id,)).fetchone()
    return dict(row) if row else None


def get_probable_pitchers(conn: sqlite3.Connection, game_id: str) -> dict:
    rows = conn.execute(
        "SELECT * FROM probable_pitchers WHERE game_id = ?", (game_id,)
    ).fetchall()
    return {r["side"]: dict(r) for r in rows}


def upsert_accuracy_log(
    conn: sqlite3.Connection,
    game_id: str,
    predicted_tier: str | None,
    predicted_winner: str | None,   # 'home' | 'away'
    actual_winner: str | None,      # 'home' | 'away'
    winner_correct: int | None,
    predicted_ou: str | None,       # 'over' | 'under'
    actual_total: int | None,
    ou_correct: int | None,
    analysis_note: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO accuracy_log (
            game_id, predicted_tier, predicted_winner, actual_winner, winner_correct,
            predicted_ou, actual_total, ou_correct, analysis_note, checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(game_id) DO UPDATE SET
            predicted_tier = excluded.predicted_tier,
            predicted_winner = excluded.predicted_winner,
            actual_winner = excluded.actual_winner,
            winner_correct = excluded.winner_correct,
            predicted_ou = excluded.predicted_ou,
            actual_total = excluded.actual_total,
            ou_correct = excluded.ou_correct,
            analysis_note = excluded.analysis_note,
            checked_at = CURRENT_TIMESTAMP
        """,
        (
            game_id, predicted_tier, predicted_winner, actual_winner, winner_correct,
            predicted_ou, actual_total, ou_correct, analysis_note,
        ),
    )
    conn.commit()


def upsert_prediction(
    conn: sqlite3.Connection,
    game_id: str,
    win_prob_home: float | None,
    win_prob_away: float | None,
    ou_line: float | None,
    over_prob: float | None,
    under_prob: float | None,
    tier: str,
    model_version: str,
    draw_prob: float | None = None,
    ou_line_source: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO predictions (
            game_id, win_prob_home, win_prob_away, draw_prob, ou_line, ou_line_source,
            over_prob, under_prob, tier, model_version, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(game_id) DO UPDATE SET
            win_prob_home = excluded.win_prob_home,
            win_prob_away = excluded.win_prob_away,
            draw_prob = excluded.draw_prob,
            ou_line = excluded.ou_line,
            ou_line_source = excluded.ou_line_source,
            over_prob = excluded.over_prob,
            under_prob = excluded.under_prob,
            tier = excluded.tier,
            model_version = excluded.model_version,
            created_at = CURRENT_TIMESTAMP
        """,
        (
            game_id, win_prob_home, win_prob_away, draw_prob, ou_line, ou_line_source,
            over_prob, under_prob, tier, model_version,
        ),
    )
    conn.commit()


def upsert_market_ou_line(
    conn: sqlite3.Connection,
    date: str,
    league: str,
    home_name: str,
    away_name: str,
    ou_line: float,
    source: str = "betman",
) -> None:
    conn.execute(
        """
        INSERT INTO market_ou_lines (date, league, home_name, away_name, ou_line, source, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(date, league, home_name, away_name) DO UPDATE SET
            ou_line = excluded.ou_line,
            source = excluded.source,
            updated_at = CURRENT_TIMESTAMP
        """,
        (date, league, home_name, away_name, ou_line, source),
    )
    conn.commit()


def _normalize_team_name(name: str) -> str:
    """팀명 비교용 정규화 — 공백/구단 접미사 제거 후 소문자화."""
    if not name:
        return ""
    return name.replace(" ", "").replace("　", "").lower()


def find_market_ou_line(conn: sqlite3.Connection, target_date: str, league: str, home_name: str, away_name: str) -> float | None:
    """날짜+리그로 후보를 가져온 뒤, 정규화한 팀명이 서로 포함 관계면 매칭.
    배트맨 표기와 우리 쪽 표기가 완전히 같지 않을 수 있어 느슨하게 비교한다."""
    rows = conn.execute(
        "SELECT home_name, away_name, ou_line FROM market_ou_lines WHERE date = ? AND league = ?",
        (target_date, league),
    ).fetchall()

    norm_home = _normalize_team_name(home_name)
    norm_away = _normalize_team_name(away_name)

    for r in rows:
        cand_home = _normalize_team_name(r["home_name"])
        cand_away = _normalize_team_name(r["away_name"])
        home_match = norm_home in cand_home or cand_home in norm_home
        away_match = norm_away in cand_away or cand_away in norm_away
        if home_match and away_match:
            return r["ou_line"]
    return None


def upsert_probable_pitcher(
    conn: sqlite3.Connection,
    game_id: str,
    team_id: str,
    side: str,
    pitcher_id: str | None = None,
    pitcher_name: str | None = None,
    throws: str | None = None,
    era_last5: float | None = None,
    whip_last5: float | None = None,
    days_rest: int | None = None,
    era_season: float | None = None,
    whip_season: float | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO probable_pitchers (
            game_id, team_id, side, pitcher_id, pitcher_name, throws,
            era_last5, whip_last5, days_rest, era_season, whip_season, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(game_id, side) DO UPDATE SET
            team_id = excluded.team_id,
            pitcher_id = excluded.pitcher_id,
            pitcher_name = excluded.pitcher_name,
            throws = COALESCE(excluded.throws, probable_pitchers.throws),
            era_last5 = COALESCE(excluded.era_last5, probable_pitchers.era_last5),
            whip_last5 = COALESCE(excluded.whip_last5, probable_pitchers.whip_last5),
            days_rest = COALESCE(excluded.days_rest, probable_pitchers.days_rest),
            era_season = COALESCE(excluded.era_season, probable_pitchers.era_season),
            whip_season = COALESCE(excluded.whip_season, probable_pitchers.whip_season),
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            game_id, team_id, side, pitcher_id, pitcher_name, throws,
            era_last5, whip_last5, days_rest, era_season, whip_season,
        ),
    )
    conn.commit()
