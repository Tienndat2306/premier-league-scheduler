from typing import List
from .match import Match


class Fixture:
    """
    Đại diện cho MỘT VÒNG ĐẤU (Fixture)
    - Chứa 10 trận đấu (Match)
    - Mỗi đội chỉ được xuất hiện đúng 1 lần trong vòng
    """

    def __init__(self, round_num: int):
        self.round_num = round_num
        self.matches: List[Match] = []

    def add_match(self, match: Match):
        if match.round_num != self.round_num:
            raise ValueError(f"Match round ({match.round_num}) != Fixture round ({self.round_num})")

        if self.has_team(match.home_team) or self.has_team(match.away_team):
            raise ValueError(f"Một đội không thể đá 2 trận trong cùng vòng {self.round_num}")

        self.matches.append(match)

    def has_team(self, team) -> bool:
        return any(
            team == m.home_team or team == m.away_team
            for m in self.matches
        )

    def teams_in_round(self):
        teams = []
        for m in self.matches:
            teams.extend([m.home_team, m.away_team])
        return teams

    def derby_matches(self):
        return [m for m in self.matches if m.is_derby()]

    def copy(self):
        new_fx = Fixture(self.round_num)
        new_fx.matches = [m.copy() for m in self.matches]
        return new_fx

    def to_dict(self, derbies_override=None):
        return {
            "round": self.round_num,
            "matches": [m.to_dict(derbies_override) for m in self.matches]
        }

    def __repr__(self):
        return f"Fixture(Round {self.round_num}, Matches={len(self.matches)})"
