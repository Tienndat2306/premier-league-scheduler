import random
from datetime import datetime, date, time as dt_time
from .team import Team
from utils.derby_utils import is_derby_pair


class Match:
    def __init__(
        self,
        match_id: int,
        home_team: Team,
        away_team: Team,
        round_num: int,
        date=None,
        time=None,
        is_prime_time: bool = False,
        custom_derbies=None
    ):
        self.id = match_id
        self.home_team = home_team
        self.away_team = away_team
        self.round_num = round_num
        self.date = date
        self.time = time
        self.venue = home_team.stadium.name if getattr(home_team, "stadium", None) else f"{home_team.name} Stadium"
        self.city = home_team.stadium.city if getattr(home_team, "stadium", None) else ""
        self.custom_derbies = custom_derbies
        self._is_prime_time = is_prime_time

    def copy(self):
        """Tạo bản sao độc lập của Match"""
        return Match(
            match_id=self.id,
            home_team=self.home_team,
            away_team=self.away_team,
            round_num=self.round_num,
            date=self.date,
            time=self.time,
            is_prime_time=self._is_prime_time,
            custom_derbies=self.custom_derbies
        )

    def randomize_time(self, possible_dates=None, possible_times=None):
        """Random lại ngày và/hoặc giờ thi đấu"""
        if possible_dates:
            self.date = random.choice(possible_dates)
        if possible_times:
            self.time = random.choice(possible_times)

    def is_derby(self, derbies_override=None) -> bool:
        derby_list = derbies_override if derbies_override is not None else self.custom_derbies
        return is_derby_pair(self.home_team, self.away_team, derby_list)

    @property
    def date_obj(self):
        if isinstance(self.date, date):
            return self.date.date() if isinstance(self.date, datetime) else self.date
        if isinstance(self.date, str) and self.date:
            try:
                return datetime.strptime(self.date[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None

    @property
    def date_str(self) -> str:
        if isinstance(self.date, date):
            d = self.date.date() if isinstance(self.date, datetime) else self.date
            return d.isoformat()
        return str(self.date)[:10] if self.date else ""

    @property
    def day_name(self) -> str:
        d = self.date_obj
        return d.strftime("%A") if d else ""

    @property
    def time_str(self) -> str:
        if isinstance(self.time, dt_time):
            return f"{self.time.hour:02d}:{self.time.minute:02d}"
        if isinstance(self.time, str) and self.time:
            return self.time[:5]
        return "15:00"

    @property
    def is_weekend(self) -> bool:
        d = self.date_obj
        return d.weekday() >= 5 if d else False

    @property
    def is_prime_time(self) -> bool:
        if self._is_prime_time:
            return True
        if isinstance(self.time, dt_time):
            return (self.time.hour > 17 or (self.time.hour == 17 and self.time.minute >= 30)) and self.is_weekend
        t_str = self.time_str
        return t_str >= "17:30" and self.is_weekend

    @is_prime_time.setter
    def is_prime_time(self, value: bool):
        self._is_prime_time = bool(value)

    def to_dict(self, derbies_override=None):
        return {
            "id": self.id,
            "round": self.round_num,
            "home": self.home_team.name,
            "away": self.away_team.name,
            "home_id": self.home_team.id,
            "away_id": self.away_team.id,
            "home_short": self.home_team.short,
            "away_short": self.away_team.short,
            "venue": self.home_team.stadium.name if getattr(self.home_team, "stadium", None) else self.venue,
            "city": self.home_team.stadium.city if getattr(self.home_team, "stadium", None) else self.city,
            "date": self.date_str,
            "time": self.time_str,
            "day": self.day_name,
            "is_weekend": self.is_weekend,
            "is_prime_time": self.is_prime_time,
            "is_derby": self.is_derby(derbies_override)
        }

    def __repr__(self):
        return f"Match(R{self.round_num}: {self.home_team.name} vs {self.away_team.name})"
