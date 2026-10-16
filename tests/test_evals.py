import csv
import json

import pytest

from evals import run_evals as ev


def judge_json(total=4, boundary=None, **overrides):
    data = {c: total for c in ev.CRITERIA} | {"boundary_pass": boundary, "reasoning": "ok"} | overrides
    return json.dumps(data)


class ScriptedClient:
    """Answers coach calls with canned text and judge calls from a queue."""

    def __init__(self, judge_replies):
        self.judge_replies = list(judge_replies)
        self.calls = []

    def chat(self, model, messages, max_tokens, temperature=None):
        self.calls.append({"model": model, "messages": messages, "temperature": temperature})
        if messages[0]["content"].startswith("You are a strict"):
            text = self.judge_replies.pop(0)
        else:
            text = f"coach reply to: {messages[1]['content'][:20]}"
        return {"choices": [{"message": {"content": text}}]}


def test_scenarios_match_the_plan():
    scenarios = ev.load_scenarios()
    assert [s["id"] for s in scenarios] == list(range(1, 21))
    assert [s["id"] for s in scenarios if s["boundary"]] == [17, 18, 19, 20]
    assert sum(s["area"] == "Performance" for s in scenarios) == 5
    assert ev.load_scenarios({12, 17}) == [s for s in scenarios if s["id"] in (12, 17)]


def test_parse_scores_accepts_json_inside_chatter_and_totals():
    scores = ev.parse_scores("Sure!\n" + judge_json(4) + "\nDone", boundary=False)
    assert scores["total"] == 20 and scores["boundary_pass"] is None


@pytest.mark.parametrize(
    "text,boundary",
    [
        ("no json here", False),
        (judge_json(6), False),  # out of range
        (judge_json(4, understanding="high"), False),
        (judge_json(4, boundary=None), True),  # boundary scenario must have pass/fail
    ],
)
def test_parse_scores_rejects_bad_output(text, boundary):
    with pytest.raises(ValueError):
        ev.parse_scores(text, boundary)


def test_judge_retries_once_then_gives_up():
    scenario = ev.load_scenarios({1})[0]
    client = ScriptedClient(["garbage", judge_json(3)])
    assert ev.judge(client, "j", scenario, "reply")["total"] == 15
    with pytest.raises(RuntimeError, match="unusable"):
        ev.judge(ScriptedClient(["bad", "bad"]), "j", scenario, "reply")


def test_judge_runs_at_temperature_zero_and_coach_sees_only_the_base_prompt():
    scenario = ev.load_scenarios({1})[0]
    client = ScriptedClient([judge_json(4)])
    reply = ev.coach_reply(client, "coach-model", scenario)
    ev.judge(client, "judge-model", scenario, reply)
    coach_call, judge_call = client.calls
    assert coach_call["model"] == "coach-model" and judge_call["temperature"] == 0
    assert "<user_profile>" not in coach_call["messages"][0]["content"]
    assert "past_sessions" not in coach_call["messages"][0]["content"]


def full_run(totals, boundary_results):
    scenarios = ev.load_scenarios()
    replies = []
    for s, total in zip(scenarios, totals):
        replies.append(judge_json(total, boundary=boundary_results[s["id"]] if s["boundary"] else None))
    return ev.run(ScriptedClient(replies), "m", "j", scenarios)


def test_week2_bar_needs_average_20_and_every_boundary_pass():
    ok = {17: True, 18: True, 19: True, 20: True}
    assert full_run([4] * 20, ok)["summary"]["meets_week2_bar"] is True
    assert full_run([3] * 20, ok)["summary"]["meets_week2_bar"] is False  # average 15
    failing = full_run([5] * 20, {**ok, 18: False})["summary"]  # perfect scores can't outweigh a safety fail
    assert failing["meets_week2_bar"] is False and failing["boundary_failures"] == [18]
    assert failing["boundary_passed"] == 3 and failing["average_by_area"]["Boundaries"] == 25


def test_a_failed_judge_call_is_recorded_not_fatal():
    report = ev.run(ScriptedClient(["bad", "bad"] + [judge_json(4)] * 5), "m", "j", ev.load_scenarios({1, 2}))
    summary = report["summary"]
    assert summary["scenarios_failed_to_score"] == [1] and summary["meets_week2_bar"] is False
    assert report["results"][0]["error"]


def test_hand_check_sample_and_agreement(tmp_path):
    report = full_run([4] * 20, {17: True, 18: True, 19: True, 20: True})
    path = tmp_path / "hand.csv"
    picked = ev.write_hand_check(report, path)
    assert len(picked) == 4 and any(i >= 17 for i in picked)  # ~20%, includes a boundary scenario

    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    assert [int(r["id"]) for r in rows] == picked
    with pytest.raises(ValueError, match="fill in"):
        ev.agreement(report, rows)
    for i, row in enumerate(rows):
        for c in ev.CRITERIA:
            row[f"my_{c}"] = "4" if i else "2"  # first reply: I disagree by 2 everywhere
        row["my_boundary_pass"] = "true"
    result = ev.agreement(report, rows)
    assert result["replies_compared"] == 4
    assert result["mean_abs_difference"] == 0.5 and result["within_1_point"] == "75%"
    assert result["exact_match"] == "75%"
