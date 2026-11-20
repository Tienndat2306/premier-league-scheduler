import random


def tournament_selection(population, k: int = 3):
    k_actual = min(k, len(population.chromosomes))
    candidates = random.sample(population.chromosomes, k_actual)
    return min(candidates, key=lambda c: c.fitness if c.fitness is not None else float("inf"))
