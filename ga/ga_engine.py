import time
import random
from ga.population import Population
from ga.chromosome import Chromosome
from ga.selection import tournament_selection
from ga.crossover import crossover
from ga.mutation import mutate, _swap_rounds_matches, _swap_team_labels
from ga.repair import repair
from ga.fitness import evaluate
from constraints.hard import resolve_schedule_stadium_conflicts
from generators.round_robin import generate_round_robin
from generators.initial_population import generate_initial_population
from utils.date_utils import get_match_dates, get_time_slots


def memetic_local_search(
    chromosome: Chromosome,
    steps: int = 4,
    possible_dates=None,
    possible_times=None,
    custom_derbies=None,
    stadium_avail=None
) -> Chromosome:
    """
    Pha tìm kiếm cục bộ (Memetic Hill-Climbing Local Search) trên cá thể ưu tú (Elite):
    Thử các phép biến đổi cấu trúc (TeamSwap hoặc Synchronized RoundSwap) và chỉ chấp nhận nếu giảm điểm phạt.
    """
    best_c = chromosome
    if best_c.fitness is None:
        evaluate(best_c, custom_derbies=custom_derbies)

    round_nums = sorted(best_c.schedule.fixtures.keys())
    half = len(round_nums) // 2
    if half < 2:
        return best_c

    first_fx = best_c.schedule.fixtures[round_nums[0]]
    all_teams = []
    for m in first_fx.matches:
        all_teams.extend([m.home_team, m.away_team])

    for _ in range(steps):
        cand = best_c.copy()
        if len(all_teams) >= 2 and random.random() < 0.6:
            t_a, t_b = random.sample(all_teams, 2)
            _swap_team_labels(cand.schedule, t_a, t_b)
        else:
            i1, i2 = random.sample(range(half), 2)
            _swap_rounds_matches(cand.schedule.fixtures[round_nums[i1]], cand.schedule.fixtures[round_nums[i2]])
            _swap_rounds_matches(cand.schedule.fixtures[round_nums[half + i1]], cand.schedule.fixtures[round_nums[half + i2]])

        repair(cand, possible_dates=possible_dates, possible_times=possible_times, stadium_avail=stadium_avail)
        evaluate(cand, custom_derbies=custom_derbies)
        if cand.fitness < best_c.fitness:
            best_c = cand

    return best_c


def run_ga(
    initial_schedules,
    generations: int = 80,
    population_size: int = 40,
    mutation_rate: float = 0.25,
    elitism: bool = True,
    possible_dates=None,
    possible_times=None,
    custom_derbies=None,
    stadium_avail=None
) -> Chromosome:
    """
    Bộ máy thực thi Memetic Genetic Algorithm (GA Engine) cốt lõi:
    Selection (Tournament) -> Order & Polarity Crossover -> Multi-Operator Mutation -> Repair -> Evaluation -> Elite Local Search.
    Lưu lại lịch sử hội tụ `fitness_history` và `execution_time_ms` trên đối tượng Schedule tốt nhất.
    """
    t0 = time.perf_counter()
    population = Population([
        Chromosome(s) for s in initial_schedules
    ])

    for c in population.chromosomes:
        if stadium_avail:
            c.schedule.stadium_availability = dict(stadium_avail)
        repair(c, possible_dates=possible_dates, possible_times=possible_times, stadium_avail=stadium_avail)
        evaluate(c, custom_derbies=custom_derbies)

    fitness_history = []

    for gen in range(generations):
        new_population = []

        # 1. Elitism + Memetic Local Search trên cá thể tốt nhất
        if elitism:
            elite = population.best().copy()
            if gen % 3 == 0:
                elite = memetic_local_search(
                    elite,
                    steps=2,
                    possible_dates=possible_dates,
                    possible_times=possible_times,
                    custom_derbies=custom_derbies,
                    stadium_avail=stadium_avail
                )
            new_population.append(elite)

        # 2. Sinh thế hệ mới
        while len(new_population) < population_size:
            p1 = tournament_selection(population)
            p2 = tournament_selection(population)

            child = crossover(p1, p2)

            mutate(
                child,
                mutation_rate=mutation_rate,
                possible_dates=possible_dates,
                possible_times=possible_times
            )

            repair(child, possible_dates=possible_dates, possible_times=possible_times, stadium_avail=stadium_avail)
            evaluate(child, custom_derbies=custom_derbies)

            new_population.append(child)

        population = Population(new_population[:population_size])
        best = population.best()
        fitness_history.append(round(float(best.fitness), 2))

        if gen % 20 == 0 or gen == generations - 1:
            print(f"GA Gen {gen + 1}/{generations}: best penalty = {best.fitness}")

        # 3. Dừng sớm nếu đạt nghiệm tối ưu tuyệt đối
        if best.fitness == 0:
            print("Optimal schedule found (penalty = 0)")
            break

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    best_chrom = population.best()
    repair(best_chrom, possible_dates=possible_dates, possible_times=possible_times, stadium_avail=stadium_avail)
    evaluate(best_chrom, custom_derbies=custom_derbies)
    best_chrom.schedule.fitness_history = fitness_history
    best_chrom.schedule.execution_time_ms = elapsed_ms
    best_chrom.schedule.final_penalty = round(float(best_chrom.fitness), 2)
    return best_chrom


class GAScheduler:
    """
    Lớp bao bọc (Facade) kết nối hệ thống package `ga/` với `scheduler_service` và `HybridScheduler`.
    """

    def __init__(self, teams, constraints=None, population_size=None, generations=None, mutation_rate=None):
        self.teams = list(teams)
        self.constraints = constraints or {}
        ga_cfg = self.constraints.get("ga_params", {})

        self.population_size = int(population_size if population_size is not None else ga_cfg.get("population_size", 40))
        self.generations = int(generations if generations is not None else ga_cfg.get("generations", 80))
        self.mutation_rate = float(mutation_rate if mutation_rate is not None else ga_cfg.get("mutation_rate", 0.25))
        self.custom_derbies = self.constraints.get("derby_matches")
        self.stadium_avail = self.constraints.get("stadium_availability", {})
        self.season_start = self.constraints.get("season_start", "2024-08-17")

    def optimize_schedule_object(self):
        fixtures = generate_round_robin(self.teams, custom_derbies=self.custom_derbies)
        round_dates = get_match_dates(self.season_start, total_rounds=len(fixtures))
        time_slots = get_time_slots()

        initial_schedules = generate_initial_population(
            fixtures=fixtures,
            population_size=self.population_size,
            round_dates=round_dates,
            time_slots=time_slots,
            teams=self.teams,
            constraints=self.constraints
        )

        best_chrom = run_ga(
            initial_schedules=initial_schedules,
            generations=self.generations,
            population_size=self.population_size,
            mutation_rate=self.mutation_rate,
            possible_dates=round_dates,
            possible_times=time_slots,
            custom_derbies=self.custom_derbies,
            stadium_avail=self.stadium_avail
        )

        best_schedule = best_chrom.schedule
        if self.stadium_avail:
            resolve_schedule_stadium_conflicts(best_schedule, self.stadium_avail)
        best_schedule.sorted_matches = sorted(
            best_schedule.all_matches(),
            key=lambda m: (m.round_num, m.date_str, m.time_str)
        )
        return best_schedule

    def optimize_schedule(self):
        schedule_obj = self.optimize_schedule_object()
        return schedule_obj.to_match_dicts(self.custom_derbies)

    def refine_schedule_object(self, base_schedule_obj):
        """
        Tinh chỉnh từ một đối tượng Schedule có sẵn (dùng cho HybridScheduler):
        Kết hợp cá thể gốc từ Round Robin với quần thể đa dạng (shuffled Berger + cyclic shifts)
        và chạy đủ số thế hệ để đảm bảo Hybrid luôn đạt chất lượng tốt hơn hoặc bằng GA độc lập.
        """
        total_r = base_schedule_obj.total_rounds or 38
        round_dates = get_match_dates(self.season_start, total_rounds=total_r)
        time_slots = get_time_slots()

        base_copy = base_schedule_obj.copy()
        if self.stadium_avail:
            base_copy.stadium_availability = dict(self.stadium_avail)
            resolve_schedule_stadium_conflicts(base_copy, self.stadium_avail)

        fixtures = generate_round_robin(self.teams, custom_derbies=self.custom_derbies)
        diverse_pop = generate_initial_population(
            fixtures=fixtures,
            population_size=max(4, self.population_size),
            round_dates=round_dates,
            time_slots=time_slots,
            teams=self.teams,
            constraints=self.constraints
        )
        initial_schedules = [base_copy] + diverse_pop[:max(3, self.population_size - 1)]

        best_chrom = run_ga(
            initial_schedules=initial_schedules,
            generations=self.generations,
            population_size=len(initial_schedules),
            mutation_rate=self.mutation_rate,
            possible_dates=round_dates,
            possible_times=time_slots,
            custom_derbies=self.custom_derbies,
            stadium_avail=self.stadium_avail
        )

        best_schedule = best_chrom.schedule
        if self.stadium_avail:
            resolve_schedule_stadium_conflicts(best_schedule, self.stadium_avail)
        best_schedule.sorted_matches = sorted(
            best_schedule.all_matches(),
            key=lambda m: (m.round_num, m.date_str, m.time_str)
        )
        return best_schedule
