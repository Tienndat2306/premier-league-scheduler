import json
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DERBY_PATH = os.path.join(BASE_DIR, "data", "derbies.json")


def load_derbies(path=DEFAULT_DERBY_PATH):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {frozenset(pair) for pair in data if isinstance(pair, list) and len(pair) >= 2}
        except Exception:
            pass
    return {
        frozenset(["Manchester United", "Manchester City"]),
        frozenset(["Liverpool", "Everton"]),
        frozenset(["Arsenal", "Tottenham"]),
        frozenset(["Chelsea", "Tottenham"])
    }


DERBY_SET = load_derbies()


def is_derby_pair(home_team, away_team, custom_derbies=None) -> bool:
    """
    Kiểm tra 2 đội có phải trận Derby hay không.
    Hỗ trợ cả đối tượng Team lẫn tên/mã viết tắt dạng str.
    """
    h_name = getattr(home_team, "name", str(home_team))
    a_name = getattr(away_team, "name", str(away_team))
    h_short = getattr(home_team, "short", h_name[:3].upper())
    a_short = getattr(away_team, "short", a_name[:3].upper())

    if custom_derbies is not None:
        for pair in custom_derbies:
            if len(pair) >= 2:
                p_set = set(pair)
                if (h_name in p_set and a_name in p_set) or (h_short in p_set and a_short in p_set):
                    return True
        return False

    # Kiểm tra trong DERBY_SET
    if frozenset([h_name, a_name]) in DERBY_SET or frozenset([h_short, a_short]) in DERBY_SET:
        return True

    # Nếu không truyền custom_derbies, kiểm tra thêm cùng thành phố
    h_stadium = getattr(home_team, "stadium", None)
    a_stadium = getattr(away_team, "stadium", None)
    if h_stadium and a_stadium and getattr(h_stadium, "city", None) and h_stadium.city == a_stadium.city:
        return True

    return False
