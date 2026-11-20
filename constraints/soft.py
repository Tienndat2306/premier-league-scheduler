from datetime import time, datetime
from utils.derby_utils import DERBY_SET

# Các cặp CLB đối địch cùng thành phố / khu vực không được đá sân nhà trong cùng một ngày (Police & Traffic Rule)
CITY_CLASH_PAIRS = [
    frozenset(["Manchester United", "Manchester City"]),
    frozenset(["Liverpool", "Everton"]),
    frozenset(["Arsenal", "Tottenham"]),
    frozenset(["Chelsea", "Fulham"]),
    frozenset(["Aston Villa", "Wolverhampton"])
]

MIN_REPEAT_SEPARATION_ROUNDS = 8


def _build_derby_lookup(custom_derbies):
    if custom_derbies is None:
        return None
    return {frozenset(p[:2]) for p in custom_derbies if isinstance(p, (list, tuple)) and len(p) >= 2}


def evaluate_soft_details(schedule, custom_derbies=None, team_requests=None) -> dict:
    """
    Phân tích chi tiết và tính điểm phạt ràng buộc mềm (Soft Constraints Penalty - càng nhỏ càng tốt):
    1. Chuỗi đá Sân nhà hoặc Sân khách liên tiếp > 2 trận (Home/Away Streaks).
    2. Khoảng cách tối thiểu giữa trận Lượt đi và Lượt về của cùng 1 cặp đấu (< 8 vòng).
    3. Xung đột an ninh đô thị (2 đội đối địch cùng thành phố đá sân nhà trong cùng 1 ngày).
    4. Trận Derby nhưng không xếp vào cuối tuần (Thứ 7 / Chủ Nhật) hoặc quá nhiều Derby cùng vòng.
    5. Cân bằng số trận sân nhà/khách, quy tắc mở màn/hạ màn (Vòng 1 & Vòng 38 trái dấu H/A),
       và công bằng truyền hình (TV Broadcast Fairness).
    6. Yêu cầu riêng của từng CLB ở vòng cụ thể (`team_requests`, ví dụ `{"Arsenal": {"1": "A"}}`).
    """
    streak_penalty = 0.0
    repeat_separation_penalty = 0.0
    city_clash_penalty = 0.0
    derby_penalty = 0.0
    balance_penalty = 0.0
    team_request_penalty = 0.0
    open_close_penalty = 0.0
    tv_fairness_penalty = 0.0

    home_count = {}
    prime_count_by_team = {}
    home_streaks = {}
    away_streaks = {}
    streak_breaks_count = 0
    city_clash_count = 0
    repeat_violation_count = 0
    team_request_violations = 0
    open_close_violations = 0
    min_leg_gap = 38

    first_meeting_round = {}
    sat_matches = 0
    sun_matches = 0
    round1_ha = {}
    last_round_ha = {}

    derby_lookup = _build_derby_lookup(custom_derbies)
    reqs = team_requests if team_requests is not None else getattr(schedule, "team_requests", None) or {}
    sorted_rounds = sorted(schedule.fixtures.keys())
    first_r = sorted_rounds[0] if sorted_rounds else 1
    last_r = sorted_rounds[-1] if sorted_rounds else 38

    for round_num in sorted_rounds:
        fixture = schedule.fixtures[round_num]
        derbies_in_round = 0
        home_teams_by_date = {}
        r_str = str(round_num)

        for match in fixture.matches:
            ht = match.home_team
            at = match.away_team
            hid = ht.id
            aid = at.id
            h_name = ht.name
            a_name = at.name

            if round_num == first_r:
                round1_ha[h_name] = "H"
                round1_ha[a_name] = "A"
            if round_num == last_r:
                last_round_ha[h_name] = "H"
                last_round_ha[a_name] = "A"

            # Kiểm tra yêu cầu riêng của CLB (team_requests)
            if reqs:
                h_req = reqs.get(h_name, {}).get(r_str)
                if h_req and h_req.upper() != "H":
                    team_request_penalty += 20.0
                    team_request_violations += 1
                a_req = reqs.get(a_name, {}).get(r_str)
                if a_req and a_req.upper() != "A":
                    team_request_penalty += 20.0
                    team_request_violations += 1

            # 1. Chuỗi Sân nhà / Sân khách liên tiếp (Home / Away Streaks)
            hs = home_streaks.get(hid, 0) + 1
            home_streaks[hid] = hs
            away_streaks[hid] = 0

            as_ = away_streaks.get(aid, 0) + 1
            away_streaks[aid] = as_
            home_streaks[aid] = 0

            if hs == 2:
                streak_penalty += 2
            elif hs > 2:
                streak_penalty += 25 * (hs - 2)
                streak_breaks_count += 1

            if as_ == 2:
                streak_penalty += 2
            elif as_ > 2:
                streak_penalty += 25 * (as_ - 2)
                streak_breaks_count += 1

            # 2. Khoảng cách vòng đấu giữa Lượt đi và Lượt về (Minimum Separation Between Legs)
            pair_key = (hid, aid) if hid < aid else (aid, hid)
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
            d_obj = match.date_obj
            if d_obj:
                home_teams_by_date.setdefault(d_obj, set()).add(h_name)
                wd = d_obj.weekday()
                if wd == 5:
                    sat_matches += 1
                elif wd == 6:
                    sun_matches += 1
            else:
                wd = -1

            # 4. Kiểm tra Derby & Khung giờ
            if derby_lookup is not None:
                is_d = (
                    frozenset((h_name, a_name)) in derby_lookup
                    or frozenset((ht.short, at.short)) in derby_lookup
                )
            else:
                is_d = match.is_derby()

            if is_d:
                derbies_in_round += 1
                if wd not in (5, 6):
                    derby_penalty += 15

            if match.is_prime_time:
                prime_count_by_team[h_name] = prime_count_by_team.get(h_name, 0) + 1
                prime_count_by_team[a_name] = prime_count_by_team.get(a_name, 0) + 1
            else:
                prime_count_by_team.setdefault(h_name, 0)
                prime_count_by_team.setdefault(a_name, 0)

            home_count[hid] = home_count.get(hid, 0) + 1

        # Kiểm tra xung đột an ninh đô thị (2 đội đối địch cùng thành phố cùng đá sân nhà trong 1 ngày)
        for _, home_set in home_teams_by_date.items():
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

    # Quy tắc EPL Vòng 1 & Vòng 38: Nếu một CLB đá cùng Sân nhà hoặc cùng Sân khách ở cả Vòng mở màn và Vòng hạ màn
    if first_r != last_r:
        for t_name, r1_type in round1_ha.items():
            if last_round_ha.get(t_name) == r1_type:
                open_close_violations += 1
                # Trong Canonical Mirrored Schedule, Vòng 1 và Vòng 38 tự động đối xứng nếu hoán vị phù hợp

    # Quy tắc công bằng truyền hình (TV Fairness): Mỗi CLB nên có ít nhất 2 trận giờ vàng
    for t_name, p_cnt in prime_count_by_team.items():
        if p_cnt < 2:
            tv_fairness_penalty += (2 - p_cnt) * 5.0

    balance_penalty += tv_fairness_penalty + team_request_penalty

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
        "team_request_penalty": round(team_request_penalty, 2),
        "tv_fairness_penalty": round(tv_fairness_penalty, 2),
        "streak_breaks_count": streak_breaks_count,
        "city_clash_count": city_clash_count,
        "repeat_violation_count": repeat_violation_count,
        "team_request_violations": team_request_violations,
        "open_close_alternating_clubs": len(round1_ha) - open_close_violations,
        "min_leg_gap": min_leg_gap if first_meeting_round else 19
    }


def soft_penalty(schedule, custom_derbies=None) -> float:
    """Trả về tổng điểm phạt ràng buộc mềm (dùng trực tiếp cho hàm Fitness của GA)"""
    return evaluate_soft_details(schedule, custom_derbies=custom_derbies)["total_penalty"]
