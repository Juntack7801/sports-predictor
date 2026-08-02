"""
team_name_map.py
배트맨(한글 팀명 표기) <-> 우리 DB에 저장된 팀명(MLB는 영문, NPB는 일본어) 매핑표.

*** 중요 안내 ***
이 매핑은 일반적으로 통용되는 한글 팀명 기준으로 작성한 것이며,
실제 배트맨 사이트의 정확한 표기(띄어쓰기, 축약 여부 등)와 다를 수 있다.
betman_odds_collector.py를 실제로 돌려보고 매칭이 안 되는 팀이 있으면
아래 딕셔너리에 그 팀만 추가/수정하면 된다. (예: "다저스"만 오는지
"LA다저스"로 오는지는 실제 페이지를 봐야 확실함)

KBO는 배트맨도 한글로 표기하므로 별도 매핑 없이 db.find_market_ou_line()의
느슨한 포함 매칭만으로 대부분 해결된다.
"""

# 배트맨에서 흔히 쓰이는 한글 팀명 -> MLB Stats API의 영문 팀명(name 필드)
MLB_KR_TO_EN = {
    "양키스": "New York Yankees",
    "뉴욕양키스": "New York Yankees",
    "레드삭스": "Boston Red Sox",
    "보스턴": "Boston Red Sox",
    "블루제이스": "Toronto Blue Jays",
    "토론토": "Toronto Blue Jays",
    "레이스": "Tampa Bay Rays",
    "탬파베이": "Tampa Bay Rays",
    "오리올스": "Baltimore Orioles",
    "볼티모어": "Baltimore Orioles",
    "화이트삭스": "Chicago White Sox",
    "가디언스": "Cleveland Guardians",
    "클리블랜드": "Cleveland Guardians",
    "타이거스": "Detroit Tigers",
    "디트로이트": "Detroit Tigers",
    "로열스": "Kansas City Royals",
    "캔자스시티": "Kansas City Royals",
    "트윈스": "Minnesota Twins",
    "미네소타": "Minnesota Twins",
    "애스트로스": "Houston Astros",
    "휴스턴": "Houston Astros",
    "에인절스": "Los Angeles Angels",
    "엔젤스": "Los Angeles Angels",
    "애슬레틱스": "Athletics",
    "매리너스": "Seattle Mariners",
    "시애틀": "Seattle Mariners",
    "레인저스": "Texas Rangers",
    "텍사스": "Texas Rangers",
    "브레이브스": "Atlanta Braves",
    "애틀랜타": "Atlanta Braves",
    "말린스": "Miami Marlins",
    "마이애미": "Miami Marlins",
    "메츠": "New York Mets",
    "뉴욕메츠": "New York Mets",
    "필리스": "Philadelphia Phillies",
    "필라델피아": "Philadelphia Phillies",
    "내셔널스": "Washington Nationals",
    "워싱턴": "Washington Nationals",
    "컵스": "Chicago Cubs",
    "시카고컵스": "Chicago Cubs",
    "레즈": "Cincinnati Reds",
    "신시내티": "Cincinnati Reds",
    "브루어스": "Milwaukee Brewers",
    "밀워키": "Milwaukee Brewers",
    "파이리츠": "Pittsburgh Pirates",
    "피츠버그": "Pittsburgh Pirates",
    "카디널스": "St. Louis Cardinals",
    "세인트루이스": "St. Louis Cardinals",
    "다이아몬드백스": "Arizona Diamondbacks",
    "애리조나": "Arizona Diamondbacks",
    "로키스": "Colorado Rockies",
    "콜로라도": "Colorado Rockies",
    "다저스": "Los Angeles Dodgers",
    "LA다저스": "Los Angeles Dodgers",
    "파드리스": "San Diego Padres",
    "샌디에이고": "San Diego Padres",
    "자이언츠": "San Francisco Giants",
    "샌프란시스코": "San Francisco Giants",
}

# 배트맨에서 흔히 쓰이는 한글 팀명 -> npb.jp에 표기되는 일본어 팀명
NPB_KR_TO_JP = {
    "요미우리": "読売ジャイアンツ",
    "자이언츠": "読売ジャイアンツ",
    "한신": "阪神タイガース",
    "타이거스": "阪神タイガース",
    "주니치": "中日ドラゴンズ",
    "드래곤즈": "中日ドラゴンズ",
    "야쿠르트": "東京ヤクルトスワローズ",
    "스왈로즈": "東京ヤクルトスワローズ",
    "요코하마": "横浜DeNAベイスターズ",
    "DeNA": "横浜DeNAベイスターズ",
    "히로시마": "広島東洋カープ",
    "카프": "広島東洋カープ",
    "소프트뱅크": "福岡ソフトバンクホークス",
    "훅스": "福岡ソフトバンクホークス",
    "니혼햄": "北海道日本ハムファイターズ",
    "파이터스": "北海道日本ハムファイターズ",
    "라쿠텐": "東北楽天ゴールデンイーグルス",
    "이글스": "東北楽天ゴールデンイーグルス",
    "세이부": "埼玉西武ライオンズ",
    "라이온즈": "埼玉西武ライオンズ",
    "치바롯데": "千葉ロッテマリーンズ",
    "롯데": "千葉ロッテマリーンズ",
    "오릭스": "オリックス・バファローズ",
    "버팔로즈": "オリックス・バファローズ",
}


def translate_betman_name(league: str, kr_name: str) -> str:
    """배트맨 한글 팀명을 우리 DB 팀명으로 변환. 매핑에 없으면 원문 그대로 반환
    (KBO는 어차피 한글이라 원문으로도 느슨한 매칭이 대부분 가능)."""
    table = {"MLB": MLB_KR_TO_EN, "NPB": NPB_KR_TO_JP}.get(league, {})
    # 공백 제거 후 매칭 (배트맨 표기가 "LA 다저스"인지 "LA다저스"인지 모르므로)
    key = kr_name.replace(" ", "")
    return table.get(key, kr_name)


# 화면 표시용: 우리 DB 팀명(MLB=영문, NPB=일본어) -> 한글 팀명 (하나의 정식 명칭만)
MLB_EN_TO_KR = {
    "New York Yankees": "뉴욕 양키스",
    "Boston Red Sox": "보스턴 레드삭스",
    "Toronto Blue Jays": "토론토 블루제이스",
    "Tampa Bay Rays": "탬파베이 레이스",
    "Baltimore Orioles": "볼티모어 오리올스",
    "Chicago White Sox": "시카고 화이트삭스",
    "Cleveland Guardians": "클리블랜드 가디언스",
    "Detroit Tigers": "디트로이트 타이거스",
    "Kansas City Royals": "캔자스시티 로열스",
    "Minnesota Twins": "미네소타 트윈스",
    "Houston Astros": "휴스턴 애스트로스",
    "Los Angeles Angels": "LA 에인절스",
    "Athletics": "애슬레틱스",
    "Seattle Mariners": "시애틀 매리너스",
    "Texas Rangers": "텍사스 레인저스",
    "Atlanta Braves": "애틀랜타 브레이브스",
    "Miami Marlins": "마이애미 말린스",
    "New York Mets": "뉴욕 메츠",
    "Philadelphia Phillies": "필라델피아 필리스",
    "Washington Nationals": "워싱턴 내셔널스",
    "Chicago Cubs": "시카고 컵스",
    "Cincinnati Reds": "신시내티 레즈",
    "Milwaukee Brewers": "밀워키 브루어스",
    "Pittsburgh Pirates": "피츠버그 파이리츠",
    "St. Louis Cardinals": "세인트루이스 카디널스",
    "Arizona Diamondbacks": "애리조나 다이아몬드백스",
    "Colorado Rockies": "콜로라도 로키스",
    "Los Angeles Dodgers": "LA 다저스",
    "San Diego Padres": "샌디에이고 파드리스",
    "San Francisco Giants": "샌프란시스코 자이언츠",
}

# 화면 표시용: npb.jp 일본어 팀명 -> 한글 팀명
NPB_JP_TO_KR = {
    "読売ジャイアンツ": "요미우리 자이언츠",
    "阪神タイガース": "한신 타이거스",
    "中日ドラゴンズ": "주니치 드래곤즈",
    "東京ヤクルトスワローズ": "야쿠르트 스왈로즈",
    "横浜DeNAベイスターズ": "요코하마 DeNA 베이스타즈",
    "広島東洋カープ": "히로시마 카프",
    "福岡ソフトバンクホークス": "소프트뱅크 호크스",
    "北海道日本ハムファイターズ": "니혼햄 파이터스",
    "東北楽天ゴールデンイーグルス": "라쿠텐 이글스",
    "埼玉西武ライオンズ": "세이부 라이온즈",
    "千葉ロッテマリーンズ": "롯데 마리너스",
    "オリックス・バファローズ": "오릭스 버팔로즈",
}


def get_display_kr_name(league: str, team_name: str) -> str:
    """화면에 보여줄 한글 팀명. KBO는 원래 한글이라 그대로, MLB/NPB는 매핑표로 변환.
    매핑에 없는 팀은 원래 이름을 그대로 반환한다(지어내지 않음)."""
    if league == "KBO":
        return team_name
    if league == "MLB":
        return MLB_EN_TO_KR.get(team_name, team_name)
    if league == "NPB":
        return NPB_JP_TO_KR.get(team_name, team_name)
    return team_name


def get_display_kr_name_short(league: str, team_name: str) -> str:
    """카드 제목처럼 짧게 보여줄 때 쓰는 축약 이름 (예: '워싱턴 내셔널스' -> '워싱턴').
    KBO는 이미 짧아서(예: 'LG') 그대로 반환."""
    full = get_display_kr_name(league, team_name)
    if league == "KBO":
        return full
    return full.split(" ")[0] if full else full
