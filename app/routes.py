from flask import Blueprint, render_template, request, jsonify, send_file
import traceback
import copy
import json
import os

from app.services.scheduler_service import (
    load_project_metadata,
    generate_schedule_by_algorithm,
    DATA_DIR
)
from exports.export_excel import export_to_excel_bytes
from utils.validation import validate_schedule
from constraints.soft import evaluate_soft_details, CITY_CLASH_PAIRS

main_bp = Blueprint("main", __name__)

premier_league_clubs, team_metadata, initial_derbies = load_project_metadata()

default_constraints = {
    "derby_matches": initial_derbies,
    "stadium_availability": {},
    "team_requests": {},
    "tv_broadcast": {
        "prime_time_matches": 38,
        "weekend_matches_min": 7
    },
    "ga_params": {
        "population_size": 40,
        "generations": 80,
        "mutation_rate": 0.25
    },
    "season_start": "2024-08-17",
    "team_metadata": team_metadata
}

current_constraints = copy.deepcopy(default_constraints)
latest_schedule_obj = None
latest_schedule = []
latest_algorithm = "hybrid"
latest_generation_response = None
LAST_SCHEDULE_FILE = os.path.join(DATA_DIR, "latest_schedule.json")


def _load_saved_schedule_from_disk():
    """Khôi phục lịch đã tạo gần nhất từ file data/latest_schedule.json (nếu có)"""
    global latest_schedule, latest_algorithm, latest_generation_response
    if os.path.exists(LAST_SCHEDULE_FILE):
        try:
            with open(LAST_SCHEDULE_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict) and saved.get("schedule"):
                    latest_schedule = saved["schedule"]
                    latest_algorithm = saved.get("algorithm_used", "hybrid")
                    latest_generation_response = saved
        except Exception:
            pass


def _save_latest_schedule_to_disk(payload: dict):
    """Lưu lịch vừa tạo xuống file data/latest_schedule.json để giữ trạng thái lâu dài"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LAST_SCHEDULE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


_load_saved_schedule_from_disk()


def ensure_latest_schedule():
    """Đảm bảo luôn có sẵn một lịch thi đấu hợp lệ khi người dùng mở trang /full_schedule hoặc xuất Excel"""
    global latest_schedule_obj, latest_schedule, latest_generation_response
    if not latest_schedule:
        latest_schedule_obj, latest_schedule = generate_schedule_by_algorithm(
            algorithm=latest_algorithm,
            clubs=premier_league_clubs,
            constraints=current_constraints
        )
        soft_details = evaluate_soft_details(latest_schedule_obj, custom_derbies=current_constraints.get("derby_matches"))
        latest_generation_response = {
            "schedule": latest_schedule,
            "total_matches": len(latest_schedule),
            "algorithm_used": latest_algorithm,
            "is_valid_hard_constraints": validate_schedule(latest_schedule_obj),
            "execution_time_ms": latest_schedule_obj.execution_time_ms,
            "fitness_history": latest_schedule_obj.fitness_history,
            "soft_details": soft_details,
            "ga_params_used": current_constraints.get("ga_params"),
            "season_start": current_constraints.get("season_start"),
            "metrics": {
                "derby_matches": sum(1 for m in latest_schedule if m.get("is_derby")),
                "weekend_matches": sum(1 for m in latest_schedule if m.get("is_weekend")),
                "prime_time_matches": sum(1 for m in latest_schedule if m.get("is_prime_time"))
            },
            "status": "success"
        }
    return latest_schedule


@main_bp.after_request
def add_no_cache_headers(response):
    """Đảm bảo trình duyệt không lấy bản cache cũ của trang chủ khi người dùng ấn nút Back"""
    if response.mimetype == "text/html":
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@main_bp.route("/")
def index():
    if not latest_generation_response and os.path.exists(LAST_SCHEDULE_FILE):
        _load_saved_schedule_from_disk()
    return render_template(
        "index.html",
        clubs=premier_league_clubs,
        team_metadata=team_metadata,
        constraints=current_constraints,
        latest_algorithm=latest_algorithm,
        saved_response=latest_generation_response
    )


@main_bp.route("/get_latest_schedule", methods=["GET"])
def get_latest_schedule():
    """Trả về lịch đã tạo gần nhất để trang chủ tự động hiển thị lại khi bấm Back"""
    if not latest_generation_response and os.path.exists(LAST_SCHEDULE_FILE):
        _load_saved_schedule_from_disk()
    if latest_generation_response and latest_generation_response.get("schedule"):
        return jsonify({
            "has_schedule": True,
            "data": latest_generation_response
        })
    return jsonify({"has_schedule": False})


@main_bp.route("/clear_schedule", methods=["POST"])
def clear_schedule():
    """Xóa lịch đã lưu hiện tại nếu người dùng muốn làm mới từ đầu"""
    global latest_schedule_obj, latest_schedule, latest_generation_response
    latest_schedule_obj = None
    latest_schedule = []
    latest_generation_response = None
    if os.path.exists(LAST_SCHEDULE_FILE):
        try:
            os.remove(LAST_SCHEDULE_FILE)
        except Exception:
            pass
    return jsonify({"status": "success", "message": "Saved schedule cleared"})


@main_bp.route("/constraints")
def constraints_page():
    stadium_list = [
        {"club": club, "stadium": team_metadata[club]["stadium"], "city": team_metadata[club]["city"]}
        for club in premier_league_clubs
    ]
    return render_template(
        "constraints.html",
        clubs=premier_league_clubs,
        team_metadata=team_metadata,
        stadium_list=stadium_list,
        constraints=current_constraints
    )


@main_bp.route("/save_constraints", methods=["POST"])
def save_constraints():
    global current_constraints
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No constraint data provided", "status": "error"}), 400

        derby_matches = data.get("derby_matches", default_constraints["derby_matches"])
        valid_derbies = []
        for pair in derby_matches:
            if isinstance(pair, list) and len(pair) >= 2 and pair[0] and pair[1] and pair[0] != pair[1]:
                valid_derbies.append([pair[0], pair[1]])

        stadium_avail = data.get("stadium_availability", {})
        tv_broadcast = data.get("tv_broadcast", default_constraints["tv_broadcast"])
        ga_params = data.get("ga_params", current_constraints.get("ga_params", default_constraints["ga_params"]))
        season_start = data.get("season_start", current_constraints.get("season_start", "2024-08-17"))

        current_constraints = {
            "derby_matches": valid_derbies,
            "stadium_availability": stadium_avail,
            "team_requests": data.get("team_requests", {}),
            "tv_broadcast": {
                "prime_time_matches": int(tv_broadcast.get("prime_time_matches", 38)),
                "weekend_matches_min": int(tv_broadcast.get("weekend_matches_min", 7))
            },
            "ga_params": {
                "population_size": max(4, int(ga_params.get("population_size", 40))),
                "generations": max(1, int(ga_params.get("generations", 80))),
                "mutation_rate": min(1.0, max(0.0, float(ga_params.get("mutation_rate", 0.25))))
            },
            "season_start": str(season_start),
            "team_metadata": team_metadata
        }

        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(os.path.join(DATA_DIR, "derbies.json"), "w", encoding="utf-8") as f:
                json.dump(valid_derbies, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "message": "Constraints & GA settings saved successfully",
            "constraints": current_constraints
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@main_bp.route("/auto_detect_city_derbies", methods=["POST"])
def auto_detect_city_derbies():
    """Tự động phát hiện các cặp đấu cùng thành phố (City Derbies) dựa trên dữ liệu stadiums.json"""
    city_groups = {}
    for club, meta in team_metadata.items():
        city = meta.get("city", "")
        if city:
            city_groups.setdefault(city, []).append(club)

    detected = [list(p) for p in current_constraints.get("derby_matches", [])]
    existing_sets = {frozenset(p) for p in detected if len(p) >= 2}

    added_count = 0
    for city, clubs_in_city in city_groups.items():
        if len(clubs_in_city) > 1:
            for i in range(len(clubs_in_city)):
                for j in range(i + 1, len(clubs_in_city)):
                    pair = [clubs_in_city[i], clubs_in_city[j]]
                    if frozenset(pair) not in existing_sets:
                        detected.append(pair)
                        existing_sets.add(frozenset(pair))
                        added_count += 1

    return jsonify({
        "status": "success",
        "derby_matches": detected,
        "added_count": added_count
    })


@main_bp.route("/reset_constraints", methods=["POST"])
def reset_constraints():
    global current_constraints
    current_constraints = copy.deepcopy(default_constraints)
    return jsonify({
        "status": "success",
        "message": "Constraints reset to default",
        "constraints": current_constraints
    })


@main_bp.route("/full_schedule")
@main_bp.route("/schedule")
def full_schedule_page():
    schedule = ensure_latest_schedule()
    soft_details = evaluate_soft_details(latest_schedule_obj, custom_derbies=current_constraints.get("derby_matches")) if latest_schedule_obj else {}
    return render_template(
        "schedule.html",
        clubs=premier_league_clubs,
        team_metadata=team_metadata,
        schedule=schedule,
        algorithm=latest_algorithm,
        execution_time_ms=getattr(latest_schedule_obj, "execution_time_ms", 0.0),
        fitness_history=getattr(latest_schedule_obj, "fitness_history", []),
        soft_details=soft_details
    )


@main_bp.route("/export_excel", methods=["GET"])
@main_bp.route("/export-excel", methods=["GET"])
def export_excel():
    """Xuất lịch thi đấu hiện tại ra file Excel (.xlsx) qua module exports/export_excel.py"""
    try:
        schedule = ensure_latest_schedule()
        output = export_to_excel_bytes(schedule)
        filename = f"epl_schedule_{latest_algorithm}.xlsx"
        return send_file(
            output,
            as_attachment=True,
            download_name=filename,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Excel export failed: {str(e)}"}), 500


@main_bp.route("/generate_schedule", methods=["POST"])
def generate_schedule_route():
    global latest_schedule_obj, latest_schedule, latest_algorithm, current_constraints, latest_generation_response
    try:
        data = request.get_json() or {}
        clubs = data.get("clubs", premier_league_clubs)
        algorithm = data.get("algorithm", "round_robin")

        runtime_constraints = copy.deepcopy(data.get("constraints") or current_constraints)
        runtime_constraints["team_metadata"] = team_metadata

        if "season_start" in data and data["season_start"]:
            runtime_constraints["season_start"] = str(data["season_start"])
            current_constraints["season_start"] = str(data["season_start"])

        if "ga_params" in data and isinstance(data["ga_params"], dict):
            gp = data["ga_params"]
            runtime_constraints["ga_params"] = {
                "population_size": max(4, int(gp.get("population_size", 40))),
                "generations": max(1, int(gp.get("generations", 80))),
                "mutation_rate": min(1.0, max(0.0, float(gp.get("mutation_rate", 0.25))))
            }
            current_constraints["ga_params"] = copy.deepcopy(runtime_constraints["ga_params"])

        if algorithm not in ("round_robin", "genetic", "csp", "hybrid"):
            return jsonify({
                "error": f'Algorithm "{algorithm}" not supported',
                "supported_algorithms": ["round_robin", "genetic", "csp", "hybrid"]
            }), 400

        schedule_obj, schedule = generate_schedule_by_algorithm(
            algorithm=algorithm,
            clubs=clubs,
            constraints=runtime_constraints
        )

        latest_schedule_obj = schedule_obj
        latest_schedule = schedule
        latest_algorithm = algorithm

        derby_count = sum(1 for match in schedule if match.get("is_derby", False))
        weekend_count = sum(1 for match in schedule if match.get("is_weekend", False))
        prime_count = sum(1 for match in schedule if match.get("is_prime_time", False))
        is_valid = validate_schedule(schedule_obj)
        soft_details = evaluate_soft_details(schedule_obj, custom_derbies=runtime_constraints.get("derby_matches"))

        response_payload = {
            "schedule": schedule,
            "total_matches": len(schedule),
            "algorithm_used": algorithm,
            "is_valid_hard_constraints": is_valid,
            "execution_time_ms": schedule_obj.execution_time_ms,
            "fitness_history": schedule_obj.fitness_history,
            "soft_details": soft_details,
            "ga_params_used": runtime_constraints.get("ga_params"),
            "season_start": runtime_constraints.get("season_start"),
            "metrics": {
                "derby_matches": derby_count,
                "weekend_matches": weekend_count,
                "prime_time_matches": prime_count
            },
            "status": "success"
        }

        latest_generation_response = response_payload
        _save_latest_schedule_to_disk(response_payload)

        return jsonify(response_payload)

    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "error": "Internal server error",
            "message": str(e),
            "type": type(e).__name__,
            "status": "error"
        }), 500


@main_bp.route("/compare_algorithms", methods=["POST"])
def compare_algorithms_route():
    """
    Chạy đối chuẩn (Benchmark) cả 4 thuật toán (round_robin, genetic, csp, hybrid)
    trên cùng cấu hình ràng buộc để so sánh trực tiếp hiệu năng, điểm phạt mềm và tính hợp lệ.
    """
    try:
        data = request.get_json() or {}
        clubs = data.get("clubs", premier_league_clubs)
        runtime_constraints = copy.deepcopy(data.get("constraints") or current_constraints)
        runtime_constraints["team_metadata"] = team_metadata

        if "season_start" in data and data["season_start"]:
            runtime_constraints["season_start"] = str(data["season_start"])

        if "ga_params" in data and isinstance(data["ga_params"], dict):
            gp = data["ga_params"]
            runtime_constraints["ga_params"] = {
                "population_size": max(4, int(gp.get("population_size", 20))),
                "generations": max(1, int(gp.get("generations", 30))),
                "mutation_rate": min(1.0, max(0.0, float(gp.get("mutation_rate", 0.25))))
            }

        alg_names = {
            "round_robin": "Round Robin (Berger Table)",
            "genetic": "Genetic Algorithm (GA)",
            "csp": "Constraint Satisfaction (CSP)",
            "hybrid": "Hybrid (RR + GA + CSP)"
        }

        comparison_results = []
        for alg in ("round_robin", "genetic", "csp", "hybrid"):
            sched_obj, match_dicts = generate_schedule_by_algorithm(
                algorithm=alg,
                clubs=clubs,
                constraints=runtime_constraints
            )
            is_valid = validate_schedule(sched_obj)
            soft_details = evaluate_soft_details(sched_obj, custom_derbies=runtime_constraints.get("derby_matches"))

            comparison_results.append({
                "algorithm": alg,
                "label": alg_names[alg],
                "total_matches": len(match_dicts),
                "is_valid_hard": is_valid,
                "execution_time_ms": sched_obj.execution_time_ms,
                "total_penalty": soft_details["total_penalty"],
                "streak_penalty": soft_details["streak_penalty"],
                "streak_breaks_count": soft_details["streak_breaks_count"],
                "repeat_separation_penalty": soft_details["repeat_separation_penalty"],
                "min_leg_gap": soft_details["min_leg_gap"],
                "city_clash_count": soft_details["city_clash_count"],
                "derby_matches": sum(1 for m in match_dicts if m.get("is_derby")),
                "weekend_matches": sum(1 for m in match_dicts if m.get("is_weekend")),
                "prime_time_matches": sum(1 for m in match_dicts if m.get("is_prime_time"))
            })

        return jsonify({
            "status": "success",
            "results": comparison_results
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500


@main_bp.route("/analyze_schedule", methods=["POST"])
def analyze_schedule():
    try:
        data = request.get_json() or {}
        schedule = data.get("schedule", [])

        if not schedule:
            return jsonify({"error": "No schedule provided"}), 400

        analysis = {
            "matches_per_round": {},
            "home_away_balance": {},
            "team_sequences": {},
            "max_streaks": {},
            "derby_matches": 0,
            "weekend_matches": 0,
            "prime_time_matches": 0,
            "city_clashes": 0,
            "min_leg_gap": 38,
            "streak_breaks_over_2": 0
        }

        home_counts = {}
        away_counts = {}
        derby_counts = {}
        prime_counts = {}
        team_sequences = {}
        first_meeting_round = {}

        sorted_schedule = sorted(schedule, key=lambda x: (x.get("round", 0), x.get("date", ""), x.get("time", "")))
        cur_home_streak = {}
        cur_away_streak = {}
        max_home_streak = {}
        max_away_streak = {}
        home_teams_by_date = {}

        for match in sorted_schedule:
            round_num = match.get("round", 0)
            analysis["matches_per_round"][round_num] = analysis["matches_per_round"].get(round_num, 0) + 1

            home = match.get("home")
            away = match.get("away")
            d_str = match.get("date", "")
            is_derby = bool(match.get("is_derby", False))
            is_prime = bool(match.get("is_prime_time", False))

            if d_str and home:
                home_teams_by_date.setdefault(d_str, set()).add(home)

            if home and away:
                pair_key = frozenset([home, away])
                if pair_key in first_meeting_round:
                    gap = abs(round_num - first_meeting_round[pair_key])
                    if gap < analysis["min_leg_gap"]:
                        analysis["min_leg_gap"] = gap
                else:
                    first_meeting_round[pair_key] = round_num

            if is_derby:
                analysis["derby_matches"] += 1
                if home:
                    derby_counts[home] = derby_counts.get(home, 0) + 1
                if away:
                    derby_counts[away] = derby_counts.get(away, 0) + 1

            if match.get("is_weekend", False):
                analysis["weekend_matches"] += 1

            if is_prime:
                analysis["prime_time_matches"] += 1
                if home:
                    prime_counts[home] = prime_counts.get(home, 0) + 1
                if away:
                    prime_counts[away] = prime_counts.get(away, 0) + 1

            if home:
                home_counts[home] = home_counts.get(home, 0) + 1
                cur_home_streak[home] = cur_home_streak.get(home, 0) + 1
                cur_away_streak[home] = 0
                if cur_home_streak[home] > 2:
                    analysis["streak_breaks_over_2"] += 1
                max_home_streak[home] = max(max_home_streak.get(home, 0), cur_home_streak[home])
                team_sequences.setdefault(home, []).append({
                    "round": round_num,
                    "type": "H",
                    "opponent": away,
                    "opponent_short": team_metadata.get(away, {}).get("short", (away or "")[:3].upper()),
                    "date": d_str,
                    "time": match.get("time", "15:00"),
                    "is_derby": is_derby,
                    "is_prime": is_prime,
                    "streak": cur_home_streak[home]
                })

            if away:
                away_counts[away] = away_counts.get(away, 0) + 1
                cur_away_streak[away] = cur_away_streak.get(away, 0) + 1
                cur_home_streak[away] = 0
                if cur_away_streak[away] > 2:
                    analysis["streak_breaks_over_2"] += 1
                max_away_streak[away] = max(max_away_streak.get(away, 0), cur_away_streak[away])
                team_sequences.setdefault(away, []).append({
                    "round": round_num,
                    "type": "A",
                    "opponent": home,
                    "opponent_short": team_metadata.get(home, {}).get("short", (home or "")[:3].upper()),
                    "date": d_str,
                    "time": match.get("time", "15:00"),
                    "is_derby": is_derby,
                    "is_prime": is_prime,
                    "streak": cur_away_streak[away]
                })

        for d_str, home_set in home_teams_by_date.items():
            for clash_pair in CITY_CLASH_PAIRS:
                if clash_pair.issubset(home_set):
                    analysis["city_clashes"] += 1

        all_teams = sorted(set(list(home_counts.keys()) + list(away_counts.keys())))
        for club in all_teams:
            h_cnt = home_counts.get(club, 0)
            a_cnt = away_counts.get(club, 0)
            meta = team_metadata.get(club, {})
            analysis["home_away_balance"][club] = {
                "home": h_cnt,
                "away": a_cnt,
                "total": h_cnt + a_cnt,
                "difference": abs(h_cnt - a_cnt),
                "max_home_streak": max_home_streak.get(club, 0),
                "max_away_streak": max_away_streak.get(club, 0),
                "derby": derby_counts.get(club, 0),
                "prime_time": prime_counts.get(club, 0),
                "stadium": meta.get("stadium", f"{club} Stadium"),
                "city": meta.get("city", ""),
                "short": meta.get("short", club[:3].upper())
            }
            analysis["team_sequences"][club] = sorted(team_sequences.get(club, []), key=lambda x: x["round"])

        return jsonify(analysis)

    except Exception as e:
        return jsonify({
            "error": str(e),
            "status": "error"
        }), 500
