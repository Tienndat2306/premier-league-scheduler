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
        self.team_requests = self.constraints.get("team_requests", {})
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
        fixed.team_requests = dict(self.team_requests)

        # Bước 0: Đáp ứng yêu cầu Sân nhà/Sân khách ở vòng cụ thể của CLB (nếu có) bằng phép đảo H/A đối xứng
        if self.team_requests:
            self._enforce_team_round_requests(fixed)

        # Bước 1: Giải quyết xung đột sân vận động (Stadium Availability)
        self._resolve_stadium_conflicts(fixed)

        # Bước 2: Đảm bảo các trận Derby luôn nằm ở cuối tuần & Prime Time, và đủ số trận cuối tuần mỗi vòng
        self._enforce_derby_and_weekend_constraints(fixed)

        # Bước 3: Giải quyết xung đột 2 đội đối địch cùng thành phố đá sân nhà cùng ngày (Police / City Clash)
        self._resolve_city_home_clashes(fixed)

        # Bước 4: Đảm bảo chỉ tiêu tổng số trận Prime Time tối thiểu và phân bổ công bằng giữa 20 CLB
        self._enforce_prime_time_target(fixed)

        # Bước 5: Chốt khóa cuối cùng để đảm bảo 100% không có trận nào bị đẩy ngược vào ngày sân bận
        self._resolve_stadium_conflicts(fixed)

        fixed.sorted_matches = sorted(
            fixed.all_matches(),
            key=lambda m: (m.round_num, m.date_str, m.time_str)
        )
        return fixed

    def _enforce_team_round_requests(self, schedule: Schedule):
        """
        Đáp ứng yêu cầu Sân nhà (H) hoặc Sân khách (A) tại một vòng cụ thể của CLB
        bằng cách hoán đổi đối xứng quyền chủ nhà với trận lượt về tương ứng.
        """
        all_matches = schedule.all_matches()
        for club_name, req_map in (self.team_requests or {}).items():
            if not isinstance(req_map, dict):
                continue
            for r_str, pref in req_map.items():
                try:
                    r_num = int(r_str)
                except ValueError:
                    continue
                pref_up = str(pref).upper()
                if pref_up not in ("H", "A") or r_num not in schedule.fixtures:
                    continue
                fx = schedule.fixtures[r_num]
                target_m = next(
                    (m for m in fx.matches if m.home_team.name == club_name or m.away_team.name == club_name),
                    None
                )
                if not target_m:
                    continue
                is_currently_home = target_m.home_team.name == club_name
                if (pref_up == "H" and not is_currently_home) or (pref_up == "A" and is_currently_home):
                    rev_m = next(
                        (
                            m2 for m2 in all_matches
                            if m2.id != target_m.id
                            and m2.home_team.id == target_m.away_team.id
                            and m2.away_team.id == target_m.home_team.id
                        ),
                        None
                    )
                    if rev_m:
                        for m_obj in (target_m, rev_m):
                            m_obj.home_team, m_obj.away_team = m_obj.away_team, m_obj.home_team
                            ht = m_obj.home_team
                            m_obj.venue = ht.stadium.name if getattr(ht, "stadium", None) else f"{ht.name} Stadium"
                            m_obj.city = ht.stadium.city if getattr(ht, "stadium", None) else ""

    def _is_stadium_unavailable(self, home_team, target_date) -> bool:
        return is_stadium_unavailable(home_team, target_date, self.stadium_avail)

    def _resolve_stadium_conflicts(self, schedule: Schedule):
        resolve_schedule_stadium_conflicts(schedule, self.stadium_avail)

    def _resolve_city_home_clashes(self, schedule: Schedule):
        """
        Bộ giải CSP Backtracking với MRV (Minimum Remaining Values) & Forward Checking ở cấp độ Vòng đấu:
        Phân bổ lại ngày thi đấu trong cuối tuần / ngày khả dụng cho các CLB thuộc cặp xung đột thành phố
        (CITY_CLASH_PAIRS) sao cho:
        1. Không có 2 đội đối địch cùng thành phố nào đá sân nhà trong cùng 1 ngày.
        2. Không vi phạm lịch bận sân vận động (Stadium Availability).
        3. Không làm giảm số trận cuối tuần dưới mức tối thiểu (`weekend_matches_min`).
        """
        round_dates = get_match_dates(self.season_start, total_rounds=max(38, schedule.total_rounds))
        clash_teams = {team_name for pair in CITY_CLASH_PAIRS for team_name in pair}

        for r_idx, r_num in enumerate(sorted(schedule.fixtures.keys())):
            fx = schedule.fixtures[r_num]
            base_saturday = round_dates[r_idx]
            sunday_date = base_saturday + timedelta(days=1)
            monday_date = base_saturday + timedelta(days=2)
            friday_date = base_saturday - timedelta(days=1)

            # Lọc các trận có đội chủ nhà nằm trong tập có nguy cơ xung đột thành phố
            relevant_matches = [m for m in fx.matches if m.home_team.name in clash_teams]
            if len(relevant_matches) < 2:
                continue

            # Xây dựng miền giá trị (Domain) hợp lệ cho từng trận (Forward-checked với Stadium Availability)
            domains = {}
            for m in relevant_matches:
                is_d = m.is_derby(self.custom_derbies)
                candidate_pool = [base_saturday, sunday_date] if is_d else [base_saturday, sunday_date, monday_date, friday_date]
                valid_dates = [
                    d for d in candidate_pool
                    if not self._is_stadium_unavailable(m.home_team, d)
                ]
                if not valid_dates:
                    valid_dates = [m.date_obj or base_saturday]
                # Ưu tiên giữ nguyên ngày hiện tại nếu hợp lệ để hạn chế xáo trộn không cần thiết
                cur_d = m.date_obj
                if cur_d in valid_dates:
                    valid_dates.sort(key=lambda x: 0 if x == cur_d else (1 if x.weekday() >= 5 else 2))
                domains[m.id] = valid_dates

            # Sắp xếp biến theo heuristic MRV (Minimum Remaining Values - miền giá trị nhỏ nhất xét trước)
            ordered_matches = sorted(relevant_matches, key=lambda m: len(domains[m.id]))
            assignment = {}

            def _is_consistent(match_obj, cand_date) -> bool:
                h_name = match_obj.home_team.name
                for assigned_m_id, assigned_date in assignment.items():
                    if assigned_date != cand_date:
                        continue
                    other_m = next(x for x in ordered_matches if x.id == assigned_m_id)
                    other_h = other_m.home_team.name
                    if frozenset((h_name, other_h)) in CITY_CLASH_PAIRS:
                        return False
                return True

            def _backtrack(idx: int) -> bool:
                if idx == len(ordered_matches):
                    return True
                curr_m = ordered_matches[idx]
                for cand_date in domains[curr_m.id]:
                    if _is_consistent(curr_m, cand_date):
                        assignment[curr_m.id] = cand_date
                        if _backtrack(idx + 1):
                            return True
                        del assignment[curr_m.id]
                return False

            if _backtrack(0):
                for m in ordered_matches:
                    new_d = assignment[m.id]
                    if m.date_obj != new_d:
                        m.date = new_d
                        if m.is_derby(self.custom_derbies) or m.is_prime_time:
                            m.time = dt_time(17, 30) if new_d.weekday() == 6 else dt_time(20, 0)

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
        """
        Đảm bảo chỉ tiêu tổng số trận giờ vàng (`prime_time_matches`) VÀ phân bổ công bằng truyền hình
        (TV Broadcast Fairness: mọi CLB đều có ít nhất 2 trận giờ vàng trong mùa giải).
        """
        target_prime = max(20, int(self.tv_broadcast.get("prime_time_matches", 38)))
        all_matches = schedule.all_matches()

        prime_by_team = {t.name: 0 for t in self.teams}
        current_prime = 0
        for m in all_matches:
            if m.is_prime_time:
                current_prime += 1
                prime_by_team[m.home_team.name] = prime_by_team.get(m.home_team.name, 0) + 1
                prime_by_team[m.away_team.name] = prime_by_team.get(m.away_team.name, 0) + 1

        # Ưu tiên nâng các trận cuối tuần có sự góp mặt của các CLB đang thiếu giờ vàng (< 2 trận)
        weekend_candidates = [m for m in all_matches if m.is_weekend and not m.is_prime_time]
        while True:
            under_quota_teams = {t_name for t_name, cnt in prime_by_team.items() if cnt < 2}
            if not under_quota_teams and current_prime >= target_prime:
                break
            if not weekend_candidates:
                break

            # Chọn trận cuối tuần giúp giảm nhiều nhất số đội đang dưới ngưỡng 2 trận Prime Time
            best_m = max(
                weekend_candidates,
                key=lambda m: (
                    (1 if m.home_team.name in under_quota_teams else 0)
                    + (1 if m.away_team.name in under_quota_teams else 0),
                    -(prime_by_team.get(m.home_team.name, 0) + prime_by_team.get(m.away_team.name, 0))
                )
            )
            if not under_quota_teams and current_prime >= target_prime:
                break
            if under_quota_teams and (
                best_m.home_team.name not in under_quota_teams
                and best_m.away_team.name not in under_quota_teams
                and current_prime >= target_prime
            ):
                break

            best_m.is_prime_time = True
            best_m.time = dt_time(17, 30) if best_m.date_obj and best_m.date_obj.weekday() == 6 else dt_time(20, 0)
            current_prime += 1
            prime_by_team[best_m.home_team.name] = prime_by_team.get(best_m.home_team.name, 0) + 1
            prime_by_team[best_m.away_team.name] = prime_by_team.get(best_m.away_team.name, 0) + 1
            weekend_candidates.remove(best_m)
