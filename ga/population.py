class Population:
    def __init__(self, chromosomes):
        self.chromosomes = chromosomes

    def best(self):
        return min(self.chromosomes, key=lambda c: c.fitness if c.fitness is not None else float("inf"))

    def sort(self):
        self.chromosomes.sort(key=lambda c: c.fitness if c.fitness is not None else float("inf"))
