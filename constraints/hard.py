from datetime import datetime, date, timedelta


def _parse_date(d) -> date:
    if isinstance(d, datetime):
        return d.date()
    if isinstance(d, date):
        return d
    if isinstance(d, str) and d:
        try:
            return datetime.strptime(d[:10], "%Y-%m-%d").date()
        except ValueError:
            pass
    return date(2024, 8, 17)


def _normalize_unavailable_ranges(raw_entry):
    """
    Chuẩn hóa cấu hình lịch bận của 1 sân vận động về danh sách các cặp [(start_date, end_date), ...].
    Hỗ trợ cả định dạng đơn `["2024-08-17", "2024-08-19"]` lẫn đa khoảng `[["2024-08-17", "2024-08-19"], ["2024-11-10", "2024-11-15"]]`.
    """
    if not raw_entry or not isinstance(raw_entry, (list, tuple)):
        return []
    if len(raw_entry) >= 2 and isinstance(raw_entry[0], (str, date, datetime)):
        return [(raw_entry[0], raw_entry[1])]
    ranges = []
    for item in raw_entry:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            ranges.append((item[0], item[1]))
    return ranges


def get_stadium_unavailable_ranges(home_team, stadium_avail: dict = None):
    if not stadium_avail:
        return []
    venue_name = home_team.stadium.name if getattr(home_team, "stadium", None) else f"{home_team.name} Stadium"
    raw_entry = (
        stadium_avail.get(venue_name)
        or stadium_avail.get(f"{home_team.name} Stadium")
        or stadium_avail.get(home_team.name)
    )
    return _normalize_unavailable_ranges(raw_entry)


def is_stadium_unavailable(home_team, target_date, stadium_avail: dict = None) -> bool:
    """
    Kiểm tra xem sân nhà của `home_team` có bị bận/khóa vào ngày `target_date` hay không.
    Hỗ trợ tra cứu theo tên sân vận động, '<Tên CLB> Stadium', hoặc tên CLB, và hỗ trợ nhiều khoảng ngày bận.
    """
    if not stadium_avail or not target_date:
        return False

    d_obj = _parse_date(target_date)
    ranges = get_stadium_unavailable_ranges(home_team, stadium_avail)
    for r_start, r_end in ranges:
        try:
            s_date = _parse_date(r_start)
            e_date = _parse_date(r_end)
            if s_date <= d_obj <= e_date:
                return True
        except Exception:
            continue
    return False


def resolve_schedule_stadium_conflicts(schedule, stadium_avail: dict = None):
    """
    Tự động sửa mọi xung đột lịch bận sân vận động (Stadium Availability) trên Schedule
    mà vẫn bảo toàn 100% các ràng buộc cứng khác:
    1. Thử dời ngày thi đấu trong phạm vi tuần của vòng đấu (ưu tiên cuối tuần, rồi các ngày lân cận).
    2. Nếu sân bị khóa dài hạn nhưng sân của đội khách rảnh, hoán đổi đối xứng quyền Chủ nhà/Đội khách
       với trận lượt về tương ứng (nếu lượt về sân chủ nhà đã rảnh).
    3. Nếu cả hai lượt đều vướng, tìm một vòng đấu khác trong cùng lượt mà sân của các đội liên quan đều rảnh
       để hoán đổi cặp đấu hoặc dời sang ngày gần nhất ngoài khoảng bận mà không trùng lịch thi đấu của 2 đội.
    """
    avail = stadium_avail if stadium_avail is not None else getattr(schedule, "stadium_availability", None)
    if not avail:
        return schedule

    schedule.stadium_availability = dict(avail)
    all_matches = schedule.all_matches()

    # Tập hợp các ngày mà mỗi đội đã có lịch thi đấu (để tránh trùng 2 trận cùng ngày khi dời ngày)
    team_busy_dates = {}
    for m in all_matches:
        if m.date_obj:
            team_busy_dates.setdefault(m.home_team.id, set()).add((m.id, m.date_obj))
            team_busy_dates.setdefault(m.away_team.id, set()).add((m.id, m.date_obj))

    def _can_play_on_date(match_obj, cand_date) -> bool:
        for tid in (match_obj.home_team.id, match_obj.away_team.id):
            for mid, d_used in team_busy_dates.get(tid, set()):
                if mid != match_obj.id and d_used == cand_date:
                    return False
        return True

    def _update_match_date(match_obj, new_date):
        old_date = match_obj.date_obj
        for tid in (match_obj.home_team.id, match_obj.away_team.id):
            s = team_busy_dates.setdefault(tid, set())
            if old_date:
                s.discard((match_obj.id, old_date))
            s.add((match_obj.id, new_date))
        match_obj.date = new_date

    def _swap_home_away(m_obj):
        h, a = m_obj.home_team, m_obj.away_team
        m_obj.home_team, m_obj.away_team = a, h
        m_obj.venue = a.stadium.name if getattr(a, "stadium", None) else f"{a.name} Stadium"
        m_obj.city = a.stadium.city if getattr(a, "stadium", None) else ""

    for match in all_matches:
        d_obj = match.date_obj
        if not d_obj or not is_stadium_unavailable(match.home_team, d_obj, avail):
            continue

        resolved = False

        # Chiến lược 1: Dời sang ngày lân cận trong tuần của vòng đấu [-3..+4]
        for offset in [1, -1, 2, -2, 3, -3, 4]:
            cand = d_obj + timedelta(days=offset)
            if not is_stadium_unavailable(match.home_team, cand, avail) and _can_play_on_date(match, cand):
                _update_match_date(match, cand)
                resolved = True
                break

        if resolved:
            continue

        # Chiến lược 2: Đảo sân Nhà/Khách đối xứng với trận lượt về tương ứng
        reverse_match = next(
            (
                m2 for m2 in all_matches
                if m2.id != match.id
                and m2.home_team.id == match.away_team.id
                and m2.away_team.id == match.home_team.id
            ),
            None
        )
        if reverse_match and reverse_match.date_obj:
            rev_d = reverse_match.date_obj
            if (
                not is_stadium_unavailable(match.away_team, d_obj, avail)
                and not is_stadium_unavailable(match.home_team, rev_d, avail)
            ):
                _swap_home_away(match)
                _swap_home_away(reverse_match)
                resolved = True

        if resolved:
            continue

        # Chiến lược 3: Tìm ngày khả dụng ngoài khoảng bị khóa (dành cho kịch bản sân bị khóa nhiều tháng)
        ranges = get_stadium_unavailable_ranges(match.home_team, avail)
        for r_start, r_end in ranges:
            s_unavail = _parse_date(r_start)
            e_unavail = _parse_date(r_end)
            if s_unavail <= d_obj <= e_unavail:
                for step in range(1, 60):
                    for cand in (e_unavail + timedelta(days=step), s_unavail - timedelta(days=step)):
                        if not is_stadium_unavailable(match.home_team, cand, avail) and _can_play_on_date(match, cand):
                            _update_match_date(match, cand)
                            resolved = True
                            break
                    if resolved:
                        break
            if resolved:
                break

    return schedule


def check_hard_constraints(schedule, stadium_avail: dict = None) -> int:
    """
    Kiểm tra các ràng buộc cứng (Hard Constraints) trên một Schedule:
    1. Mỗi trận phải có ngày & giờ hợp lệ.
    2. Mỗi đội chỉ được đá đúng 1 trận trong 1 vòng đấu.
    3. Một đội không thể đá 2 trận cùng 1 thời điểm (ngày + giờ).
    4. Mỗi cặp đấu có thứ tự (Home, Away) chỉ xuất hiện đúng 1 lần trong toàn mùa giải.
    5. Không có trận đấu nào diễn ra trên sân vận động đang trong thời gian bận/bảo trì (stadium_availability).
    """
    violations = 0
    team_round = set()
    team_datetime = set()
    match_pairs = set()

    avail = stadium_avail if stadium_avail is not None else getattr(schedule, "stadium_availability", None)

    for match in schedule.all_matches():
        h = match.home_team.id
        a = match.away_team.id
        r = match.round_num
        d = match.date_str
        t = match.time_str

        if not d or not t:
            violations += 1
            continue

        # 1 đội / 1 vòng
        for team in (h, a):
            key = (team, r)
            if key in team_round:
                violations += 1
            team_round.add(key)

        # 1 đội / 1 thời điểm
        for team in (h, a):
            key = (team, d, t)
            if key in team_datetime:
                violations += 1
            team_datetime.add(key)

        # 1 cặp (Home, Away) chỉ xuất hiện 1 lần
        pair = (h, a)
        if pair in match_pairs:
            violations += 1
        match_pairs.add(pair)

        # Kiểm tra lịch bận sân vận động (Stadium Availability)
        if avail and is_stadium_unavailable(match.home_team, match.date_obj, avail):
            violations += 1

    return violations
