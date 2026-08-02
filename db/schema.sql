-- sports-predictor DB schema
-- SQLite 기준 (Postgres로 옮길 때는 TEXT->VARCHAR, TIMESTAMP 등만 조정하면 됨)

CREATE TABLE IF NOT EXISTS teams (
    team_id      TEXT PRIMARY KEY,
    league       TEXT NOT NULL,      -- 'KBO' | 'NPB' | 'MLB'
    name         TEXT NOT NULL,
    abbreviation TEXT,
    park_factor  REAL,
    updated_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS games (
    game_id             TEXT PRIMARY KEY,
    league              TEXT NOT NULL,
    date                DATE NOT NULL,
    home_team_id        TEXT NOT NULL,
    away_team_id        TEXT NOT NULL,
    home_score          INTEGER,
    away_score          INTEGER,
    venue_name          TEXT,
    series_game_no      INTEGER,        -- 시리즈 몇 차전
    series_record_before TEXT,          -- 예: '1승0패' (홈팀 기준)
    status              TEXT,           -- scheduled | live | final
    game_datetime_utc   TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (home_team_id) REFERENCES teams(team_id),
    FOREIGN KEY (away_team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS probable_pitchers (
    game_id       TEXT NOT NULL,
    team_id       TEXT NOT NULL,
    side          TEXT NOT NULL,        -- 'home' | 'away'
    pitcher_id    TEXT,
    pitcher_name  TEXT,
    throws        TEXT,                 -- 'L' | 'R'
    era_last5     REAL,
    whip_last5    REAL,
    days_rest     INTEGER,
    era_season    REAL,
    whip_season   REAL,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (game_id, side),
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS team_season_stats (
    team_id           TEXT NOT NULL,
    season            INTEGER NOT NULL,
    wins              INTEGER,
    losses            INTEGER,
    win_pct           REAL,
    home_win_pct      REAL,
    away_win_pct      REAL,
    last10_win_pct    REAL,
    runs_scored_avg   REAL,
    runs_allowed_avg  REAL,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, season),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE IF NOT EXISTS market_ou_lines (
    date          DATE NOT NULL,
    league        TEXT NOT NULL,      -- 'KBO' | 'NPB' | 'MLB'
    home_name     TEXT NOT NULL,      -- 배트맨 사이트에 표기된 팀명 그대로 (매칭용)
    away_name     TEXT NOT NULL,
    ou_line       REAL NOT NULL,      -- 배트맨에 표기된 실제 총점 언더/오버 기준선
    source        TEXT DEFAULT 'betman',
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (date, league, home_name, away_name)
);

CREATE TABLE IF NOT EXISTS predictions (
    game_id       TEXT PRIMARY KEY,
    win_prob_home REAL,
    win_prob_away REAL,
    draw_prob     REAL,        -- 축구용, 야구는 NULL
    ou_line       REAL,
    ou_line_source TEXT,       -- 'betman' (실제 배당 라인 그대로) | 'self' (자체 계산 라인)
    over_prob     REAL,
    under_prob    REAL,
    tier          TEXT,        -- '관망' | '추천' | '극추천'
    model_version TEXT,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);

CREATE TABLE IF NOT EXISTS accuracy_log (
    game_id           TEXT PRIMARY KEY,
    predicted_tier    TEXT,
    predicted_winner  TEXT,
    actual_winner     TEXT,
    winner_correct    INTEGER,   -- 0/1
    predicted_ou      TEXT,      -- 'over' | 'under'
    actual_total      INTEGER,
    ou_correct        INTEGER,   -- 0/1
    analysis_note     TEXT,      -- 왜 적중/실패했는지에 대한 자동 분석 코멘트
    checked_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (game_id) REFERENCES games(game_id)
);
