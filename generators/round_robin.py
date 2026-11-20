from typing import List
from models.match import Match
from models.schedule import Schedule
from models.team import Team
from constraints.hard import resolve_schedule_stadium_conflicts
from utils.date_utils import get_match_dates, get_season_end, assign_slot_for_match


def generate_round_robin(teams: List[Team], custom_derbies=None) -> List[List[Match]]:
    """
    Tạo danh sách 38 vòng đấu (mỗi vòng 10 đối tượng Match) theo thuật toán Canonical Berger Table (1-Factorization)
    đảm bảo cân bằng luân phiên Sân nhà / Sân khách với số lần break tối thiểu lý thuyết (N - 2 = 18 breaks/lượt).
    """
    team_list = list(teams)
    n = len(team_list)
    if n < 2:
        return []

    if n % 2 == 1:
        team_list.append(None)
        n += 1

    rounds = n - 1
    half = n // 2

    fixed_team = team_list[0]
    rotating_teams = team_list[1:]

    first_leg = []
    match_id = 1

    # -------- LƯỢT ĐI (19 VÒNG) --------
    for r_idx in range(rounds):
        round_num = r_idx + 1
        current_lineup = [fixed_team] + rotating_teams
        round_matches = []

        for i in range(half):
            t1 = current_lineup[i]
            t2 = current_lineup[n - 1 - i]

            if t1 is not None and t2 is not None:
                if i == 0:
                    # Đội cố định luân phiên H/A mỗi vòng
                    home, away = (t1, t2) if (r_idx % 2 == 0) else (t2, t1)
                else:
                    # Quy chuẩn Canonical 1-Factorization: vị trí i lẻ và chẵn đảo chiều nhau
                    home, away = (t1, t2) if (i % 2 == 1) else (t2, t1)

                round_matches.append(
                    Match(
                        match_id=match_id,
                        home_team=home,
                        away_team=away,
                        round_num=round_num,
                        custom_derbies=custom_derbies
                    )
                )
                match_id += 1

        first_leg.append(round_matches)
        rotating_teams = [rotating_teams[-1]] + rotating_teams[:-1]

    # -------- LƯỢT VỀ (19 VÒNG - Mirrored Order) --------
    second_leg = []
    for r_idx, round_matches in enumerate(first_leg):
        rev_round_num = rounds + r_idx + 1
        rev_round = []
        for m in round_matches:
            rev_round.append(
                Match(
                    match_id=match_id,
                    home_team=m.away_team,
                    away_team=m.home_team,
                    round_num=rev_round_num,
                    custom_derbies=custom_derbies
                )
            )
            match_id += 1
        second_leg.append(rev_round)

    return first_leg + second_leg


class RoundRobinScheduler:
    """
    Bộ xếp lịch Round Robin hướng đối tượng, trả về đối tượng Schedule
    hoặc danh sách dict tương thích hoàn toàn với API & Frontend.
    """

    def __init__(self, teams: List[Team], constraints: dict = None):
        self.teams = list(teams)
        self.constraints = constraints or {}

    def generate_schedule_object(self) -> Schedule:
        custom_derbies = self.constraints.get("derby_matches")
        stadium_avail = self.constraints.get("stadium_availability", {})
        tv_broadcast = self.constraints.get("tv_broadcast", {})
        weekend_min = int(tv_broadcast.get("weekend_matches_min", 7))
        season_start = self.constraints.get("season_start", "2024-08-17")

        all_rounds = generate_round_robin(self.teams, custom_derbies=custom_derbies)
        return self.build_schedule_object_from_rounds(
            all_rounds,
            season_start=season_start,
            weekend_min=weekend_min,
            stadium_avail=stadium_avail,
            custom_derbies=custom_derbies
        )

    def build_schedule_object_from_rounds(
        self,
        all_rounds: List[List[Match]],
        season_start="2024-08-17",
        weekend_min: int = 7,
        stadium_avail: dict = None,
        custom_derbies=None
    ) -> Schedule:
        stadium_avail = stadium_avail or self.constraints.get("stadium_availability", {})
        custom_derbies = custom_derbies if custom_derbies is not None else self.constraints.get("derby_matches")
        round_dates = get_match_dates(season_start, total_rounds=max(38, len(all_rounds)))

        schedule = Schedule()
        schedule.season_start = round_dates[0] if round_dates else None
        schedule.season_end = get_season_end(season_start, total_rounds=len(all_rounds))
        schedule.stadium_availability = dict(stadium_avail)

        match_id = 1
        for r_idx, round_matches in enumerate(all_rounds):
            round_num = r_idx + 1
            base_saturday = round_dates[r_idx]

            # Ưu tiên đưa trận Derby lên đầu vòng để gán vào cuối tuần / Prime Time
            sorted_matches = sorted(
                round_matches,
                key=lambda m: 0 if m.is_derby(custom_derbies) else 1
            )

            for m_idx, orig_match in enumerate(sorted_matches):
                m = orig_match.copy()
                m.id = match_id
                m.round_num = round_num
                m.custom_derbies = custom_derbies
                match_id += 1

                is_derby = m.is_derby(custom_derbies)
                m_date, m_time, is_prime = assign_slot_for_match(
                    base_saturday=base_saturday,
                    match_index=m_idx,
                    total_in_round=len(sorted_matches),
                    is_derby=is_derby,
                    weekend_min=weekend_min,
                    home_team_name=m.home_team.name,
                    venue_name=m.venue,
                    stadium_avail=stadium_avail
                )
                m.date = m_date
                m.time = m_time
                m.is_prime_time = is_prime

                schedule.add_match(m)

        if stadium_avail:
            resolve_schedule_stadium_conflicts(schedule, stadium_avail)

        schedule.sorted_matches = sorted(
            schedule.all_matches(),
            key=lambda x: (x.round_num, x.date_str, x.time_str)
        )
        return schedule

    def generate_schedule(self) -> List[dict]:
        schedule_obj = self.generate_schedule_object()
        return schedule_obj.to_match_dicts(self.constraints.get("derby_matches"))
