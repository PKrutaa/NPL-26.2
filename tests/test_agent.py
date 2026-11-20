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
