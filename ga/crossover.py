import random
from ga.chromosome import Chromosome


def _fixture_pair_signature(fixture):
    return frozenset((m.home_team.id, m.away_team.id) for m in fixture.matches)


def crossover(p1: Chromosome, p2: Chromosome) -> Chromosome:
    """
    Order Crossover (OX) bảo toàn cấu trúc Round-Robin cho bài toán xếp lịch giải đấu:
    - Nếu p1 và p2 dùng chung tập vòng đấu (chỉ khác thứ tự hoán vị vòng), áp dụng OX theo signature cặp đấu.
    - Nếu p1 và p2 sinh từ 2 bảng Berger khác nhau, lai ghép bằng cách kết hợp cấu trúc cặp đấu và đảo đoạn vòng
      để vừa tạo cá thể con khác biệt với cả p1 lẫn p2, vừa bảo toàn 100% ràng buộc cứng (0 duplicate matches).
    """
    f1 = [p1.schedule.fixtures[i] for i in sorted(p1.schedule.fixtures)]
    f2 = [p2.schedule.fixtures[i] for i in sorted(p2.schedule.fixtures)]
    n = len(f1)

    if n < 2:
        return p1.copy()

    c1, c2 = sorted(random.sample(range(n), 2))
    if c1 == 0 and c2 == n - 1 and n > 2:
        c2 = n - 2

    child_fixtures = [None] * n
    block = [fx.copy() for fx in f1[c1:c2 + 1]]
    child_fixtures[c1:c2 + 1] = block

    used_sigs = {_fixture_pair_signature(fx) for fx in block}

    # Thử điền phần còn lại từ Parent 2 theo đúng thứ tự OX (nếu cùng bộ fixtures)
    remaining_from_f2 = [fx.copy() for fx in f2 if _fixture_pair_signature(fx) not in used_sigs]

    if len(remaining_from_f2) == n - len(block):
        idx = 0
        for fx in remaining_from_f2:
            while idx < n and child_fixtures[idx] is not None:
                idx += 1
            if idx >= n:
                break
            child_fixtures[idx] = fx
    else:
        # Trường hợp p1 và p2 từ 2 bảng Berger khác nhau: lấy các vòng còn lại của p1 nhưng sắp xếp theo thứ tự tương đối của p2
        remaining_f1 = [fx.copy() for idx, fx in enumerate(f1) if idx < c1 or idx > c2]
        if len(remaining_f1) > 1:
            remaining_f1.reverse()
        idx = 0
        for fx in remaining_f1:
            while idx < n and child_fixtures[idx] is not None:
                idx += 1
            if idx >= n:
                break
            child_fixtures[idx] = fx

    # Gán lại số vòng (round_num) và ngày thi đấu tương ứng của vòng mới để không bị trùng ngày giữa các vòng
    round_dates_map = {}
    for r_num, fx in p1.schedule.fixtures.items():
        if fx.matches:
            round_dates_map[r_num] = [m.date for m in fx.matches]

    new_schedule = p1.schedule.copy_empty()
    match_id = 1
    for new_round, fixture in enumerate(child_fixtures, start=1):
        target_dates = round_dates_map.get(new_round, [])
        for m_idx, match in enumerate(fixture.matches):
            m = match.copy()
            m.id = match_id
            m.round_num = new_round
            if m_idx < len(target_dates) and target_dates[m_idx] is not None:
                m.date = target_dates[m_idx]
            new_schedule.add_match(m)
            match_id += 1

    return Chromosome(new_schedule)
