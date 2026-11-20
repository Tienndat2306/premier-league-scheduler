from typing import Dict, List
from .fixture import Fixture
from .match import Match


class Schedule:
    """
    Đại diện cho TOÀN BỘ MÙA GIẢI (38 vòng, 380 trận)
    - Gồm nhiều Fixture (38 vòng)
    - Là 1 Chromosome trong Genetic Algorithm
    """

    def __init__(self):
        self.fixtures: Dict[int, Fixture] = {}
        self.sorted_matches: List[Match] = []
        self.season_start = None
        self.season_end = None
        self.fitness_history: List[float] = []
        self.execution_time_ms: float = 0.0
        self.final_penalty: float = 0.0
        self.stadium_availability: dict = {}
        self.team_requests: dict = {}

    @property
    def total_rounds(self) -> int:
        return len(self.fixtures)

    def copy_empty(self):
        """Tạo schedule mới với cùng số vòng nhưng chưa có trận đấu"""
        new_schedule = Schedule()
        for round_num in self.fixtures.keys():
            new_schedule.fixtures[round_num] = Fixture(round_num)
        new_schedule.season_start = self.season_start
        new_schedule.season_end = self.season_end
        new_schedule.stadium_availability = dict(self.stadium_availability)
        new_schedule.team_requests = dict(self.team_requests)
        return new_schedule

    def copy(self):
        """Deep copy toàn bộ Schedule"""
        new_schedule = Schedule()
        for round_num, fx in self.fixtures.items():
            new_schedule.fixtures[round_num] = fx.copy()
        new_schedule.season_start = self.season_start
        new_schedule.season_end = self.season_end
        new_schedule.fitness_history = list(self.fitness_history)
        new_schedule.execution_time_ms = self.execution_time_ms
        new_schedule.final_penalty = self.final_penalty
        new_schedule.stadium_availability = dict(self.stadium_availability)
        new_schedule.team_requests = dict(self.team_requests)
        return new_schedule

    def add_match(self, match: Match):
        round_num = match.round_num
        if round_num not in self.fixtures:
            self.fixtures[round_num] = Fixture(round_num)
        self.fixtures[round_num].add_match(match)

    def get_fixture(self, round_num: int) -> Fixture | None:
        return self.fixtures.get(round_num)

    def get_match_by_id(self, match_id: int):
        for fixture in self.fixtures.values():
            for match in fixture.matches:
                if match.id == match_id:
                    return match
        return None

    def all_matches(self) -> List[Match]:
        matches = []
        for round_num in sorted(self.fixtures.keys()):
            matches.extend(self.fixtures[round_num].matches)
        return matches

    def total_matches(self) -> int:
        return len(self.all_matches())

    def derby_matches(self) -> List[Match]:
        return [m for m in self.all_matches() if m.is_derby()]

    def is_valid(self) -> bool:
        for fixture in self.fixtures.values():
            if len(fixture.matches) != 10:
                return False
        return True

    def to_match_dicts(self, derbies_override=None) -> List[dict]:
        """Xuất danh sách 380 trận dạng List[dict] cho API / Frontend / DataTables"""
        return [m.to_dict(derbies_override) for m in self.all_matches()]

    def to_dict(self, derbies_override=None):
        return {
            "total_rounds": len(self.fixtures),
            "total_matches": self.total_matches(),
            "fixtures": [
                fixture.to_dict(derbies_override)
                for fixture in sorted(self.fixtures.values(), key=lambda f: f.round_num)
            ]
        }

    def __repr__(self):
        return f"Schedule(Rounds={len(self.fixtures)}, Matches={self.total_matches()})"
