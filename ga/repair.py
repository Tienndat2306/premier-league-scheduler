from datetime import timedelta, time
from constraints.hard import check_hard_constraints, resolve_schedule_stadium_conflicts


def repair(chromosome, possible_dates=None, possible_times=None, stadium_avail=None):
    """
    Sửa lỗi vi phạm ràng buộc cứng (nếu có) trên một Chromosome:
    1. Giải quyết triệt để mọi xung đột lịch bận sân vận động (stadium_availability).
    2. Đảm bảo mỗi vòng đấu có ngày/giờ hợp lệ và không đội nào bị trùng ngày/giờ.
    """
    schedule = chromosome.schedule
    avail = stadium_avail if stadium_avail is not None else getattr(schedule, "stadium_availability", None)
    if avail:
        resolve_schedule_stadium_conflicts(schedule, avail)

    if check_hard_constraints(schedule, avail) == 0:
        return chromosome

    default_times = possible_times or [time(12, 30), time(15, 0), time(17, 30), time(20, 0)]

    for r_idx, r_num in enumerate(sorted(schedule.fixtures.keys())):
        fx = schedule.fixtures[r_num]
        base_date = None
        if possible_dates and r_idx < len(possible_dates):
            base_date = possible_dates[r_idx]
        elif fx.matches and fx.matches[0].date_obj:
            base_date = fx.matches[0].date_obj

        for m_idx, match in enumerate(fx.matches):
            if not match.date_obj and base_date:
                offset = 0 if m_idx < 6 else 1
                match.date = base_date + timedelta(days=offset)
            if not match.time:
                match.time = default_times[m_idx % len(default_times)]

    if avail:
        resolve_schedule_stadium_conflicts(schedule, avail)

    return chromosome
