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
    made.pyboy = SimpleNamespace(memory={0xC6AA: 12, 0xC6AB: 12})
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
    assert set(made.policy.asked[0].values()) == {"Go north", "Talk to the character"}


def test_goal_follows_the_steps_of_the_objective():
    made = agent()
    made.pyboy = SimpleNamespace(memory={address: 0 for address in range(0xC600, 0xCA00)})
    made.pyboy.memory[0xC6D0 + 1] = 0x04  # sword received: global flag 0x0a
    assert made.objective("00:39") == ("maku-tree", "Go south or west.")
    assert made.objective("00:68") == ("maku-tree", "Go north.")  # waypoint passed on arrival
    assert made.objective("00:48") == ("maku-tree", "Enter the door or stairs.")
    assert made.objective("04:04") == ("maku-tree", "Go north.")  # inside the Maku Path
    assert made.objective("00:38") == ("maku-tree", "Talk to the character.")
