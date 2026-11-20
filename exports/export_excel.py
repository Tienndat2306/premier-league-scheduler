import io
import pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment


def _normalize_matches(schedule):
    """Chuyển đổi cả đối tượng OOP `Schedule` lẫn `List[dict]` thành danh sách dòng chuẩn"""
    if schedule is None:
        raise ValueError("No schedule to export")

    rows = []
    if hasattr(schedule, "all_matches"):
        for m in schedule.all_matches():
            rows.append({
                "Round": m.round_num,
                "Date": m.date_str,
                "Time": m.time_str,
                "Day": m.day_name,
                "Home Team": m.home_team.name if hasattr(m.home_team, "name") else str(m.home_team),
                "Away Team": m.away_team.name if hasattr(m.away_team, "name") else str(m.away_team),
                "Venue": m.venue,
                "City": getattr(m, "city", ""),
                "Derby": "Yes" if m.is_derby() else "No",
                "Prime Time": "Yes" if m.is_prime_time else "No",
                "Weekend": "Yes" if m.is_weekend else "No"
            })
    elif isinstance(schedule, list):
        for m in schedule:
            rows.append({
                "Round": m.get("round"),
                "Date": m.get("date"),
                "Time": m.get("time", "15:00"),
                "Day": m.get("day", ""),
                "Home Team": m.get("home"),
                "Away Team": m.get("away"),
                "Venue": m.get("venue"),
                "City": m.get("city", ""),
                "Derby": "Yes" if m.get("is_derby") else "No",
                "Prime Time": "Yes" if m.get("is_prime_time") else "No",
                "Weekend": "Yes" if m.get("is_weekend") else "No"
            })
    else:
        raise TypeError("Unsupported schedule type for Excel export")

    return rows


def _build_club_summary_rows(match_rows):
    """Tổng hợp bảng thống kê cân bằng Sân nhà / Sân khách / Derby / Giờ vàng cho từng CLB (Sheet 2)"""
    stats = {}
    for row in sorted(match_rows, key=lambda r: (r.get("Round") or 0, r.get("Date") or "")):
        home = row.get("Home Team")
        away = row.get("Away Team")
        is_derby = row.get("Derby") == "Yes"
        is_prime = row.get("Prime Time") == "Yes"
        is_wknd = row.get("Weekend") == "Yes"

        for club, is_home in ((home, True), (away, False)):
            if not club:
                continue
            if club not in stats:
                stats[club] = {
                    "Club": club,
                    "Home Stadium": row.get("Venue", "") if is_home else "",
                    "City": row.get("City", "") if is_home else "",
                    "Home Matches": 0,
                    "Away Matches": 0,
                    "Total Matches": 0,
                    "H/A Diff": 0,
                    "Derby Matches": 0,
                    "Prime Time Matches": 0,
                    "Weekend Matches": 0,
                    "_cur_h": 0,
                    "_cur_a": 0,
                    "Max Home Streak": 0,
                    "Max Away Streak": 0
                }
            s = stats[club]
            if is_home:
                if not s["Home Stadium"] and row.get("Venue"):
                    s["Home Stadium"] = row.get("Venue")
                if not s["City"] and row.get("City"):
                    s["City"] = row.get("City")
                s["Home Matches"] += 1
                s["_cur_h"] += 1
                s["_cur_a"] = 0
                s["Max Home Streak"] = max(s["Max Home Streak"], s["_cur_h"])
            else:
                s["Away Matches"] += 1
                s["_cur_a"] += 1
                s["_cur_h"] = 0
                s["Max Away Streak"] = max(s["Max Away Streak"], s["_cur_a"])

            s["Total Matches"] += 1
            if is_derby:
                s["Derby Matches"] += 1
            if is_prime:
                s["Prime Time Matches"] += 1
            if is_wknd:
                s["Weekend Matches"] += 1

    summary_rows = []
    for club in sorted(stats.keys()):
        s = stats[club]
        s["H/A Diff"] = abs(s["Home Matches"] - s["Away Matches"])
        s.pop("_cur_h", None)
        s.pop("_cur_a", None)
        summary_rows.append(s)
    return summary_rows


def _style_workbook(writer):
    """Định dạng tiêu đề màu tím đặc trưng EPL và tự động căn chỉnh độ rộng các cột"""
    header_fill = PatternFill(start_color="37003C", end_color="37003C", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)

    for sheet_name, ws in writer.sheets.items():
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for col in ws.columns:
            max_len = 0
            col_letter = col[0].column_letter
            for cell in col:
                val_str = str(cell.value or "")
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 38))


def export_to_excel(schedule, filename="epl_schedule.xlsx"):
    """Xuất lịch thi đấu ra file Excel gồm 2 sheets trên ổ đĩa"""
    rows = _normalize_matches(schedule)
    summary_rows = _build_club_summary_rows(rows)
    df_matches = pd.DataFrame(rows)
    df_summary = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(filename, engine="openpyxl") as writer:
        df_matches.to_excel(writer, index=False, sheet_name="EPL Schedule")
        df_summary.to_excel(writer, index=False, sheet_name="Club Summary & Balance")
        _style_workbook(writer)
    return filename


def export_to_excel_bytes(schedule) -> io.BytesIO:
    """Xuất lịch thi đấu ra bộ nhớ đệm BytesIO (2 sheets định dạng đẹp) để trả trực tiếp qua HTTP download"""
    rows = _normalize_matches(schedule)
    summary_rows = _build_club_summary_rows(rows)
    df_matches = pd.DataFrame(rows)
    df_summary = pd.DataFrame(summary_rows)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_matches.to_excel(writer, index=False, sheet_name="EPL Schedule")
        df_summary.to_excel(writer, index=False, sheet_name="Club Summary & Balance")
        _style_workbook(writer)
    output.seek(0)
    return output
