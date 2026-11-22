import json

from zelda_env import segments


def decision(node, choice, origin="laya", reached=(), outcome="nothing new"):
    return {"decision": 1, "node": node, "choice": choice, "origin": origin, "reached": list(reached),
            "outcome": outcome, "survey_s": 2.0}


def test_metrics_report_loop_events_and_the_longest_repetitive_stretch(tmp_path):
    back_and_forth = [decision("a@0", "exit:b"), decision("b@0", "exit:a")] * 5
    varied = [decision(f"r{index}@0", "exit:next") for index in range(6)]
    records = [*varied, *back_and_forth, {"event": "loop_cut"}, decision("c@0", "talk", reached=["espada"])]
    trace = tmp_path / "trace.jsonl"
    trace.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
    result = segments.metrics(trace)
    assert result["decisions"] == 17
    assert result["reached"] == ["espada"]
    assert result["loop_cuts"] == 1 and result["impasses"] == 0
    # Ten moves back and forth, plus one different move on each side.
    assert result["longest_repeat"] == 12
    assert result["most_repeated"][0][2] == 5


def test_capture_copies_only_complete_checkpoints_and_keeps_existing_ones(tmp_path):
    session, store = tmp_path / "session", tmp_path / "segments"
    session.mkdir()
    (session / "objetivo-espada.state").write_bytes(b"state")
    (session / "objetivo-espada.memory.json").write_text("{}")
    (session / "objetivo-maku-tree.state").write_bytes(b"state without memory")
    assert segments.capture(store, session) == ["espada"]
    (session / "objetivo-espada.state").write_bytes(b"newer")
    assert segments.capture(store, session) == []
    assert (store / "espada.state").read_bytes() == b"state"
    assert segments.capture(store, session, replace=True) == ["espada"]
    assert (store / "espada.state").read_bytes() == b"newer"
