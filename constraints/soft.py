from datetime import time, datetime

# Các cặp CLB đối địch cùng thành phố / khu vực không được đá sân nhà trong cùng một ngày (Police & Traffic Rule)
CITY_CLASH_PAIRS = [
    frozenset(["Manchester United", "Manchester City"]),
    frozenset(["Liverpool", "Everton"]),
    frozenset(["Arsenal", "Tottenham"]),
    frozenset(["Chelsea", "Fulham"]),
    frozenset(["Aston Villa", "Wolverhampton"])
]

MIN_REPEAT_SEPARATION_ROUNDS = 8


def evaluate_soft_details(schedule, custom_derbies=None) -> dict:
    """
    Phân tích chi tiết và tính điểm phạt ràng buộc mềm (Soft Constraints Penalty - càng nhỏ càng tốt):
    1. Chuỗi đá Sân nhà hoặc Sân khách liên tiếp > 2 trận (Home/Away Streaks).
    2. Khoảng cách tối thiểu giữa trận Lượt đi và Lượt về của cùng 1 cặp đấu (< 8 vòng).
    3. Xung đột an ninh đô thị (2 đội đối địch cùng thành phố đá sân nhà trong cùng 1 ngày).
    4. Trận Derby nhưng không xếp vào cuối tuần (Thứ 7 / Chủ Nhật) hoặc quá nhiều Derby cùng vòng.
    5. Cân bằng số trận sân nhà/khách.
    """
    streak_penalty = 0.0
    repeat_separation_penalty = 0.0
    city_clash_penalty = 0.0
    derby_penalty = 0.0
    balance_penalty = 0.0

    home_count = {}
    home_streaks = {}
    away_streaks = {}
    streak_breaks_count = 0
    city_clash_count = 0
    repeat_violation_count = 0
    min_leg_gap = 38

    first_meeting_round = {}
    sat_matches = 0
    sun_matches = 0

    for round_num in sorted(schedule.fixtures.keys()):
        fixture = schedule.fixtures[round_num]
        derbies_in_round = 0
        home_teams_by_date = {}

        for match in fixture.matches:
            hid = match.home_team.id
            aid = match.away_team.id
            h_name = match.home_team.name
            a_name = match.away_team.name

            # 1. Chuỗi Sân nhà / Sân khách liên tiếp (Home / Away Streaks)
            home_streaks[hid] = home_streaks.get(hid, 0) + 1
            away_streaks[hid] = 0

            away_streaks[aid] = away_streaks.get(aid, 0) + 1
            home_streaks[aid] = 0

            if home_streaks[hid] == 2:
                streak_penalty += 2
            elif home_streaks[hid] > 2:
                streak_penalty += 25 * (home_streaks[hid] - 2)
                streak_breaks_count += 1

            if away_streaks[aid] == 2:
                streak_penalty += 2
            elif away_streaks[aid] > 2:
                streak_penalty += 25 * (away_streaks[aid] - 2)
                streak_breaks_count += 1

            # 2. Khoảng cách vòng đấu giữa Lượt đi và Lượt về (Minimum Separation Between Legs)
            pair_key = frozenset([hid, aid])
            if pair_key in first_meeting_round:
                gap = round_num - first_meeting_round[pair_key]
                if gap < min_leg_gap:
                    min_leg_gap = gap
                if gap < MIN_REPEAT_SEPARATION_ROUNDS:
                    repeat_separation_penalty += (MIN_REPEAT_SEPARATION_ROUNDS - gap) * 18
                    repeat_violation_count += 1
            else:
                first_meeting_round[pair_key] = round_num

            # 3. Gom nhóm đội chủ nhà theo ngày để kiểm tra xung đột sân cùng thành phố
            d_str = match.date_str
            if d_str:
                home_teams_by_date.setdefault(d_str, set()).add(h_name)

            # 4. Kiểm tra Derby & Khung giờ
            if match.is_derby(custom_derbies):
                derbies_in_round += 1
                d_obj = match.date_obj
                if not (d_obj and d_obj.weekday() in (5, 6)):
                    derby_penalty += 15

            home_count[hid] = home_count.get(hid, 0) + 1

            d_obj = match.date_obj
            if d_obj:
                wd = d_obj.weekday()
                if wd == 5:
                    sat_matches += 1
                elif wd == 6:
                    sun_matches += 1

        # Kiểm tra xung đột an ninh đô thị (2 đội đối địch cùng thành phố cùng đá sân nhà trong 1 ngày)
        for d_str, home_set in home_teams_by_date.items():
            for clash_pair in CITY_CLASH_PAIRS:
                if clash_pair.issubset(home_set):
                    city_clash_penalty += 30
                    city_clash_count += 1

        if derbies_in_round > 2:
            derby_penalty += 15 * (derbies_in_round - 2)

    for count in home_count.values():
        if count != 19:
            balance_penalty += abs(count - 19) * 10

    if sat_matches + sun_matches == 0:
        balance_penalty += 50

    total_penalty = (
        streak_penalty
        + repeat_separation_penalty
        + city_clash_penalty
        + derby_penalty
        + balance_penalty
    )

    return {
        "total_penalty": round(total_penalty, 2),
        "streak_penalty": round(streak_penalty, 2),
        "repeat_separation_penalty": round(repeat_separation_penalty, 2),
        "city_clash_penalty": round(city_clash_penalty, 2),
        "derby_penalty": round(derby_penalty, 2),
        "balance_penalty": round(balance_penalty, 2),
        "streak_breaks_count": streak_breaks_count,
        "city_clash_count": city_clash_count,
        "repeat_violation_count": repeat_violation_count,
        "min_leg_gap": min_leg_gap if first_meeting_round else 19
    }


def soft_penalty(schedule, custom_derbies=None) -> float:
    """Trả về tổng điểm phạt ràng buộc mềm (dùng trực tiếp cho hàm Fitness của GA)"""
    return evaluate_soft_details(schedule, custom_derbies=custom_derbies)["total_penalty"]
