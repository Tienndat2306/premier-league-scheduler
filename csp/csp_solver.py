from datetime import timedelta, time as dt_time
from models.schedule import Schedule
from generators.round_robin import RoundRobinScheduler
from utils.date_utils import get_match_dates
from constraints.soft import CITY_CLASH_PAIRS
from constraints.hard import is_stadium_unavailable, resolve_schedule_stadium_conflicts


class CSPScheduler:
    """
    Constraint Satisfaction Problem (CSP) Scheduler trên mô hình OOP `Schedule`:
    1. Ràng buộc cứng (Hard Constraints):
       - Mỗi đội đá đúng 1 trận mỗi vòng.
       - Mỗi cặp đội gặp nhau đúng 2 lần (1 lượt sân nhà, 1 lượt sân khách).
       - Không xếp trận sân nhà vào ngày sân vận động bận (Stadium Availability).
    2. Ràng buộc An ninh Đô thị (Police & City Clash Constraint):
       - Hai CLB đối địch cùng thành phố (MU & Man City, Liverpool & Everton, Arsenal & Tottenham...)
         không được đá sân nhà trong cùng một ngày.
    3. Ràng buộc mềm / Phát sóng (Broadcast & Derby Constraints):
       - Các trận Derby phải diễn ra vào cuối tuần (Thứ 7 / Chủ Nhật) và khung giờ vàng (Prime Time).
       - Đảm bảo số trận cuối tuần tối thiểu mỗi vòng (`weekend_matches_min`).
       - Đảm bảo tổng số trận giờ vàng tối thiểu cả mùa (`prime_time_matches`).
    """

    def __init__(self, teams, constraints=None):
        self.teams = list(teams)
        self.constraints = constraints or {}
        self.custom_derbies = self.constraints.get("derby_matches")
        self.stadium_avail = self.constraints.get("stadium_availability", {})
        self.tv_broadcast = self.constraints.get("tv_broadcast", {
            "prime_time_matches": 38,
            "weekend_matches_min": 7
        })
        self.season_start = self.constraints.get("season_start", "2024-08-17")

    def solve_object(self) -> Schedule:
        rr = RoundRobinScheduler(self.teams, self.constraints)
        base_schedule = rr.generate_schedule_object()
        return self.satisfy_constraints_object(base_schedule)

    def solve(self):
        schedule_obj = self.solve_object()
        return schedule_obj.to_match_dicts(self.custom_derbies)

    def satisfy_constraints_object(self, schedule: Schedule) -> Schedule:
        fixed = schedule.copy()
        fixed.stadium_availability = dict(self.stadium_avail)

        # Bước 1: Giải quyết xung đột sân vận động (Stadium Availability)
        self._resolve_stadium_conflicts(fixed)

        # Bước 2: Đảm bảo các trận Derby luôn nằm ở cuối tuần & Prime Time, và đủ số trận cuối tuần mỗi vòng
        self._enforce_derby_and_weekend_constraints(fixed)

        # Bước 3: Giải quyết xung đột 2 đội đối địch cùng thành phố đá sân nhà cùng ngày (Police / City Clash)
        self._resolve_city_home_clashes(fixed)

        # Bước 4: Đảm bảo chỉ tiêu tổng số trận Prime Time tối thiểu theo yêu cầu truyền hình
        self._enforce_prime_time_target(fixed)

        # Bước 5: Chốt khóa cuối cùng để đảm bảo 100% không có trận nào bị đẩy ngược vào ngày sân bận
        self._resolve_stadium_conflicts(fixed)

        fixed.sorted_matches = sorted(
            fixed.all_matches(),
            key=lambda m: (m.round_num, m.date_str, m.time_str)
        )
        return fixed

    def _is_stadium_unavailable(self, home_team, target_date) -> bool:
        return is_stadium_unavailable(home_team, target_date, self.stadium_avail)

    def _resolve_stadium_conflicts(self, schedule: Schedule):
        resolve_schedule_stadium_conflicts(schedule, self.stadium_avail)

    def _resolve_city_home_clashes(self, schedule: Schedule):
        """
        Tách ngày thi đấu nếu 2 CLB đối địch cùng thành phố (ví dụ MU & Man City, Liverpool & Everton)
        cùng đá sân nhà trong 1 ngày của vòng đấu (chuyển 1 trận sang ngày kế tiếp trong cuối tuần).
        """
        round_dates = get_match_dates(self.season_start, total_rounds=max(38, schedule.total_rounds))
        for r_idx, r_num in enumerate(sorted(schedule.fixtures.keys())):
            fx = schedule.fixtures[r_num]
            base_saturday = round_dates[r_idx]
            sunday_date = base_saturday + timedelta(days=1)

            for clash_pair in CITY_CLASH_PAIRS:
                pair_list = list(clash_pair)
                m_a = next((m for m in fx.matches if m.home_team.name == pair_list[0]), None)
                m_b = next((m for m in fx.matches if m.home_team.name == pair_list[1]), None)

                if m_a and m_b and m_a.date_str == m_b.date_str:
                    # Dời m_b sang ngày còn lại của cuối tuần (Thứ 7 <-> Chủ Nhật) nếu sân không bận
                    if m_b.date_obj == base_saturday and not self._is_stadium_unavailable(m_b.home_team, sunday_date):
                        m_b.date = sunday_date
                    elif m_b.date_obj != base_saturday and not self._is_stadium_unavailable(m_b.home_team, base_saturday):
                        m_b.date = base_saturday

    def _enforce_derby_and_weekend_constraints(self, schedule: Schedule):
        weekend_min = int(self.tv_broadcast.get("weekend_matches_min", 7))
        round_dates = get_match_dates(self.season_start, total_rounds=max(38, schedule.total_rounds))

        for r_idx, r_num in enumerate(sorted(schedule.fixtures.keys())):
            fx = schedule.fixtures[r_num]
            base_saturday = round_dates[r_idx]
            sunday_date = base_saturday + timedelta(days=1)

            for i, m in enumerate(fx.matches):
                m.custom_derbies = self.custom_derbies
                if m.is_derby(self.custom_derbies):
                    if not m.is_weekend:
                        preferred_dates = [sunday_date, base_saturday] if (i % 2 == 1) else [base_saturday, sunday_date]
                        for cand_d in preferred_dates:
                            if not self._is_stadium_unavailable(m.home_team, cand_d):
                                m.date = cand_d
                                break
                    m.is_prime_time = True
                    m.time = dt_time(17, 30) if m.date_obj and m.date_obj.weekday() == 6 else dt_time(20, 0)

            weekend_count = sum(1 for m in fx.matches if m.is_weekend)
            if weekend_count < weekend_min:
                for m in fx.matches:
                    if not m.is_weekend:
                        if not self._is_stadium_unavailable(m.home_team, base_saturday):
                            m.date = base_saturday
                            weekend_count += 1
                        elif not self._is_stadium_unavailable(m.home_team, sunday_date):
                            m.date = sunday_date
                            weekend_count += 1
                        if weekend_count >= weekend_min:
                            break

    def _enforce_prime_time_target(self, schedule: Schedule):
        target_prime = int(self.tv_broadcast.get("prime_time_matches", 38))
        all_matches = schedule.all_matches()
        current_prime = sum(1 for m in all_matches if m.is_prime_time)

        if current_prime < target_prime:
            for m in all_matches:
                if m.is_weekend and not m.is_prime_time:
                    m.is_prime_time = True
                    m.time = dt_time(17, 30) if m.date_obj and m.date_obj.weekday() == 6 else dt_time(20, 0)
                    current_prime += 1
                    if current_prime >= target_prime:
                        break
