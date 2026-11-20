import random
from ga.chromosome import Chromosome


def _fixture_unordered_signature(fixture):
    return frozenset(frozenset((m.home_team.id, m.away_team.id)) for m in fixture.matches)


def _apply_ha_polarity_from_parent(child_fixtures, donor_schedule):
    """
    Kế thừa chiều Sân nhà / Sân khách (H/A polarity) cho một tập ngẫu nhiên các cặp đội
    từ cá thể cha/mẹ thứ hai `donor_schedule`, đồng bộ đối xứng cả Lượt đi và Lượt về
    để bảo toàn 100% ràng buộc Double Round-Robin (1 trận sân nhà, 1 trận sân khách).
    """
    donor_first_home = {}
    for r_num in sorted(donor_schedule.fixtures.keys()):
        for m in donor_schedule.fixtures[r_num].matches:
            pair = frozenset((m.home_team.id, m.away_team.id))
            if pair not in donor_first_home:
                donor_first_home[pair] = m.home_team.id

    all_pairs = list(donor_first_home.keys())
    if not all_pairs:
        return

    # Chọn ngẫu nhiên 40% - 60% cặp đấu để thừa hưởng H/A orientation từ Parent 2
    inherited_pairs = set(random.sample(all_pairs, k=max(1, len(all_pairs) // 2)))
    seen_in_child = set()

    for fx in child_fixtures:
        for m in fx.matches:
            pair = frozenset((m.home_team.id, m.away_team.id))
            if pair not in inherited_pairs:
                continue
            desired_first_home_id = donor_first_home[pair]
            is_first_encounter = pair not in seen_in_child
            seen_in_child.add(pair)

            should_be_home_id = desired_first_home_id if is_first_encounter else (
                m.away_team.id if m.home_team.id == desired_first_home_id else m.home_team.id
            )
            # Hoặc xác định rõ đội còn lại trong cặp:
            other_id = next(iter(pair - {desired_first_home_id}))
            target_home_id = desired_first_home_id if is_first_encounter else other_id

            if m.home_team.id != target_home_id:
                m.home_team, m.away_team = m.away_team, m.home_team
                m.venue = m.home_team.stadium.name if getattr(m.home_team, "stadium", None) else f"{m.home_team.name} Stadium"
                m.city = m.home_team.stadium.city if getattr(m.home_team, "stadium", None) else ""


def crossover(p1: Chromosome, p2: Chromosome) -> Chromosome:
    """
    Order Crossover (OX) kết hợp H/A Polarity Uniform Crossover bảo toàn 100% cấu trúc Round-Robin:
    1. Nếu p1 và p2 dùng chung bảng phân cặp Berger (chỉ khác hoán vị vòng hoặc chiều H/A),
       áp dụng Half-season Order Crossover (OX) độc lập trên Lượt đi và Lượt về, sau đó lai ghép H/A polarity.
    2. Nếu p1 và p2 sinh từ 2 phép gán nhãn đội Berger khác nhau, lấy khung cặp đấu của một cha/mẹ,
       áp dụng OX trên thứ tự chỉ số vòng tương đối và kế thừa mặt nạ Sân nhà/Sân khách (H/A polarity)
       cũng như khung giờ phát sóng từ cha/mẹ còn lại.
    """
    f1 = [p1.schedule.fixtures[i] for i in sorted(p1.schedule.fixtures)]
    f2 = [p2.schedule.fixtures[i] for i in sorted(p2.schedule.fixtures)]
    n = len(f1)

    if n < 2:
        return p1.copy()

    half = n // 2
    c1, c2 = sorted(random.sample(range(half), 2))
    if c1 == 0 and c2 == half - 1 and half > 2:
        c2 = half - 2

    # Kiểm tra xem p1 và p2 có cùng bộ 1-factorization ở lượt đi hay không
    sigs1_first = {_fixture_unordered_signature(fx) for fx in f1[:half]}
    sigs2_first = {_fixture_unordered_signature(fx) for fx in f2[:half]}

    child_fixtures = [None] * n

    if sigs1_first == sigs2_first:
        # OX trên lượt đi (0..half-1)
        block1 = [fx.copy() for fx in f1[c1:c2 + 1]]
        child_fixtures[c1:c2 + 1] = block1
        used1 = {_fixture_unordered_signature(fx) for fx in block1}
        rem1 = [fx.copy() for fx in f2[:half] if _fixture_unordered_signature(fx) not in used1]
        idx = 0
        for fx in rem1:
            while idx < half and child_fixtures[idx] is not None:
                idx += 1
            if idx < half:
                child_fixtures[idx] = fx

        # OX tương ứng trên lượt về (half..n-1)
        d1, d2 = half + c1, half + c2
        block2 = [fx.copy() for fx in f1[d1:d2 + 1]]
        child_fixtures[d1:d2 + 1] = block2
        used2 = {_fixture_unordered_signature(fx) for fx in block2}
        rem2 = [fx.copy() for fx in f2[half:] if _fixture_unordered_signature(fx) not in used2]
        idx = half
        for fx in rem2:
            while idx < n and child_fixtures[idx] is not None:
                idx += 1
            if idx < n:
                child_fixtures[idx] = fx

        # Đồng bộ lại chiều H/A giữa lượt đi và lượt về theo p2 cho một nửa số cặp đấu
        _apply_ha_polarity_from_parent(child_fixtures, p2.schedule)
    else:
        # Khác bảng Berger: lấy cấu trúc 1-factor từ p1, lai ghép hoán vị vị trí vòng và thừa hưởng H/A polarity từ p2
        child_fixtures = [fx.copy() for fx in f1]
        # Hoán đổi một đoạn ngắn vòng ở lượt đi và đồng bộ ở lượt về để không phá vỡ khoảng cách lượt đi - lượt về
        swap_a, swap_b = random.sample(range(half), 2)
        child_fixtures[swap_a], child_fixtures[swap_b] = child_fixtures[swap_b], child_fixtures[swap_a]
        child_fixtures[half + swap_a], child_fixtures[half + swap_b] = (
            child_fixtures[half + swap_b],
            child_fixtures[half + swap_a]
        )
        _apply_ha_polarity_from_parent(child_fixtures, p2.schedule)

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
