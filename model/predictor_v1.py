"""
predictor_v1.py
기획서 7장에 명시된 v1 공식을 코드화:
    승리 확률 = 시즌승률 60% + 최근폼(최근10경기 승률) 40% + 홈 어드밴티지
    오버/언더 = 팀별 평균 득점/실점 기반 예상 총점을 리그 평균과 비교

등급(관망/추천/극추천)은 8장 주의사항에 따라 초기엔 보수적으로:
    60% 미만 = 관망 / 60~80% = 추천 / 80%+ = 극추천

사용법:
    from model.predictor_v1 import predict
    result = predict(features)   # features = feature_builder.build_features(...) 결과
"""

MODEL_VERSION = "v1-weighted"

HOME_ADVANTAGE = 0.04          # MLB 통산 홈 승률이 원정보다 약 4~5%p 높은 경향을 반영한 보정값
DEFAULT_WIN_PCT = 0.5          # 데이터가 없을 때 대체값 (완전 중립)
LEAGUE_AVG_TOTAL_RUNS = 8.5    # MLB 리그 평균 경기당 총득점 근사치 (실제 배당사 라인이 생기면 대체 예정)
OU_SENSITIVITY = 0.35          # 예상 총점이 리그 평균에서 벗어난 정도를 확률로 변환하는 민감도

TIER_RECOMMEND = 0.60
TIER_STRONG_RECOMMEND = 0.80   # 8장 주의사항: 표본 부족 초기엔 보수적으로 80%+ 유지


def _sigmoid(x: float) -> float:
    import math
    return 1 / (1 + math.exp(-x))


def _safe(value, default=DEFAULT_WIN_PCT):
    return value if value is not None else default


def predict_win_prob(features: dict) -> tuple[float, float]:
    """시즌승률 60% + 최근폼 40% + 홈어드밴티지로 홈/원정 승리 확률 산출."""
    home_rating = (
        0.6 * _safe(features.get("home_win_pct_season"))
        + 0.4 * _safe(features.get("home_last10_win_pct"))
        + HOME_ADVANTAGE
    )
    away_rating = (
        0.6 * _safe(features.get("away_win_pct_season"))
        + 0.4 * _safe(features.get("away_last10_win_pct"))
    )

    total = home_rating + away_rating
    if total <= 0:
        return 0.5, 0.5

    win_prob_home = home_rating / total
    return round(win_prob_home, 3), round(1 - win_prob_home, 3)


def predict_over_under(features: dict) -> tuple[float, float, float]:
    """팀별 평균 득점/실점으로 예상 총점을 구한다.
    features에 market_ou_line(배트맨 등 실제 배당 라인)이 있으면 그 라인을 기준으로
    오버/언더 확률을 계산하고, 화면에도 그 실제 라인을 보여준다.
    없으면 리그 평균 기준 자체 계산 라인(0.5 단위 반올림)으로 대체한다."""
    home_scored = _safe(features.get("home_runs_scored_avg"), LEAGUE_AVG_TOTAL_RUNS / 2)
    home_allowed = _safe(features.get("home_runs_allowed_avg"), LEAGUE_AVG_TOTAL_RUNS / 2)
    away_scored = _safe(features.get("away_runs_scored_avg"), LEAGUE_AVG_TOTAL_RUNS / 2)
    away_allowed = _safe(features.get("away_runs_allowed_avg"), LEAGUE_AVG_TOTAL_RUNS / 2)

    # 홈팀 예상 득점 = (홈팀 평균득점 + 원정팀 평균실점) / 2, 원정팀도 동일 방식
    expected_home_runs = (home_scored + away_allowed) / 2
    expected_away_runs = (away_scored + home_allowed) / 2
    expected_total_raw = expected_home_runs + expected_away_runs

    market_ou_line = features.get("market_ou_line")

    if market_ou_line is not None:
        # 실제 배당 라인 기준으로 우리 예상 총점이 얼마나 위/아래인지로 확률 산출
        diff = expected_total_raw - market_ou_line
        ou_line = market_ou_line
    else:
        # 실배당이 없으면 우리 예상치를 0.5 단위로 반올림한 값을 라인으로 삼는다.
        # 확률도 반드시 "화면에 보여주는 그 라인" 기준으로 계산해야 앞뒤가 맞는다
        # (예전 버그: 라인은 우리 예상치로 보여주면서, 확률은 리그 평균과 비교해서
        #  라인과 확률이 서로 다른 기준이라 숫자가 이상하게 보였음).
        ou_line = round(expected_total_raw * 2) / 2
        diff = expected_total_raw - ou_line

    over_prob = round(_sigmoid(diff * OU_SENSITIVITY), 3)
    under_prob = round(1 - over_prob, 3)

    return ou_line, over_prob, under_prob


def determine_tier(*probs: float) -> str:
    """여러 확률 중 가장 자신 있는 값을 기준으로 관망/추천/극추천 등급 부여."""
    max_prob = max(probs)
    if max_prob >= TIER_STRONG_RECOMMEND:
        return "극추천"
    if max_prob >= TIER_RECOMMEND:
        return "추천"
    return "관망"


def predict(features: dict) -> dict:
    win_prob_home, win_prob_away = predict_win_prob(features)
    ou_line, over_prob, under_prob = predict_over_under(features)
    tier = determine_tier(win_prob_home, win_prob_away, over_prob, under_prob)
    ou_line_source = "betman" if features.get("market_ou_line") is not None else "self"

    return {
        "game_id": features["game_id"],
        "win_prob_home": win_prob_home,
        "win_prob_away": win_prob_away,
        "ou_line": ou_line,
        "ou_line_source": ou_line_source,
        "over_prob": over_prob,
        "under_prob": under_prob,
        "tier": tier,
        "model_version": MODEL_VERSION,
    }
