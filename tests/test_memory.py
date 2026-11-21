"""The no-loop guarantee, checked on small worlds without the emulator."""

import json
import random

from zelda_env.agent import Memory, node_of
from zelda_env.survey import Option


def exits(*rooms):
    return [Option(f"exit:{room}", "exit", f"to {room}", (), room) for room in rooms]


def talk(name):
    return Option(f"interact:{name}", "interact", name, ())


def test_tried_option_is_not_offered_again():
    memory = Memory()
    options = [*exits("B"), talk("monkey:text1")]
    node = node_of("A", options)
    memory.arrive(node, options)
    assert len(memory.fresh(node, options)) == 2
    memory.record(node, "interact:monkey:text1")
    assert [option.id for option in memory.fresh(node, options)] == ["exit:B"]
    # The same character with a new line is a new option.
    assert talk("monkey:text2") in memory.fresh(node, [*options, talk("monkey:text2")])


def test_areas_of_one_room_are_separate_nodes():
    assert node_of("A", exits("B")) != node_of("A", exits("C"))


def test_progress_keeps_talks_and_reopens_the_map():
    memory = Memory()
    options = [*exits("B"), talk("bear:text1")]
    node = node_of("A", options)
    memory.arrive(node, options)
    memory.record(node, "exit:B")
    memory.record(node, "interact:bear:text1")
    assert memory.enter(b"sword")
    assert [option.id for option in memory.fresh(node, options)] == ["exit:B"]
    # A flag that toggles back restores the earlier record instead of resetting it.
    memory.enter(b"")
    assert memory.fresh(node, options) == []


def test_hop_leads_to_the_nearest_area_with_untried_options():
    memory = Memory()
    a, b, c = exits("B"), exits("A", "C"), [*exits("B"), talk("npc:text1")]
    na, nb, nc = node_of("A", a), node_of("B", b), node_of("C", c)
    memory.arrive(na, a)
    memory.record(na, "exit:B")
    memory.arrive(nb, b, na, "exit:B")
    memory.record(nb, "exit:C")
    memory.arrive(nc, c, nb, "exit:C")
    memory.record(nc, "exit:B")
    memory.arrive(nb, b, nc, "exit:B")
    memory.record(nb, "exit:A")
    memory.arrive(na, a, nb, "exit:A")
    assert memory.fresh(na, a) == []
    assert memory.hop(na, a) == "exit:B"


def test_dump_and_load_round_trip():
    memory = Memory()
    options = exits("B")
    node = node_of("A", options)
    memory.arrive(node, options)
    memory.record(node, "exit:B")
    memory.banned.add((node, "exit:B"))
    restored = Memory.load(json.loads(json.dumps(memory.dump())))
    assert restored.tries(node, "exit:B") == 1 and (node, "exit:B") in restored.banned


def test_exploration_of_a_random_world_terminates_without_repeats():
    """Follow fresh options, then hops, on random graphs. It must stop, never spin."""
    for seed in range(30):
        rng = random.Random(seed)
        rooms = [f"r{index}" for index in range(12)]
        links = {room: set() for room in rooms}
        for index, room in enumerate(rooms[1:], 1):
            other = rooms[rng.randrange(index)]
            links[room].add(other)
            links[other].add(room)
        world = {room: [*exits(*sorted(links[room])), talk(f"{room}:text")] for room in rooms}
        memory, room, origin, via = Memory(), "r0", None, None
        for steps in range(10_000):
            options = world[room]
            node = node_of(room, options)
            memory.arrive(node, options, origin, via)
            fresh = memory.fresh(node, options)
            choice = rng.choice(fresh).id if fresh else memory.hop(node, options)
            if choice is None:
                break
            memory.record(node, choice)
            origin, via = node, choice
            if choice.startswith("exit:"):
                room = choice.split(":", 1)[1]
        else:
            raise AssertionError("exploration did not terminate")
        tried = memory.current["tried"]
        assert all(f"{node_of(name, world[name])}|interact:{name}:text" in tried for name in rooms)
        assert max(count for key, count in tried.items() if "interact" in key) == 1
        assert steps < 200


def test_a_character_with_many_lines_is_talked_to_three_times():
    memory = Memory()
    lines = [Option(f"interact:slot4:a:text{index}", "interact", "talk", ()) for index in range(6)]
    node = node_of("A", lines)
    memory.arrive(node, lines)
    for option in lines[:3]:
        memory.record(node, option.id)
    assert memory.fresh(node, lines) == []
    # Another character in the same place is unaffected.
    other = Option("interact:slot5:a:text0", "interact", "talk", ())
    assert memory.fresh(node, [*lines, other]) == [other]


def test_tool_uses_in_one_area_run_out():
    memory = Memory()
    digs = [Option(f"item:15:3a:{index:02x}", "interact", "dig", ()) for index in range(14)]
    door = Option("exit:B", "exit", "door", (), "B")
    node = node_of("A", [door])
    memory.arrive(node, [*digs, door])
    for option in digs[:10]:
        assert option in memory.fresh(node, [*digs, door])
        memory.record(node, option.id)
    assert memory.fresh(node, [*digs, door]) == [door]


def test_surveys_that_share_an_exit_are_the_same_area():
    memory = Memory()
    first = memory.area("A", exits("B"))
    assert memory.area("A", exits("B", "C")) == first  # a closer look found one more exit
    assert memory.area("A", exits("C")) == first
    other = memory.area("A", exits("D"))  # no exit in common: another part of the room
    assert other != first
    assert Memory.load(json.loads(json.dumps(memory.dump()))).area("A", exits("D")) == other


def test_a_survey_that_links_two_areas_joins_their_records():
    memory = Memory()
    south = memory.area("A", exits("S"))
    north = memory.area("A", exits("N"))
    assert south != north
    memory.arrive(north, exits("N"))
    memory.record(north, "exit:N")
    memory.edges.setdefault("X@0", {})["exit:A"] = north
    joined = memory.area("A", exits("S", "N"))  # the block between them was pushed aside
    assert joined == south
    assert memory.tries(south, "exit:N") == 1
    assert memory.edges["X@0"]["exit:A"] == south
    assert north not in memory.current["pending"] and north not in memory.current["visited"]


def test_an_option_that_opened_a_way_is_offered_again_when_the_way_closes():
    memory = Memory()
    push = Option("push:7:4:up", "push", "push", ())
    closed, opened = [*exits("S"), push], [*exits("S", "N"), push]
    node = memory.area("A", closed)
    memory.arrive(node, closed)
    memory.record(node, push.id)
    memory.unlocked(node, push.id, {"exit:N"})
    assert push not in memory.fresh(node, opened)   # the way is open: nothing to redo
    assert push in memory.fresh(node, closed)       # the room reset: push again


def test_way_out_follows_the_known_map_and_trips_skip_other_interiors():
    memory = Memory()
    hall, back = exits("01:76", "04:e8"), exits("04:e7")
    hall_node, back_node, outside = memory.area("04:e7", hall), memory.area("04:e8", back), "01:76@0"
    memory.edges[back_node] = {"exit:04:e7": hall_node}
    memory.edges[hall_node] = {"exit:01:76": outside, "exit:04:e8": back_node}
    assert memory.hop(back_node, back, leaving=True) == "exit:04:e7"
    assert memory.hop(hall_node, hall, leaving=True) == "exit:01:76"
    # Something untried deep in this interior attracts a trip only if the room is allowed.
    memory.current["pending"][back_node] = ["talk"]
    assert memory.hop(hall_node, hall) == "exit:04:e8"
    assert memory.hop(hall_node, hall, lambda room: room.startswith("01:")) is None


def test_coming_back_to_a_dungeon_room_makes_its_actions_available_again():
    memory = Memory()
    push, door = Option("push:7:4:up", "push", "push", ()), Option("exit:N", "exit", "north", (), "N")
    node = memory.area("A", [door])
    memory.arrive(node, [push, door])
    memory.record(node, push.id)
    memory.record(node, door.id)
    memory.revisit(node)
    assert memory.fresh(node, [push, door]) == [push]  # the exit stays known
    for _ in range(10):
        memory.record(node, push.id)
        memory.revisit(node)
    assert memory.fresh(node, [push, door]) == []  # the limit holds
