from datetime import datetime
from ga.crossover import crossover
from ga.fitness import evaluate
from ga.repair import repair
from ga.chromosome import Chromosome
from ga.selection import tournament_selection
from ga.population import Population
from ga.mutation import mutate
from generators.round_robin import generate_round_robin
from generators.initial_population import generate_initial_population
from app.services.scheduler_service import load_teams, load_calendar
from utils.date_utils import get_match_dates, get_time_slots
from utils.validation import validate_schedule


def test_ga_pipeline():
    population_size = 10
    generations = 10
    mutation_rate = 0.2
    tournament_k = 3

    print("Loading data...")
    calendar = load_calendar()
    teams = load_teams()
    fixtures = generate_round_robin(teams)

    season_start = datetime(2025, 8, 16)
    round_dates = get_match_dates(
        season_start=season_start,
        total_rounds=calendar["rounds"]
    )
    time_slots = get_time_slots()

    initial_population = generate_initial_population(
        fixtures=fixtures,
        population_size=population_size,
        round_dates=round_dates,
        time_slots=time_slots
    )

    population = Population([Chromosome(s) for s in initial_population])
    for c in population.chromosomes:
        evaluate(c)

    print("Initial population created")

    for gen in range(generations):
        fitness_values = [c.fitness for c in population.chromosomes]
        new_population = [population.best().copy()]

        while len(new_population) < population_size:
            p1 = tournament_selection(population, k=tournament_k)
            p2 = tournament_selection(population, k=tournament_k)

            child = crossover(p1, p2)
            mutate(
                child,
                mutation_rate=mutation_rate,
                possible_dates=round_dates,
                possible_times=time_slots
            )
            repair(child, possible_dates=round_dates, possible_times=time_slots)
            evaluate(child)
            new_population.append(child)

        population = Population(new_population)
        best = population.best()
        print(f"Gen {gen + 1}/{generations}: best penalty = {best.fitness} (min={min(fitness_values)})")

        if best.fitness == 0:
            break

    best = population.best()
    assert best.schedule.total_matches() == 380, "Total matches must be 380"
    assert validate_schedule(best.schedule), "Best schedule must satisfy all hard constraints"
    print("GA pipeline test passed! Final best fitness:", best.fitness)


if __name__ == "__main__":
    test_ga_pipeline()
