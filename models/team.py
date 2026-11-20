from .stadium import Stadium


class Team:
    def __init__(self, id: int, name: str, short: str, stadium_id: int, stadium: Stadium):
        self.id = id
        self.name = name
        self.short = short
        self.stadium_id = stadium_id
        self.stadium = stadium

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "short": self.short,
            "stadium_id": self.stadium_id,
            "stadium": self.stadium.name if self.stadium else f"{self.name} Stadium",
            "city": self.stadium.city if self.stadium else ""
        }

    def __repr__(self):
        return f"Team({self.id}, {self.name})"

    def __eq__(self, other):
        if isinstance(other, Team):
            return self.id == other.id
        if isinstance(other, str):
            return self.name == other or self.short == other
        return False

    def __hash__(self):
        return hash(self.id)
