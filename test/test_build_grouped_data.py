"""Standalone check for generate.build_grouped_data unit-group splitting. Run: python test_build_grouped_data.py"""
import generate


def _act(name, km=5.0):
    fname, lname = name.split(" ", 1)
    return {"athlete": {"firstname": fname, "lastname": lname}, "distance": km * 1000,
            "moving_time": 1800, "elapsed_time": 1800, "total_elevation_gain": 0, "type": "Run"}


def demo():
    uc_map = {
        "SAR FORTY": {"unit": "40SAR", "company": "Hercules"},
        "SAR FORTYONE": {"unit": "41SAR", "company": "Glory"},
        "SAB EIGHT": {"unit": "8SAB", "company": "Comd Office"},
        "NOUNIT RUNNER": {"unit": "", "company": ""},
    }
    acts = [_act("SAR FORTY"), _act("SAR FORTYONE"), _act("SAB EIGHT"), _act("NOUNIT RUNNER")]
    members = [{"firstname": n.split()[0], "lastname": n.split()[1]} for n in uc_map]

    result = generate.build_grouped_data(acts, members, "test", name_map=None, uc_map=uc_map)

    assert {"all", "nsf", "nsmen"} <= result.keys()

    all_names = {r["name"] for r in result["all"]["leaderboard"]}
    assert all_names == set(uc_map.keys()), all_names

    nsf_names = {r["name"] for r in result["nsf"]["leaderboard"]}
    assert nsf_names == {"SAR FORTY"}, nsf_names

    nsmen_names = {r["name"] for r in result["nsmen"]["leaderboard"]}
    assert nsmen_names == {"SAR FORTYONE", "SAB EIGHT"}, nsmen_names

    # unlabelled runner appears only in 'all'
    assert "NOUNIT RUNNER" not in nsf_names and "NOUNIT RUNNER" not in nsmen_names

    print("OK: build_grouped_data splits units correctly")


if __name__ == "__main__":
    demo()
