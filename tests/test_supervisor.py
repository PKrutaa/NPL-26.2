import json

import pytest

from zelda_env.supervisor import ABSTAIN, Supervisor, SupervisorUnavailable, build_prompt, parse

OPTIONS = [("o1", "Leave through the north edge"), ("o2", "Talk to the character")]
CONTEXT = {"goal": "Find Impa", "room": "00:8a", "items": None}


class Fake:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def complete(self, system, user, option_ids, timeout):
        self.calls += 1
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def consult(reply, **options):
    supervisor = Supervisor(Fake(reply), **options)
    return supervisor, *supervisor.consult(CONTEXT, OPTIONS, decision=10)


def test_valid_choice_is_accepted():
    supervisor, choice, record = consult(json.dumps({"option_id": "o2", "reason": "new"}))
    assert choice == "o2" and record["supervisor"] == "accepted" and supervisor.stats["accepted"] == 1


@pytest.mark.parametrize("reply, rejection", [
    (TimeoutError(), "timeout"),
    ("not json {", "invalid_json"),
    (json.dumps(["o1"]), "invalid_schema"),
    (json.dumps({"option_id": 3}), "invalid_schema"),
    (json.dumps({"option_id": "press_start_forever"}), "unknown_option"),
    (json.dumps({"option_id": ABSTAIN}), "abstain"),
    (SupervisorUnavailable("no weights"), "unavailable"),
])
def test_every_bad_outcome_returns_no_option(reply, rejection):
    supervisor, choice, record = consult(reply)
    assert choice is None
    assert record["supervisor"] == rejection
    assert supervisor.stats["rejected"] == {rejection: 1}


def test_budget_two_calls_per_impasse_and_six_decisions_apart():
    backend = Fake(json.dumps({"option_id": "o1"}))
    supervisor = Supervisor(backend)
    assert supervisor.consult(CONTEXT, OPTIONS, 10)[0] == "o1"
    assert supervisor.consult(CONTEXT, OPTIONS, 12)[1] == {"supervisor": "skipped_budget"}
    assert supervisor.consult(CONTEXT, OPTIONS, 16)[0] == "o1"
    assert supervisor.consult(CONTEXT, OPTIONS, 30)[1] == {"supervisor": "skipped_budget"}
    assert backend.calls == 2
    supervisor.progressed()
    assert supervisor.consult(CONTEXT, OPTIONS, 36)[0] == "o1"


def test_slow_answer_counts_as_timeout(monkeypatch):
    clock = iter([0.0, 25.0])
    monkeypatch.setattr("zelda_env.supervisor.time.perf_counter", lambda: next(clock))
    _, choice, record = consult(json.dumps({"option_id": "o1"}), timeout=20)
    assert choice is None and record["supervisor"] == "timeout"


def test_prompt_is_bounded_and_marks_unknown():
    prompt = build_prompt({**CONTEXT, "noise": "x" * 10_000}, OPTIONS)
    assert "items: unknown" in prompt and f"- {ABSTAIN}:" in prompt and "- o1:" in prompt
    assert len(prompt) < 2700


def test_parse_truncates_reason():
    choice, reason, rejection = parse(json.dumps({"option_id": "o1", "reason": "r" * 999}), ["o1"])
    assert choice == "o1" and len(reason) == 200 and rejection is None
