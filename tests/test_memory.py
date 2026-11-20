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
