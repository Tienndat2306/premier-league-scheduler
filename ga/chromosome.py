class Chromosome:
    """
    1 cá thể GA đại diện cho 1 Schedule
    """

    def __init__(self, schedule):
        self.schedule = schedule
        self.fitness = None

    def copy(self):
        c = Chromosome(self.schedule.copy())
        c.fitness = self.fitness
        return c
