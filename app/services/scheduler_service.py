import json
import os
import copy
import time
from typing import List, Tuple, Dict

from models.team import Team
from models.stadium import Stadium
from models.schedule import Schedule
from generators.round_robin import RoundRobinScheduler
from ga.ga_engine import GAScheduler
from csp.csp_solver import CSPScheduler
from csp.hybrid import HybridScheduler
from constraints.soft import evaluate_soft_details

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_teams() -> List[Team]:
    """Đọc danh sách đối tượng Team & Stadium từ data/teams.json và data/stadiums.json"""
    stadiums_path = os.path.join(DATA_DIR, "stadiums.json")
    teams_path = os.path.join(DATA_DIR, "teams.json")

    with open(stadiums_path, "r", encoding="utf-8") as f:
        stadium_data = json.load(f)

    stadiums = {
        s["id"]: Stadium(**s)
        for s in stadium_data
    }

    with open(teams_path, "r", encoding="utf-8") as f:
        team_data = json.load(f)

    teams = []
    for t in team_data:
        teams.append(
            Team(
                id=t["id"],
                name=t["name"],
                short=t["short"],
                stadium_id=t["stadium_id"],
                stadium=stadiums[t["stadium_id"]]
            )
        )

    return teams


def load_calendar() -> dict:
    """Đọc cấu hình mùa giải từ data/calendar.json"""
    calendar_path = os.path.join(DATA_DIR, "calendar.json")
    with open(calendar_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    return {
        "season": data.get("season", "Premier League Schedule"),
        "season_start": data.get("season_start", "2024-08-17"),
        "rounds": data.get("rounds", 38),
        "matches_per_round": data.get("matches_per_round", 10),
        "match_days": data.get("match_days", ["Saturday", "Sunday"]),
        "time_slots": data.get("time_slots", ["12:30", "15:00", "17:30", "20:00"])
    }


def load_project_metadata() -> Tuple[List[str], Dict[str, dict], List[List[str]]]:
    """Trả về (danh sách tên CLB, metadata từng CLB, danh sách cặp Derby mặc định)"""
    teams = load_teams()
    clubs = [t.name for t in teams]
    team_metadata = {t.name: t.to_dict() for t in teams}

    derbies_path = os.path.join(DATA_DIR, "derbies.json")
    derbies = [
        ["Manchester United", "Manchester City"],
        ["Liverpool", "Everton"],
        ["Arsenal", "Tottenham"],
        ["Chelsea", "Tottenham"]
    ]
    if os.path.exists(derbies_path):
        try:
            with open(derbies_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list) and loaded:
                    short_to_name = {t.short: t.name for t in teams}
                    normalized = []
                    for pair in loaded:
                        if isinstance(pair, list) and len(pair) >= 2:
                            t1 = short_to_name.get(pair[0], pair[0])
                            t2 = short_to_name.get(pair[1], pair[1])
                            normalized.append([t1, t2])
                    if normalized:
                        derbies = normalized
        except Exception:
            pass

    return clubs, team_metadata, derbies


def resolve_team_objects(club_names: List[str] = None) -> List[Team]:
    """Ánh xạ danh sách tên đội bóng sang danh sách đối tượng OOP `Team`"""
    all_teams = load_teams()
    if not club_names:
        return all_teams

    team_by_name = {t.name: t for t in all_teams}
    team_by_short = {t.short: t for t in all_teams}
    resolved = []
    for idx, name in enumerate(club_names, start=1):
        if isinstance(name, Team):
            resolved.append(name)
        elif name in team_by_name:
            resolved.append(team_by_name[name])
        elif name in team_by_short:
            resolved.append(team_by_short[name])
        else:
            st = Stadium(id=100 + idx, name=f"{name} Stadium", city="England")
            resolved.append(Team(id=100 + idx, name=str(name), short=str(name)[:3].upper(), stadium_id=st.id, stadium=st))
    return resolved


def generate_schedule_by_algorithm(
    algorithm: str = "round_robin",
    clubs: List[str] = None,
    constraints: dict = None
) -> Tuple[Schedule, List[dict]]:
    """
    Điểm điều phối trung tâm (Service Layer) cho cả 4 thuật toán:
    - `round_robin`: RoundRobinScheduler
    - `genetic`: GAScheduler (modular `ga/` package)
    - `csp`: CSPScheduler (`csp/csp_solver.py`)
    - `hybrid`: HybridScheduler (`csp/hybrid.py` = RR + GA + CSP)
    Trả về cả đối tượng OOP `Schedule` và danh sách `List[dict]` đã serialize.
    """
    t0 = time.perf_counter()
    constraints = copy.deepcopy(constraints or {})
    team_objs = resolve_team_objects(clubs)
    custom_derbies = constraints.get("derby_matches")

    if algorithm == "round_robin":
        scheduler = RoundRobinScheduler(team_objs, constraints)
        schedule_obj = scheduler.generate_schedule_object()
    elif algorithm == "genetic":
        scheduler = GAScheduler(team_objs, constraints)
        schedule_obj = scheduler.optimize_schedule_object()
    elif algorithm == "csp":
        scheduler = CSPScheduler(team_objs, constraints)
        schedule_obj = scheduler.solve_object()
    elif algorithm == "hybrid":
        scheduler = HybridScheduler(team_objs, constraints)
        schedule_obj = scheduler.generate_hybrid_schedule_object()
    else:
        raise ValueError(f'Algorithm "{algorithm}" not supported')

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 2)
    schedule_obj.execution_time_ms = elapsed_ms
    soft_details = evaluate_soft_details(schedule_obj, custom_derbies=custom_derbies)
    schedule_obj.final_penalty = soft_details["total_penalty"]

    match_dicts = schedule_obj.to_match_dicts(custom_derbies)
    return schedule_obj, match_dicts


def generate_schedule(
    season_start="2024-08-17",
    population_size: int = 40,
    generations: int = 80,
    mutation_rate: float = 0.25
) -> Schedule:
    """Hàm tương thích ngược với `epl_scheduler` service"""
    _, team_metadata, derbies = load_project_metadata()
    constraints = {
        "season_start": str(season_start),
        "derby_matches": derbies,
        "ga_params": {
            "population_size": population_size,
            "generations": generations,
            "mutation_rate": mutation_rate
        },
        "team_metadata": team_metadata
    }
    schedule_obj, _ = generate_schedule_by_algorithm("genetic", constraints=constraints)
    return schedule_obj
