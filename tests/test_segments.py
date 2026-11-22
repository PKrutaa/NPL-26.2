import json

from zelda_env import segments


def decision(node, choice, origin="laya", reached=(), outcome="nothing new"):
    return {"decision": 1, "node": node, "choice": choice, "origin": origin, "reached": list(reached),
            "outcome": outcome, "survey_s": 2.0, "after_room": node.split("@")[0]}


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


def test_a_test_passes_only_with_the_target_reached_and_no_loop_signal():
    clean = {"reached": ["espada"], "rooms": ["00:59"], "loop_cuts": 0, "impasses": 0, "dropped": 0}
    assert segments.verdict(clean, until="espada") == "passou"
    assert segments.verdict(clean, until_room="00:59") == "passou"
    assert segments.verdict(clean, until="pa") == "não concluiu"
    assert segments.verdict({**clean, "loop_cuts": 1}, until="espada") == "concluiu com ciclo"
    assert segments.verdict({**clean, "impasses": 1}, until_room="00:59") == "concluiu com ciclo"
    dropped = {**clean, "dropped": 1}
    assert segments.verdict(dropped, until="espada") == "passou"
    assert segments.verdict(dropped, until="espada", no_drops=True) == "concluiu com ciclo"


def test_a_case_keeps_its_start_point_and_target(tmp_path):
    from types import SimpleNamespace

    state = tmp_path / "falha-40.state"
    state.write_bytes(b"state")
    (tmp_path / "falha-40.memory.json").write_text("{}")
    args = SimpleNamespace(name="ciclo", state=state, memory=None, until=None, until_room="00:7b",
                           decisions=30, note="ida e volta em 00:7a", no_drops=False)
    segments.add_case(tmp_path / "store", args)
    cases = segments.load_cases(tmp_path / "store")
    assert cases == {"ciclo": {"until": None, "until_room": "00:7b", "decisions": 30,
                               "note": "ida e volta em 00:7a", "memory": True, "no_drops": False}}
    assert (tmp_path / "store" / "cases" / "ciclo" / "start.memory.json").is_file()


def test_report_shows_the_latest_result_next_to_the_previous_one(tmp_path):
    lines = [{"test": "pa", "status": "não concluiu", "decisions": 200, "loop_cuts": 2},
             {"test": "pa", "status": "passou", "decisions": 79, "loop_cuts": 0, "longest_repeat": 6,
              "seconds": 600, "commit": "abc1234"}]
    (tmp_path / "results.jsonl").write_text("\n".join(json.dumps(line) for line in lines))
    table = segments.report(tmp_path).splitlines()
    assert table[1].split() == ["pa", "passou", "79", "200", "0", "6", "600", "abc1234"]
