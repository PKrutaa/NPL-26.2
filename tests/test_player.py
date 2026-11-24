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
