import pytest
from zelda_env import player


class Backend:
    model = "fake"

    def __init__(self, content):
        self.content = content

    def _post(self, path, payload, timeout):
        if isinstance(self.content, Exception):
            raise self.content
        return {"message": {"content": self.content}}


def test_the_planner_returns_the_goal_the_supervisor_wrote():
    planner = player.Planner(Backend('{"goal": "Walk  right to the door", "reason": "the gap is east"}'))
    assert planner.goal({"map": "#.#\\n#@#"}) == ("Walk right to the door", "the gap is east")


def test_the_planner_gives_no_goal_when_the_supervisor_fails():
    for broken in ("not json", '{"reason": "no goal"}', OSError("server down")):
        planner = player.Planner(Backend(broken))
        assert planner.goal({"map": "."}) == (None, None)
        assert planner.stats["failed"] == 1


def test_the_player_is_offered_only_buttons():
    assert set(player.BUTTONS) == {"up", "down", "left", "right", "a", "b"}


def test_next_step_walks_around_a_wall_and_stops_next_to_a_solid_target():
    lines = ["#.###",
             "#...#",
             "#@#N#",
             "#####"]
    assert player.next_step(lines, (1, 2), (1, 0)) == "up"
    assert player.next_step(lines, (1, 1), (1, 0)) == "up"
    assert player.next_step(lines, (1, 0), (1, 0)) == "here"
    assert player.next_step(lines, (1, 2), (3, 2)) == "up"      # the character: go around to stand next to it
    assert player.next_step(lines, (3, 1), (3, 2)) == "here"    # next to it
    assert player.next_step(lines, (1, 2), (4, 3)) is None      # inside the wall: no way to stand next to it


def test_next_step_is_consistent_along_a_path():
    lines = ["##.##",
             "#...#",
             "#.#.#",
             "#@..#"]
    cell, seen = (1, 3), []
    for _ in range(8):
        way = player.next_step(lines, cell, (2, 0))
        if way == "here":
            break
        seen.append(way)
        dx, dy = player.puzzle.STEP[way]
        cell = (cell[0] + dx, cell[1] + dy)
    assert cell == (2, 0) and len(seen) == 4  # never steps back


def test_side_of_names_the_direction_of_a_touching_cell():
    from zelda_env.player import side_of

    assert side_of((9, 2), (9, 3)) == "down"
    assert side_of((9, 2), (8, 2)) == "left"
    assert side_of((9, 2), (9, 2)) is None
    assert side_of((9, 2), (9, 5)) is None


def test_read_answer_keeps_the_complete_fields_of_an_answer_cut_short():
    from zelda_env.player import read_answer

    cut = '{\n"goal": "Walk left to leave the screen.",\n"column": 0,\n"row": 3,\n"then": "leave west",\n"reason": "The guide say'
    assert read_answer(cut) == {"goal": "Walk left to leave the screen.", "column": 0, "row": 3, "then": "leave west"}
    assert read_answer('{"goal": "Press A now.", "reason": "ok"}') == {"goal": "Press A now.", "reason": "ok"}
    with pytest.raises(ValueError):
        read_answer('{"goal": "Walk le')
