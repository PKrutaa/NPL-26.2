"""Decision rules of the agent, with fakes in place of the emulator and the models."""

from types import SimpleNamespace

from zelda_env.agent import Agent, Memory, node_of
from zelda_env.survey import Option

OBS = SimpleNamespace(room="A", x=10, y=20, facing="up")


def option(option_id, kind="interact", destination=None, steps=1):
    return Option(option_id, kind, option_id, (("up", 12),) * steps, destination)


class Laya:
    def __init__(self):
        self.asked = []

    def choose(self, context, criteria):
        self.asked.append(criteria)
        return sorted(criteria)[-1], {"answer": "fake"}


class Sup:
    def __init__(self, reply):
        self.reply, self.calls = reply, 0

    def consult(self, context, options, decision):
        self.calls += 1
        return self.reply, {"supervisor": "accepted" if self.reply else "abstain"}

    def progressed(self):
        pass


def agent(policy=None, supervisor=None, **options):
    made = Agent.__new__(Agent)
    made.policy, made.supervisor, made.memory = policy or Laya(), supervisor, Memory()
    made.pyboy = SimpleNamespace(memory={0xC6AA: 12, 0xC6AB: 12, 0xCC39: 0xFF})
    made.hops = 0
    made.stall, made.since_progress, made.decisions, made.recent = options.get("stall", 20), 0, 0, []
    return made


def test_laya_chooses_only_among_untried_options():
    made = agent()
    options = [option("talk:1"), option("talk:2"), option("exit:B", "exit", "B")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.memory.record(node, "talk:1")
    chosen, origin, _ = made.decide(OBS, node, options, "goal")
    assert origin == "laya" and chosen.id != "talk:1"
    assert set(made.policy.asked[0].values()) == {"talk:2", "exit:B"}


def test_single_untried_option_is_forced_without_asking_models():
    supervisor = Sup("talk:1")
    made = agent(supervisor=supervisor, stall=0)
    options = [option("talk:1")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    chosen, origin, _ = made.decide(OBS, node, options, "goal")
    assert (chosen.id, origin) == ("talk:1", "forced")
    assert supervisor.calls == 0 and made.policy.asked == []


def test_supervisor_is_not_called_while_the_game_progresses():
    supervisor = Sup("talk:1")
    made = agent(supervisor=supervisor)
    options = [option("talk:1"), option("talk:2")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    _, origin, _ = made.decide(OBS, node, options, "goal")
    assert origin == "laya" and supervisor.calls == 0


def test_supervisor_picks_at_impasse_and_rejection_falls_back():
    options = [option("talk:1", steps=3), option("talk:2")]
    node = node_of("A", options)
    for reply, expected in (("talk:1", ("talk:1", "supervisor")), (None, ("talk:2", "fallback"))):
        made = agent(supervisor=Sup(reply))
        made.memory.arrive(node, options)
        made.memory.record(node, "talk:1")
        made.memory.record(node, "talk:2")
        chosen, origin, _ = made.decide(OBS, node, options, "goal")
        assert (chosen.id, origin) == expected


def test_fallback_rotates_instead_of_repeating_one_option():
    made = agent()
    options = [option("talk:1"), option("talk:2"), option("talk:3")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    picks = []
    for _ in range(9):
        chosen, origin, _ = made.decide(OBS, node, options, "goal")
        made.memory.record(node, chosen.id)
        picks.append(chosen.id)
    assert sorted(picks[3:6]) == sorted(picks[6:9]) == ["talk:1", "talk:2", "talk:3"]


def test_dropped_option_is_never_chosen():
    made = agent()
    options = [option("talk:1"), option("talk:2")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.memory.banned.add((node, "talk:2"))
    for _ in range(4):
        chosen, _, _ = made.decide(OBS, node, options, "goal")
        made.memory.record(node, chosen.id)
        assert chosen.id == "talk:1"


def test_heading_gives_compass_words_between_overworld_screens():
    from zelda_env.agent import heading

    assert heading("00:8a", "00:39") == "north or west"
    assert heading("00:8a", "00:71") == "west or north"
    assert heading("00:68", "00:48") == "north"
    assert heading("00:38", "00:39") == "east"
    # No direction across maps (indoors, dungeons) or once the landmark is reached.
    assert heading("03:f8", "00:48") is None
    assert heading("00:48", "00:48") is None


def test_laya_reads_only_the_short_goal_and_short_options():
    made = agent()
    options = [Option("exit:B", "exit", "Leave through the north edge of this screen", (), "B", "Go north"),
               Option("talk:1", "interact", "Talk to the character to the east", (), None, "Talk to the character")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.decide(OBS, node, options, "Go north.")
    assert set(made.policy.asked[0].values()) == {"Go north to a new room", "Talk to the character"}
    # Once the room on the other side is known, the exit stops saying it is new.
    made.memory.arrive(node_of("B", []), [])
    made.decide(OBS, node, options, "Go north.")
    assert set(made.policy.asked[1].values()) == {"Go north", "Talk to the character"}


def test_goal_follows_the_steps_of_the_objective():
    made = agent()
    made.pyboy = SimpleNamespace(memory={address: 0 for address in range(0xC600, 0xCA00)})
    made.pyboy.memory[0xC6D0 + 1] = 0x04  # sword received: global flag 0x0a
    assert made.objective("00:39") == ("maku-tree", "Go south or west.")
    assert made.objective("00:59") == ("maku-tree", "Go south or west.")
    assert made.objective("00:68") == ("maku-tree", "Go north.")  # waypoint passed on arrival
    assert made.objective("00:48") == ("maku-tree", "Enter the door or stairs.")
    assert made.objective("04:04") == ("maku-tree", "Go north.")  # inside the Maku Path
    assert made.objective("00:38") == ("maku-tree", "Talk to the character.")


def test_goal_names_one_direction_that_has_an_exit():
    made = agent()
    options = [Option("exit:B", "exit", "west", (), "B", "Go west"),
               Option("exit:C", "exit", "south", (), "C", "Go south")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    captured = []
    made.policy.choose = lambda context, criteria: (captured.append(context["goal"]) or sorted(criteria)[0], {})
    made.decide(OBS, node, options, "Go north or west.")
    made.decide(OBS, node, options, "Go north or east.")
    # With no exit in either direction, the way there goes around: the goal is to explore.
    assert captured == ["Go west.", "Go to a new room."]


def test_endless_trips_to_a_pending_area_are_cut_off():
    made = agent()
    here, there = [option("exit:B", "exit", "B")], [option("exit:A", "exit", "A"), option("talk:1")]
    node, far = node_of("A", here), node_of("B", there)
    made.memory.arrive(node, here)
    made.memory.record(node, "exit:B")
    made.memory.edges[node] = {"exit:B": far}
    made.memory.current["pending"][far] = ["talk:1"]  # never clears: the record is wrong
    origins = []
    for _ in range(20):
        chosen, origin, _ = made.decide(OBS, node, here, "goal")
        made.memory.record(node, chosen.id)
        origins.append(origin)
    assert origins[:14] == ["frontier"] * 14 and set(origins[14:]) == {"fallback"}


def test_a_known_exit_toward_the_goal_is_offered_again_a_limited_number_of_times():
    made = agent()
    options = [Option("exit:01:76", "exit", "door", (), "01:76", "Go outside"), option("talk:1"), option("talk:2")]
    node = node_of("04:e7", options)
    made.memory.arrive(node, options)
    made.memory.record(node, "exit:01:76")  # Link came in through it, so it is not new
    made.memory.arrive(node_of("01:76", []), [])
    offered = []
    made.policy.choose = lambda context, criteria: (
        offered.append(set(criteria.values())) or next(k for k, v in criteria.items() if v == "Go outside"), {})
    for _ in range(2):
        chosen, origin, _ = made.decide(OBS, node, options, "Go outside.")
        assert (chosen.id, origin) == ("exit:01:76", "laya")
    made.policy.choose = lambda context, criteria: (offered.append(set(criteria.values())) or sorted(criteria)[0], {})
    made.decide(OBS, node, options, "Go outside.")
    assert "Go outside" in offered[0] and "Go outside" in offered[1] and "Go outside" not in offered[2]


def test_the_dungeon_of_the_objective_is_entered_at_once_and_not_left():
    made = agent()
    made.focus = 0x0D
    made.memory.dungeons["04:0d"] = 0x0D
    outside = [Option("exit:04:0d", "exit", "door", (), "04:0d", "Enter the door or stairs"), option("talk:1")]
    node = node_of("01:48", outside)
    made.memory.arrive(node, outside)
    made.memory.record(node, "exit:04:0d")
    assert made.decide(OBS, node, outside, "Go to a new room.")[:2] == (outside[0], "route")
    made.pyboy.memory[0xCC39] = 0x0D
    made.memory.dungeons["01:48"] = 0xFF  # the overworld room Link came in from
    inside = [Option("exit:01:48", "exit", "door", (), "01:48", "Go outside"), option("push:1")]
    node = node_of("04:0d", inside)
    made.memory.arrive(node, inside)
    chosen, origin, _ = made.decide(OBS, node, inside, "Go to a new room.")
    assert (chosen.id, origin) == ("push:1", "forced")


def test_a_landmark_already_visited_is_reached_by_the_known_map():
    made = agent()
    here = [option("exit:B", "exit", "B"), option("exit:C", "exit", "C")]
    node = node_of("A", here)
    made.memory.arrive(node, here)
    made.memory.edges[node] = {"exit:C": "C@0"}
    made.memory.edges["C@0"] = {"exit:T": "T@0"}
    made.target = "T"
    assert made.decide(OBS, node, here, "Go north.")[:2] == (here[1], "route")


def test_an_exit_from_the_dungeon_to_an_unvisited_overworld_room_is_the_way_forward():
    made = agent()
    made.focus = 0x0D
    made.pyboy.memory[0xCC39] = 0x0D
    made.memory.dungeons["04:06"] = 0x0D
    options = [Option("exit:04:06", "exit", "west", (), "04:06", "Go west"),
               Option("exit:01:38", "exit", "stairs", (), "01:38", "Go outside")]
    node = node_of("04:07", options)
    made.memory.arrive(node, options)
    made.memory.record(node, "exit:04:06")
    chosen, origin, _ = made.decide(OBS, node, options, "Go to a new room.")
    assert (chosen.id, origin) == ("exit:01:38", "forced")


def test_with_nothing_pending_the_agent_sweeps_to_the_room_seen_longest_ago():
    made = agent()
    here = [option("exit:B", "exit", "B"), option("exit:C", "exit", "C")]
    node = node_of("A", here)
    made.memory.arrive(node, here)
    for name in ("exit:B", "exit:C"):
        made.memory.record(node, name)
    made.memory.edges[node] = {"exit:B": "B@0", "exit:C": "C@0"}
    made.memory.last_seen = {"A": 50, "B": 40}
    made.memory.dungeons = {"A": 0xFF, "B": 0xFF, "C": 0xFF}  # C is known but has no record: oldest
    made.pyboy.memory[0xCC39] = 0xFF
    obs = SimpleNamespace(room="A", x=10, y=20, facing="up")
    assert made.decide(obs, node, here, "Go to a new room.")[:2] == (here[1], "sweep")


def test_an_untaken_way_into_the_landmark_comes_before_the_known_path():
    made = agent()
    made.target = "T"
    options = [option("exit:B", "exit", "B"), option("exit:T/3", "exit", "T")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.memory.record(node, "exit:B")
    made.memory.edges[node] = {"exit:B": "B@0"}
    made.memory.edges["B@0"] = {"exit:T/1": "T@0"}
    chosen, origin, _ = made.decide(OBS, node, options, "Go east.")
    assert (chosen.id, origin) == ("exit:T/3", "route")


def test_a_part_of_the_landmark_with_nothing_left_is_not_a_destination_again():
    made = agent()
    made.landmark = "T"
    options = [option("exit:A/1", "exit", "A")]
    node = node_of("T", options)
    made.memory.arrive(node, options)
    made.memory.record(node, "exit:A/1")
    made.decide(SimpleNamespace(room="T", x=1, y=1, facing="up"), node, options, "Walk into the event.")
    assert made.memory.current["spent"] == [node]
    made.landmark, made.target = None, "T"
    back = [option("exit:T/1", "exit", "T")]
    here = node_of("A", back)
    made.memory.arrive(here, back)
    made.memory.record(here, "exit:T/1")
    made.memory.edges[here] = {"exit:T/1": node}
    _, origin, _ = made.decide(OBS, here, back, "Go north.")
    assert origin != "route"


def test_the_side_of_an_obstacle_is_told_only_when_no_exit_points_at_the_goal():
    made = agent()
    bush = Option("cut:1", "interact", "x", (), None, "Use the item on the obstacle to the west")
    options = [bush, Option("talk:1", "interact", "x", (), None, "Read the sign")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.decide(OBS, node, options, "Go west.")
    assert "Use the item on the obstacle to the west" in made.policy.asked[0].values()
    made = agent()
    options = [bush, Option("exit:B", "exit", "x", (), "B", "Go west")]
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.decide(OBS, node, options, "Go west.")
    assert "Use the item on the obstacle" in made.policy.asked[0].values()


def test_what_the_goal_asks_for_is_never_cut_from_a_long_list():
    made = agent()
    options = [Option(f"talk:{index}", "interact", "x", (), None, "Talk to the character") for index in range(14)]
    options.append(Option("exit:P", "exit", "x", (("up", 12),) * 9, "P", "Enter the door or stairs"))
    node = node_of("A", options)
    made.memory.arrive(node, options)
    made.decide(OBS, node, options, "Enter the door or stairs.")
    assert "Enter the door or stairs" in made.policy.asked[0].values()


def test_an_exit_found_by_a_closer_look_is_not_credited_to_the_last_action():
    made = agent()
    made.last = ("00:7a@0", "interact:2:6:05:eventc53a", {"exit:00:6a/3"}, b"same")
    made.note_opening("00:7a@0", {"exit:00:6a/3", "exit:00:79/5"}, b"same")
    assert made.memory.opened == {}
    made.last = ("04:0c@0", "push:7:4:up", set(), b"before")
    made.note_opening("04:0c@0", {"exit:04:0a/7"}, b"after")
    assert made.memory.opened == {"04:0c@0|push:7:4:up": ["exit:04:0a/7"]}


def test_a_talk_that_moves_the_story_ends_the_step_at_that_landmark(monkeypatch):
    import zelda_env.agent as module

    steps = (("00:38", "Talk to the character."), ("00:7c", "Enter the door or stairs."))
    monkeypatch.setattr(module, "OBJECTIVES", (("chave", steps, "Go to a new room.", lambda pyboy: False),))
    made = agent()
    assert made.objective("00:38") == ("chave", "Talk to the character.")
    assert made.objective("00:38") == ("chave", "Talk to the character.")  # same story state: still to do
    made.memory.enter(b"after the talk")
    assert made.objective("00:38") == ("chave", "Go south or east.")


def test_an_obstacle_removed_with_an_item_ends_the_step_at_that_landmark(monkeypatch):
    import zelda_env.agent as module

    steps = (("00:6a", "Use the item on the obstacle to the east."), ("00:7c", "Enter the door or stairs."))
    monkeypatch.setattr(module, "OBJECTIVES", (("chave", steps, "Go to a new room.", lambda pyboy: False),))
    made = agent()
    assert made.objective("00:6a") == ("chave", "Use the item on the obstacle to the east.")
    made.memory.enter(b"sapling burned")
    assert made.objective("00:6a") == ("chave", "Go east or south.")
    assert made.objective("00:6b")[1].startswith("Go ")


def test_redoing_what_opened_a_way_is_bounded_per_story_state():
    memory = Memory()
    cut, west = option("interact:2:6:05:eventc53a"), option("exit:00:79/5", "exit", "00:79")
    memory.unlocked("00:7a@0", cut.id, {west.id})
    for _ in range(3):
        assert memory.fresh("00:7a@0", [cut]) == [cut]  # the way west is closed again
        memory.record("00:7a@0", cut.id)
    assert memory.fresh("00:7a@0", [cut]) == []


def test_the_goal_direction_with_an_untaken_exit_comes_before_the_known_way():
    made = agent()
    south = Option("exit:C", "exit", "south", (), "C", "Go south")
    east = Option("exit:D", "exit", "east", (), "D", "Go east")
    node = node_of("A", [south, east])
    made.memory.arrive(node, [south, east])
    made.memory.record(node, south.id)  # the way south is known; the gate to the east just opened
    captured = []
    made.policy.choose = lambda context, criteria: (captured.append(context["goal"]) or sorted(criteria)[0], {})
    option, origin, _ = made.decide(OBS, node, [south, east], "Go south or east.")
    assert captured == [] and option is east and origin == "forced"
    made.memory.record(node, east.id)
    option, _, _ = made.decide(OBS, node, [south, east], "Go south or east.")
    assert option is south  # nothing new: the known way toward the goal is offered again


def test_a_way_the_last_action_opened_is_taken_before_the_known_route():
    made = agent()
    key, south = option("interact:4:4:15:event893a"), Option("exit:C", "exit", "south", (), "C", "Go south")
    gate = Option("exit:D", "exit", "east", (), "D", "Go east")
    node = node_of("A", [south])
    made.memory.arrive(node, [key, south])
    made.last = (node, key.id, {south.id}, b"gate closed")
    made.note_opening(node, {south.id, gate.id}, b"gate open")
    made.memory.arrive(node, [key, south, gate])
    option_, origin, _ = made.decide(OBS, node, [key, south, gate], "Go south.")
    assert option_ is gate and origin == "route"


def test_a_spent_part_of_the_landmark_stays_spent_when_the_story_moves_on(monkeypatch):
    import zelda_env.agent as module

    steps = (("00:8d", "Enter the door or stairs."),)
    monkeypatch.setattr(module, "OBJECTIVES", (("dungeon", steps, "Go to a new room.", lambda pyboy: False),))
    made = agent()
    made.objective("00:8d")
    made.spent.append("00:8d@0")
    made.memory.enter(b"gate unlocked")
    made.objective("00:5c")
    assert made.spent == ["00:8d@0"]


def test_a_second_gap_to_a_room_already_seen_is_not_taken_as_a_gate():
    made = agent()
    push, back = option("push:slot4@10:6:2:up", "push"), Option("exit:B/10", "exit", "south", (), "B", "Go south")
    other = Option("exit:B/0", "exit", "south", (), "B", "Go south")
    node = node_of("A", [back])
    made.memory.dungeons = {"A": 0, "B": 0}
    made.memory.arrive(node, [push, back])
    made.last = (node, "push:slot4@10:7:1:up", {back.id}, b"cube in the corridor")
    made.note_opening(node, {back.id, other.id}, b"cube moved")
    made.memory.arrive(node, [push, back, other])
    chosen, origin, _ = made.decide(OBS, node, [push, back, other], "Go to a new room.")
    assert origin != "route"


def test_the_sweep_does_not_go_straight_back_to_the_room_link_came_from():
    made = agent()
    here = [option("exit:B", "exit", "B"), option("exit:C", "exit", "C")]
    node = node_of("A", here)
    made.memory.arrive(node, here)
    for name in ("exit:B", "exit:C"):
        made.memory.record(node, name)
    made.memory.edges[node] = {"exit:B": "B@0", "exit:C": "C@0"}
    made.memory.last_seen = {"A": 50, "B": 10, "C": 40}
    made.memory.dungeons = {"A": 0xFF, "B": 0xFF, "C": 0xFF}
    made.pyboy.memory[0xCC39] = 0xFF
    made.entered_from = "B"  # the oldest seen, but Link has just come from it
    obs = SimpleNamespace(room="A", x=10, y=20, facing="up")
    assert made.decide(obs, node, here, "Go to a new room.")[:2] == (here[1], "sweep")


def test_coming_back_to_a_dungeon_room_makes_its_pushes_new_a_limited_number_of_times():
    memory = Memory()
    push, talk = option("push:slot4@10:7:1:up", "push"), option("interact:slot2:talk:text0001")
    memory.arrive("04:20@0", [push, talk])
    memory.record("04:20@0", push.id)
    memory.record("04:20@0", talk.id)
    for _ in range(4):
        memory.revisit("04:20@0")
        assert memory.fresh("04:20@0", [push, talk]) == [push]  # the talk stays done
        memory.record("04:20@0", push.id)
    memory.revisit("04:20@0")
    assert memory.fresh("04:20@0", [push, talk]) == []


def test_what_can_be_done_in_the_room_comes_before_going_back_to_a_seen_room():
    made = agent()
    back, other = option("exit:B/10", "exit", "B"), option("exit:B/0", "exit", "B")
    push = option("push:slot4@10:5:1:up", "push")
    node = node_of("A", [back])
    made.memory.current["visited"].append("B@0")
    made.memory.arrive(node, [back, other, push])
    made.memory.record(node, back.id)
    chosen, origin, _ = made.decide(OBS, node, [back, other, push], "Go to a new room.")
    assert chosen is push and origin == "forced"


def test_an_item_on_the_ground_is_picked_up_before_leaving():
    made = agent()
    key, door = option("collect:eb1589", "trigger"), option("exit:B", "exit", "B")
    node = node_of("A", [door])
    made.memory.arrive(node, [key, door])
    chosen, origin, _ = made.decide(OBS, node, [key, door], "Go to a new room.")
    assert chosen is key and origin == "forced"


def test_an_object_whose_push_opened_the_doors_is_not_pushed_again():
    memory = Memory()
    door = Option("exit:04:21/3", "exit", "east", (), "04:21", "Go east")
    more = [option("push:slot4@10:4:130:left", "push"), option("push:slot4@10:4:130:down", "push")]
    memory.unlocked("04:20@0", "push:slot4@10:5:1:up", {door.id})
    assert memory.fresh("04:20@0", [door, *more]) == [door]
    assert memory.fresh("04:20@0", more) == more  # the doors are shut again: the cube is back at the start
