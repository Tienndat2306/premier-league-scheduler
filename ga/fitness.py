from constraints.hard import check_hard_constraints
from constraints.soft import soft_penalty

HARD_PENALTY = 1_000_000


def evaluate(chromosome, custom_derbies=None):
    """
    Đánh giá độ thích nghi (Penalty - càng nhỏ càng tốt) của 1 Chromosome.
    Nếu vi phạm ràng buộc cứng -> phạt HARD_PENALTY * số lỗi.
    Nếu không vi phạm ràng buộc cứng -> tính điểm phạt ràng buộc mềm (soft_penalty).
    """
    schedule = chromosome.schedule

    hard = check_hard_constraints(schedule)
    if hard > 0:
        chromosome.fitness = HARD_PENALTY * hard
        return chromosome.fitness

    chromosome.fitness = soft_penalty(schedule, custom_derbies=custom_derbies)
    return chromosome.fitness
