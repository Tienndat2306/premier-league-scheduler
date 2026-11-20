import random
from datetime import datetime, time, timedelta


def _swap_rounds_matches(fx1, fx2):
    dates1 = [m.date for m in fx1.matches]
    dates2 = [m.date for m in fx2.matches]

    for m1, m2 in zip(fx1.matches, fx2.matches):
        m1.home_team, m2.home_team = m2.home_team, m1.home_team
        m1.away_team, m2.away_team = m2.away_team, m1.away_team
        m1.venue, m2.venue = m2.venue, m1.venue
        m1.city, m2.city = m2.city, m1.city

    for idx, m in enumerate(fx1.matches):
        if idx < len(dates1):
            m.date = dates1[idx]
    for idx, m in enumerate(fx2.matches):
        if idx < len(dates2):
            m.date = dates2[idx]


def _swap_team_labels(schedule, team_a, team_b):
    """
    Toán tử TeamSwap (Isomorphic Relabeling):
    Hoán đổi vị trí lịch thi đấu của 2 đội `team_a` và `team_b` trên toàn mùa giải.
    Bảo toàn 100% cấu trúc HAP (không làm tăng streak breaks) nhưng giúp giảm xung đột thành phố (City Clash)
    và tối ưu vị trí các trận Derby / sân vận động bận.
    """
    id_a, id_b = team_a.id, team_b.id
    for fx in schedule.fixtures.values():
        for m in fx.matches:
            h_id, a_id = m.home_team.id, m.away_team.id
            changed = False
            if h_id == id_a:
                m.home_team = team_b
                changed = True
            elif h_id == id_b:
                m.home_team = team_a
                changed = True

            if a_id == id_a:
                m.away_team = team_b
                changed = True
            elif a_id == id_b:
                m.away_team = team_a
                changed = True

            if changed:
                ht = m.home_team
                m.venue = ht.stadium.name if getattr(ht, "stadium", None) else f"{ht.name} Stadium"
                m.city = ht.stadium.city if getattr(ht, "stadium", None) else ""


def mutate(chromosome, mutation_rate: float = 0.2, possible_dates=None, possible_times=None):
    """
    Đột biến đa toán tử trên Chromosome bảo toàn 100% tính hợp lệ của lịch thi đấu:
    1. Synchronized / Half-Season Round Swap: Hoán đổi cặp vòng (ưu tiên hoán đổi đồng bộ cả lượt đi & lượt về để giữ khoảng cách >= 8 vòng).
    2. TeamSwap (Isomorphic Team Relabeling): Hoán đổi vai trò của 2 CLB trong bảng HAP để tối ưu xung đột thành phố và Derby.
    3. Symmetric Home/Away Inversion: Đảo quyền chủ nhà / đội khách đối xứng giữa 1 trận lượt đi và trận lượt về tương ứng.
    4. Kickoff Slot & Weekend Derby Shift: Điều chỉnh khung giờ thi đấu trong vòng.
    """
    if random.random() > mutation_rate:
        return

    schedule = chromosome.schedule
    round_nums = sorted(schedule.fixtures.keys())
    num_rounds = len(round_nums)
    if num_rounds < 2:
        return

    half = num_rounds // 2

    # 1. Hoán đổi vòng đấu (ưu tiên hoán đổi đồng bộ ở cả lượt đi và lượt về để bảo toàn khoảng cách 2 lượt)
    if half >= 2 and random.random() < 0.65:
        idx1, idx2 = random.sample(range(half), 2)
        if random.random() < 0.7:
            # Đồng bộ cả lượt đi và lượt về
            _swap_rounds_matches(schedule.fixtures[round_nums[idx1]], schedule.fixtures[round_nums[idx2]])
            _swap_rounds_matches(schedule.fixtures[round_nums[half + idx1]], schedule.fixtures[round_nums[half + idx2]])
        else:
            # Chỉ hoán đổi 2 vòng lân cận trong cùng 1 lượt
            leg_offset = 0 if random.random() < 0.5 else half
            r1 = round_nums[leg_offset + idx1]
            r2 = round_nums[leg_offset + idx2]
            _swap_rounds_matches(schedule.fixtures[r1], schedule.fixtures[r2])

    # 2. TeamSwap: Hoán đổi vị trí lịch của 2 đội bất kỳ trong bảng Berger
    if random.random() < 0.45:
        first_fx = schedule.fixtures[round_nums[0]]
        all_teams = []
        for m in first_fx.matches:
            all_teams.append(m.home_team)
            all_teams.append(m.away_team)
        if len(all_teams) >= 2:
            t_a, t_b = random.sample(all_teams, 2)
            _swap_team_labels(schedule, t_a, t_b)

    # 3. Đảo sân Nhà/Khách đối xứng giữa 1 cặp đấu ở lượt đi và trận lượt về tương ứng
    if half >= 1 and random.random() < 0.5:
        r_first = random.choice(round_nums[:half])
        fx_first = schedule.fixtures[r_first]
        if fx_first.matches:
            m1 = random.choice(fx_first.matches)
            h_team, a_team = m1.home_team, m1.away_team

            found_second = None
            for r_sec in round_nums[half:]:
                for m2 in schedule.fixtures[r_sec].matches:
                    if m2.home_team == a_team and m2.away_team == h_team:
                        found_second = m2
                        break
                if found_second:
                    break

            if found_second:
                m1.home_team, m1.away_team = a_team, h_team
                m1.venue = a_team.stadium.name if a_team.stadium else f"{a_team.name} Stadium"
                m1.city = a_team.stadium.city if a_team.stadium else ""

                found_second.home_team, found_second.away_team = h_team, a_team
                found_second.venue = h_team.stadium.name if h_team.stadium else f"{h_team.name} Stadium"
                found_second.city = h_team.stadium.city if h_team.stadium else ""

    # 4. Đột biến khung giờ cho một trận ngẫu nhiên
    all_matches = schedule.all_matches()
    if all_matches and possible_times:
        target_match = random.choice(all_matches)
        if target_match.is_derby():
            derby_times = []
            for t in possible_times:
                parsed = t if isinstance(t, time) else datetime.strptime(str(t)[:5], "%H:%M").time()
                if parsed >= time(17, 30):
                    derby_times.append(parsed)
            target_match.time = random.choice(derby_times) if derby_times else random.choice(possible_times)
            target_match.is_prime_time = True
        else:
            target_match.time = random.choice(possible_times)
