import yaml


def load_policy(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def classify_reward_status(personal_baseline, global_baseline, actual):
    if personal_baseline is None and global_baseline is None:
        return "not_eligible"

    improved = personal_baseline is not None and (personal_baseline - actual) > 0
    if improved:
        return "improved"

    maintained = global_baseline is not None and actual <= global_baseline
    if maintained:
        return "maintained"

    return "no_change"


if __name__ == "__main__":
    scenarios = [
        {
            "name": "사용자 A - 자료 부족 (첫 주, baseline 없음)",
            "personal_baseline": None, "global_baseline": None, "actual": 50,
            "expected": "not_eligible",
        },
        {
            "name": "사용자 B - 원래도 낮았고 그대로 유지",
            "personal_baseline": 30, "global_baseline": 80, "actual": 30,
            "expected": "maintained",
        },
        {
            "name": "사용자 C - Global보다 높지만 Personal 대비 크게 개선",
            "personal_baseline": 150, "global_baseline": 80, "actual": 90,
            "expected": "improved",
        },
        {
            "name": "사용자 D - 변화 없음 (Personal과 동일, Global보다도 높음)",
            "personal_baseline": 100, "global_baseline": 80, "actual": 100,
            "expected": "no_change",
        },
        {
            "name": "사용자 E - 악화 (Personal보다 더 나빠짐)",
            "personal_baseline": 80, "global_baseline": 80, "actual": 110,
            "expected": "no_change",
        },
    ]

    all_pass = True
    for s in scenarios:
        result = classify_reward_status(s["personal_baseline"], s["global_baseline"], s["actual"])
        ok = result == s["expected"]
        all_pass = all_pass and ok
        print(f"{s['name']}: 기대={s['expected']} 실제={result} -> {'PASS' if ok else 'FAIL'}")

    print()
    print("전체 결과:", "PASS" if all_pass else "FAIL")
