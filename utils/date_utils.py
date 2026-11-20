import json
import os
from datetime import datetime, date, timedelta, time as dt_time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CALENDAR_PATH = os.path.join(BASE_DIR, "data", "calendar.json")


def parse_date(d) -> date:
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


def get_match_dates(season_start, total_rounds: int = 38):
    """Trả về danh sách ngày gốc (Thứ Bảy) của 38 vòng đấu"""
    start_dt = parse_date(season_start)
    # Đưa về Thứ Bảy gần nhất nếu ngày bắt đầu không phải Thứ Bảy
    if start_dt.weekday() != 5:
        days_to_sat = (5 - start_dt.weekday()) % 7
        start_dt = start_dt + timedelta(days=days_to_sat)

    dates = []
    current = start_dt
    for _ in range(total_rounds):
        dates.append(current)
        current += timedelta(days=7)
    return dates


def get_time_slots():
    """Trả về danh sách các khung giờ thi đấu dưới dạng datetime.time"""
    raw = ["12:30", "15:00", "17:30", "20:00"]
    if os.path.exists(CALENDAR_PATH):
        try:
            with open(CALENDAR_PATH, "r", encoding="utf-8") as f:
                cal = json.load(f)
                if cal.get("time_slots"):
                    raw = cal["time_slots"]
        except Exception:
            pass
    return [datetime.strptime(t, "%H:%M").time() for t in raw]


def get_season_end(season_start, total_rounds: int = 38) -> date:
    """Tính ngày kết thúc mùa giải = sau 38 vòng"""
    start_date = parse_date(season_start)
    return start_date + timedelta(days=(total_rounds - 1) * 7)


def assign_slot_for_match(base_saturday: date, match_index: int, total_in_round: int,
                          is_derby: bool, weekend_min: int = 7,
                          home_team_name: str = "", venue_name: str = "",
                          stadium_avail: dict = None):
    """Phân bổ ngày và khung giờ hợp lý cho một trận trong vòng"""
    stadium_avail = stadium_avail or {}
    weekend_slots = max(weekend_min, min(total_in_round, 8))

    if is_derby:
        offset = 1 if (match_index % 2 == 1) else 0
    elif match_index < weekend_slots:
        offset = 0 if match_index < (weekend_slots // 2 + 1) else 1
    else:
        offset = 2 if (match_index % 2 == 0) else -1

    candidate_date = base_saturday + timedelta(days=offset)

    # Kiểm tra lịch bận sân vận động (hỗ trợ cả 1 khoảng [start, end] hoặc nhiều khoảng [[s1, e1], [s2, e2]])
    raw_unavail = (
        stadium_avail.get(venue_name)
        or stadium_avail.get(f"{home_team_name} Stadium")
        or stadium_avail.get(home_team_name)
    )
    if raw_unavail and isinstance(raw_unavail, (list, tuple)):
        ranges = (
            [(raw_unavail[0], raw_unavail[1])]
            if len(raw_unavail) >= 2 and not isinstance(raw_unavail[0], (list, tuple))
            else [(r[0], r[1]) for r in raw_unavail if isinstance(r, (list, tuple)) and len(r) >= 2]
        )

        def _date_in_ranges(dt_val):
            for rs, re in ranges:
                try:
                    if parse_date(rs) <= dt_val <= parse_date(re):
                        return True
                except Exception:
                    pass
            return False

        if _date_in_ranges(candidate_date):
            for alt_offset in [0, 1, 2, -1, 3]:
                alt_date = base_saturday + timedelta(days=alt_offset)
                if not _date_in_ranges(alt_date):
                    candidate_date = alt_date
                    break

    wd = candidate_date.weekday()
    is_weekend = wd >= 5
    is_prime = is_weekend and (is_derby or match_index == 0)

    if is_prime or is_derby:
        t_str = "17:30" if wd == 6 else "20:00"
    elif wd == 5:
        slots = ["12:30", "15:00", "15:00", "15:00", "17:30"]
        t_str = slots[match_index % len(slots)]
    elif wd == 6:
        slots = ["14:00", "16:30"]
        t_str = slots[match_index % len(slots)]
    else:
        t_str = "20:00"

    t_obj = datetime.strptime(t_str, "%H:%M").time()
    return candidate_date, t_obj, is_prime
