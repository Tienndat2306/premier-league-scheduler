from generators.round_robin import RoundRobinScheduler
from ga.ga_engine import GAScheduler
from csp.csp_solver import CSPScheduler
from models.schedule import Schedule


class HybridScheduler:
    """
    Hybrid Scheduler (Round Robin -> Genetic Algorithm -> CSP Solver)
    hoạt động trực tiếp trên mô hình OOP `Schedule`.
    """

    def __init__(self, teams, constraints=None):
        self.teams = list(teams)
        self.constraints = constraints or {}

    def generate_hybrid_schedule_object(self) -> Schedule:
        print("\n" + "=" * 60)
        print("  HYBRID SCHEDULER - FULL PIPELINE (RR -> GA -> CSP)")
        print("=" * 60)

        # Bước 1: Round Robin
        print("\n[1/3] ROUND ROBIN: Tạo khung lịch OOP cơ bản...")
        rr_scheduler = RoundRobinScheduler(self.teams, self.constraints)
        base_schedule = rr_scheduler.generate_schedule_object()
        print(f"  -> Đã tạo: {base_schedule.total_matches()} trận đấu")

        # Bước 2: Genetic Algorithm
        print("\n[2/3] GENETIC ALGORITHM: Tối ưu hóa lịch thi đấu...")
        ga_scheduler = GAScheduler(self.teams, self.constraints)
        optimized_schedule = ga_scheduler.refine_schedule_object(base_schedule)
        print(f"  -> Đã tối ưu: {optimized_schedule.total_matches()} trận đấu")

        # Bước 3: Constraint Satisfaction (CSP)
        print("\n[3/3] CONSTRAINT SATISFACTION: Áp dụng & kiểm tra ràng buộc...")
        csp_scheduler = CSPScheduler(self.teams, self.constraints)
        final_schedule = csp_scheduler.satisfy_constraints_object(optimized_schedule)
        print(f"  -> Hoàn thành: {final_schedule.total_matches()} trận đấu")

        return final_schedule

    def generate_hybrid_schedule(self):
        schedule_obj = self.generate_hybrid_schedule_object()
        return schedule_obj.to_match_dicts(self.constraints.get("derby_matches"))


def create_hybrid_scheduler(teams, constraints=None, use_simple=False):
    return HybridScheduler(teams, constraints)
