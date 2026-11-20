import random
from datetime import timedelta
from models.schedule import Schedule
from generators.round_robin import generate_round_robin
from constraints.hard import resolve_schedule_stadium_conflicts
from utils.date_utils import assign_slot_for_match


def get_weekend_dates(base_date):
    saturday = base_date + timedelta(days=(5 - base_date.weekday()) % 7)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday


def generate_initial_population(
    fixtures,
    population_size: int,
    round_dates,
    time_slots,
    teams=None,
    constraints=None
):
    """
    Khởi tạo quần thể ban đầu gồm `population_size` cá thể Schedule hợp lệ 100%.
    Hỗ trợ cả cách truyền `fixtures` trực tiếp (từ epl_scheduler/test) lẫn truyền `teams` + `constraints`.
    """
    constraints = constraints or {}
    custom_derbies = constraints.get("derby_matches")
    stadium_avail = constraints.get("stadium_availability", {})
    tv_broadcast = constraints.get("tv_broadcast", {})
    weekend_min = int(tv_broadcast.get("weekend_matches_min", 7))

    population = []
    half = len(fixtures) // 2

    for idx in range(population_size):
        schedule = Schedule()
        schedule.stadium_availability = dict(stadium_avail)

        # Tạo bộ fixtures đa dạng bằng cách hoán vị đội hoặc hoán vị thứ tự vòng lượt đi / lượt về
        if teams and idx > 0:
            shuffled_teams = list(teams)
            random.shuffle(shuffled_teams)
            candidate_fixtures = generate_round_robin(shuffled_teams, custom_derbies=custom_derbies)
        else:
            candidate_fixtures = [[m.copy() for m in r] for r in fixtures]

        first_leg_indices = list(range(half))
        second_leg_indices = list(range(half, len(candidate_fixtures)))
        if idx > 0:
            random.shuffle(first_leg_indices)
            random.shuffle(second_leg_indices)
        round_indices = first_leg_indices + second_leg_indices

        match_id = 1
        for new_round_idx, old_round_idx in enumerate(round_indices):
            round_num = new_round_idx + 1
            base_saturday, _ = get_weekend_dates(round_dates[new_round_idx])

            round_matches = sorted(
                candidate_fixtures[old_round_idx],
                key=lambda m: 0 if m.is_derby(custom_derbies) else 1
            )

            for m_idx, match in enumerate(round_matches):
                m = match.copy()
                m.id = match_id
                m.round_num = round_num
                m.custom_derbies = custom_derbies
                match_id += 1

                m_date, m_time, is_prime = assign_slot_for_match(
                    base_saturday=base_saturday,
                    match_index=m_idx,
                    total_in_round=len(round_matches),
                    is_derby=m.is_derby(custom_derbies),
                    weekend_min=weekend_min,
                    home_team_name=m.home_team.name,
                    venue_name=m.venue,
                    stadium_avail=stadium_avail
                )
                m.date = m_date
                m.time = m_time if not time_slots else (m_time if m_time in time_slots else random.choice(time_slots))
                m.is_prime_time = is_prime

                schedule.add_match(m)

        if stadium_avail:
            resolve_schedule_stadium_conflicts(schedule, stadium_avail)
        population.append(schedule)

    return population
