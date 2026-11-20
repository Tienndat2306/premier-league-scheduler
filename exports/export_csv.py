import csv
import io
from .export_excel import _normalize_matches


def export_to_csv(schedule, filename="epl_schedule.csv"):
    """Xuất lịch thi đấu ra file CSV trên ổ đĩa"""
    rows = _normalize_matches(schedule)
    if not rows:
        return filename

    fieldnames = list(rows[0].keys())
    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return filename


def export_to_csv_string(schedule) -> str:
    """Xuất lịch thi đấu ra chuỗi CSV"""
    rows = _normalize_matches(schedule)
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()
