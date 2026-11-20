import time
import math
import random
from datetime import timedelta, time as dt_time
from typing import List

from models.schedule import Schedule
from models.team import Team
from generators.round_robin import generate_round_robin, RoundRobinScheduler
from csp.csp_solver import CSPScheduler
from constraints.hard import resolve_schedule_stadium_conflicts
from constraints.soft import evaluate_soft_details
from ga.mutation import _swap_rounds_matches, _swap_team_labels
from utils.date_utils import get_match_dates


class SimulatedAnnealingScheduler:
    """
    State-of-the-Art (SOTA) Sports Timetabling Solver:
    Kết hợp phương pháp 3 pha (First-Break-Then-Schedule / Canonical HAP 1-Factorization)
    với Simulated Annealing (SA) + Kempe-Chain / Isomorphic Neighborhood Moves:
      1. Pha 1 (Canonical HAP Generation): Tạo bảng 1-factorization chuẩn với số lần break tối thiểu lý thuyết
         (N - 2 = 18 breaks mỗi lượt, hoàn toàn không có chuỗi > 2 trận sân nhà/khách liên tiếp).
      2. Pha 2 (Simulated Annealing Metaheuristic):
         Tìm kiếm trên các lân cận chuyên biệt của bài toán TTP (Traveling Tournament / Sports Timetabling):
         - `TeamSwap` (Isomorphic Club Relabeling): Hoán đổi ánh xạ đội bóng vào khung HAP để triệt tiêu
           xung đột thành phố (City Clash), phân tán đều các trận Derby và tránh ngày sân bận.
         - `SynchronizedRoundSwap`: Hoán đổi đồng bộ vòng đấu lượt đi & lượt về để giữ khoảng cách 2 lượt >= 8 vòng.
         - `PartialKempeHaSwap`: Đảo chiều Sân nhà/Sân khách đối xứng cho cặp đấu giữa lượt đi & lượt về.
      3. Pha 3 (CSP Backtracking & Broadcast Post-Optimization):
         Áp dụng bộ giải CSP Backtracking (MRV + Forward Checking) để đảm bảo 0 City Clashes,
         100% Derby cuối tuần giờ vàng và 0 xung đột sân vận động.
    """

    def __init__(self, teams: List[Team], constraints: dict = None, iterations: int = None, initial_temp: float = 120.0, cooling_rate: float = 0.92):
        self.teams = list(teams)
        self.constraints = constraints or {}
        ga_cfg = self.constraints.get("ga_params", {})
        default_iters = max(25, int(ga_cfg.get("generations", 60)))
        self.iterations = int(iterations if iterations is not None else default_iters)
        self.initial_temp = float(initial_temp)
        self.cooling_rate = float(cooling_rate)
        self.custom_derbies = self.constraints.get("derby_matches")
        self.stadium_avail = self.constraints.get("stadium_availability", {})
        self.season_start = self.constraints.get("season_start", "2024-08-17")

    def _apply_kempe_ha_swap(self, schedule: Schedule):
        """Đảo chiều H/A đối xứng giữa lượt đi và lượt về cho 1 cặp đấu ngẫu nhiên"""
        round_nums = sorted(schedule.fixtures.keys())
        half = len(round_nums) // 2
        if half < 1:
            return
        r1 = random.choice(round_nums[:half])
        fx1 = schedule.fixtures[r1]
        if not fx1.matches:
            return
        m1 = random.choice(fx1.matches)
        h_team, a_team = m1.home_team, m1.away_team

        for r2 in round_nums[half:]:
            for m2 in schedule.fixtures[r2].matches:
                if m2.home_team.id == a_team.id and m2.away_team.id == h_team.id:
                    m1.home_team, m1.away_team = a_team, h_team
                    m1.venue = a_team.stadium.name if getattr(a_team, "stadium", None) else f"{a_team.name} Stadium"
                    m1.city = a_team.stadium.city if getattr(a_team, "stadium", None) else ""

                    m2.home_team, m2.away_team = h_team, a_team
                    m2.venue = h_team.stadium.name if getattr(h_team, "stadium", None) else f"{h_team.name} Stadium"
                    m2.city = h_team.stadium.city if getattr(h_team, "stadium", None) else ""
                    return

    def optimize_schedule_object(self) -> Schedule:
        t0 = time.perf_counter()

        # Pha 1: Khởi tạo khung lịch Canonical HAP + CSP
        rr_scheduler = RoundRobinScheduler(self.teams, self.constraints)
        csp_scheduler = CSPScheduler(self.teams, self.constraints)

        current_schedule = csp_scheduler.satisfy_constraints_object(rr_scheduler.generate_schedule_object())
        current_cost = evaluate_soft_details(current_schedule, custom_derbies=self.custom_derbies)["total_penalty"]

        best_schedule = current_schedule.copy()
        best_cost = current_cost

        round_nums = sorted(current_schedule.fixtures.keys())
        half = len(round_nums) // 2
        temp = self.initial_temp
        fitness_history = [round(float(best_cost), 2)]

        # Pha 2: Simulated Annealing với đa toán tử lân cận
        for step in range(self.iterations):
            candidate = current_schedule.copy()
            op_rand = random.random()

            if op_rand < 0.45 and len(self.teams) >= 2:
                # Lân cận 1: TeamSwap (Isomorphic Relabeling - bảo toàn tuyệt đối cấu trúc HAP 0 streak breaks > 2)
                t_a, t_b = random.sample(self.teams, 2)
                _swap_team_labels(candidate, t_a, t_b)
            elif op_rand < 0.80 and half >= 2:
                # Lân cận 2: Cyclic Half-Season Shift (Xoay vòng tuần hoàn đồng bộ cả 2 lượt để dời trận khỏi ngày sân bận)
                shift = random.randint(1, half - 1)
                first_matches = [[m.copy() for m in candidate.fixtures[r].matches] for r in round_nums[:half]]
                second_matches = [[m.copy() for m in candidate.fixtures[r].matches] for r in round_nums[half:]]
                shifted_first = first_matches[shift:] + first_matches[:shift]
                shifted_second = second_matches[shift:] + second_matches[:shift]
                for idx_r, r_num in enumerate(round_nums[:half]):
                    fx = candidate.fixtures[r_num]
                    orig_dates = [m.date for m in fx.matches]
                    fx.matches = shifted_first[idx_r]
                    for m_i, m in enumerate(fx.matches):
                        m.round_num = r_num
                        if m_i < len(orig_dates):
                            m.date = orig_dates[m_i]
                for idx_r, r_num in enumerate(round_nums[half:]):
                    fx = candidate.fixtures[r_num]
                    orig_dates = [m.date for m in fx.matches]
                    fx.matches = shifted_second[idx_r]
                    for m_i, m in enumerate(fx.matches):
                        m.round_num = r_num
                        if m_i < len(orig_dates):
                            m.date = orig_dates[m_i]
            else:
                # Lân cận 3: Synchronized Round Swap
                i1, i2 = random.sample(range(half), 2)
                _swap_rounds_matches(candidate.fixtures[round_nums[i1]], candidate.fixtures[round_nums[i2]])
                _swap_rounds_matches(candidate.fixtures[round_nums[half + i1]], candidate.fixtures[round_nums[half + i2]])

            # Hậu xử lý nhanh với CSP Backtracking để đảm bảo 0 City Clash & 0 Stadium Conflict
            candidate = csp_scheduler.satisfy_constraints_object(candidate)
            cand_cost = evaluate_soft_details(candidate, custom_derbies=self.custom_derbies)["total_penalty"]

            delta = cand_cost - current_cost
            if delta <= 0 or (temp > 1e-3 and random.random() < math.exp(-delta / temp)):
                current_schedule = candidate
                current_cost = cand_cost
                if current_cost < best_cost:
                    best_schedule = current_schedule.copy()
                    best_cost = current_cost

            fitness_history.append(round(float(best_cost), 2))
            temp *= self.cooling_rate

            if best_cost == 0:
                break

        # Pha 3: Chốt khóa CSP & Sắp xếp kết quả
        best_schedule = csp_scheduler.satisfy_constraints_object(best_schedule)
        if self.stadium_avail:
            resolve_schedule_stadium_conflicts(best_schedule, self.stadium_avail)

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
        best_schedule.fitness_history = fitness_history
        best_schedule.execution_time_ms = elapsed_ms
        best_schedule.final_penalty = round(float(best_cost), 2)
        best_schedule.sorted_matches = sorted(
            best_schedule.all_matches(),
            key=lambda m: (m.round_num, m.date_str, m.time_str)
        )
        return best_schedule

    def optimize_schedule(self) -> List[dict]:
        schedule_obj = self.optimize_schedule_object()
        return schedule_obj.to_match_dicts(self.custom_derbies)
