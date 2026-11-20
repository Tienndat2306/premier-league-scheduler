import random
from datetime import datetime, time, timedelta


def mutate(chromosome, mutation_rate: float = 0.2, possible_dates=None, possible_times=None):
    """
    Đột biến trên Chromosome bảo toàn 100% tính hợp lệ của lịch thi đấu:
    1. Hoán đổi toàn bộ cặp đấu giữa 2 vòng trong cùng lượt đi hoặc lượt về (giữ nguyên mốc ngày của từng vòng).
    2. Đảo quyền chủ nhà / đội khách đối xứng giữa 1 trận lượt đi và trận lượt về tương ứng.
    3. Điều chỉnh khung giờ thi đấu trong vòng (ưu tiên giờ vàng cuối tuần cho trận Derby).
    """
    if random.random() > mutation_rate:
        return

    schedule = chromosome.schedule
    round_nums = sorted(schedule.fixtures.keys())
    num_rounds = len(round_nums)
    if num_rounds < 2:
        return

    half = num_rounds // 2

    # 1. Hoán đổi cặp đấu giữa 2 vòng (giữ nguyên date của từng vòng để không vi phạm ràng buộc ngày)
    if half >= 2 and random.random() < 0.7:
        if random.random() < 0.5:
            r1, r2 = random.sample(round_nums[:half], 2)
        else:
            r1, r2 = random.sample(round_nums[half:], 2)

        fx1 = schedule.fixtures[r1]
        fx2 = schedule.fixtures[r2]
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

    # 2. Đảo sân Nhà/Khách đối xứng giữa 1 cặp đấu ở lượt đi và trận lượt về tương ứng
    if half >= 1 and random.random() < 0.6:
        r_first = random.choice(round_nums[:half])
        fx_first = schedule.fixtures[r_first]
        if fx_first.matches:
            m1 = random.choice(fx_first.matches)
            h_team, a_team = m1.home_team, m1.away_team

            # Tìm trận lượt về tương ứng (a_team vs h_team)
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

    # 3. Đột biến khung giờ cho một trận ngẫu nhiên
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
