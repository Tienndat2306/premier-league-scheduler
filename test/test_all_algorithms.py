from app.services.scheduler_service import generate_schedule_by_algorithm, load_project_metadata
from utils.validation import validate_schedule


def test_all_algorithms():
    clubs, team_metadata, derbies = load_project_metadata()
    constraints = {
        "season_start": "2024-08-17",
        "derby_matches": derbies,
        "stadium_availability": {
            "Emirates Stadium": [["2024-08-01", "2024-08-31"], ["2024-11-01", "2024-11-20"]],
            "Old Trafford": ["2024-08-23", "2024-08-26"]
        },
        "team_requests": {
            "Arsenal": {"1": "A"},
            "Liverpool": {"38": "H"}
        },
        "tv_broadcast": {
            "prime_time_matches": 38,
            "weekend_matches_min": 7
        },
        "ga_params": {
            "population_size": 10,
            "generations": 10,
            "mutation_rate": 0.25
        },
        "team_metadata": team_metadata
    }

    for alg in ("round_robin", "genetic", "csp", "hybrid", "sota_sa"):
        schedule_obj, match_dicts = generate_schedule_by_algorithm(
            algorithm=alg,
            clubs=clubs,
            constraints=constraints
        )
        assert len(match_dicts) == 380, f"{alg}: expected 380 matches"
        assert validate_schedule(schedule_obj), f"{alg}: hard constraints violated"
        print(
            f"Algorithm '{alg}' passed: 380 matches, 0 hard violations | "
            f"soft penalty = {schedule_obj.final_penalty} | time = {schedule_obj.execution_time_ms} ms"
        )

    # Kiểm tra xuất Excel 3 sheets
    from exports.export_excel import export_to_excel_bytes
    import openpyxl
    excel_bytes = export_to_excel_bytes(schedule_obj)
    wb = openpyxl.load_workbook(excel_bytes)
    assert "EPL Schedule" in wb.sheetnames and "Club Summary & Balance" in wb.sheetnames and "38-Round H-A Matrix" in wb.sheetnames
    print("Excel 3-sheet export test passed:", wb.sheetnames)


if __name__ == "__main__":
    test_all_algorithms()
