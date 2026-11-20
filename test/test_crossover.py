from datetime import datetime
from ga.crossover import crossover
from ga.fitness import evaluate
from ga.repair import repair
from ga.chromosome import Chromosome
from generators.round_robin import generate_round_robin
from generators.initial_population import generate_initial_population
from app.services.scheduler_service import load_teams, load_calendar
from utils.date_utils import get_match_dates, get_time_slots
from utils.validation import validate_schedule


def round_signature(schedule):
    sig = []
    for r in sorted(schedule.fixtures):
        fx = schedule.fixtures[r]
        teams = sorted(
            (m.home_team.id, m.away_team.id)
            for m in fx.matches
        )
        sig.append(tuple(teams))
    return sig


def test_crossover():
    calendar = load_calendar()
    teams = load_teams()

    fixtures = generate_round_robin(teams)
    season_start = datetime(2025, 8, 16)
    round_dates = get_match_dates(season_start=season_start, total_rounds=calendar["rounds"])
    time_slots = get_time_slots()

    population = generate_initial_population(
        fixtures=fixtures,
        population_size=2,
        round_dates=round_dates,
        time_slots=time_slots
    )

    parent1 = Chromosome(population[0])
    parent2 = Chromosome(population[1])

    evaluate(parent1)
    evaluate(parent2)

    child = crossover(parent1, parent2)
    child = repair(child, possible_dates=round_dates, possible_times=time_slots)
    evaluate(child)

    for r, fx in child.schedule.fixtures.items():
        teams_in_r = []
        for m in fx.matches:
            teams_in_r.extend([m.home_team.id, m.away_team.id])
        assert len(teams_in_r) == len(set(teams_in_r)), f"Duplicate team in round {r}"

    assert child.schedule.total_matches() == 380
    assert validate_schedule(child.schedule), "Child schedule after crossover + repair must satisfy hard constraints"
    print("Crossover test passed! Child fitness:", child.fitness)


if __name__ == "__main__":
    test_crossover()
