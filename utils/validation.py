from constraints.hard import check_hard_constraints


def validate_schedule(schedule) -> bool:
    """True nếu lịch thi đấu thỏa mãn 100% ràng buộc cứng (Hard Constraints)"""
    return check_hard_constraints(schedule) == 0
