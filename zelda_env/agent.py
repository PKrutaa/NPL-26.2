"""Let Laya play: it picks among surveyed options, and memory keeps it out of loops.

    python -m zelda_env.agent --headless --decisions 200

Each decision surveys the room in a headless copy, drops options already tried without
progress, and asks Laya to choose among the rest. With nothing new in the room, the
agent travels to the nearest room that still has untried options. A small local LLM can
be consulted when the game confirms an impasse.
"""

import argparse
import hashlib
import json
import platform
import random
import time
from collections import deque
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

from . import paths
from .__main__ import add_common, resolve_common
from .adapter import execute, observe, room_layout, show_status
from .survey import ESSENCES, HEALTH, Surveyor, progress, run_route

GLOBAL_FLAGS = 0xC6D0
TREASURES = 0xC69A
TEXT_DISPLAY_STATE = (7, 0xD0C0)
MEMORY_FORMAT = 4
TALKS_PER_CHARACTER = 3
TOOL_USES_PER_AREA = 10
SURVEY_LEVELS = (
    {"grid": 16, "stride": 16, "limit": 400},
    {"grid": 8, "stride": 12, "limit": 700},
    {"grid": 4, "stride": 12, "limit": 1500},
)


def _flag(base, index):
    return lambda pyboy: bool(pyboy.memory[base + index // 8] & (1 << index % 8))


ROOM_VISITED = 0x10
GROUP4_ROOM_FLAGS = 0xC900

# Hand-written landmarks orient the task. Each objective lists steps as (room, what to
# do there), a short goal for when Link is on another map (indoors, a dungeon, the other
# era), and a fact read from the game that ends it. There are no routes or coordinates.
# Rooms and flags come from the pinned disassembly (warp tables, global flags, treasures).
OBJECTIVES = (
    ("espada", (("00:39", "Talk to the character and wait for the event."),),
     "Enter the door or stairs.", _flag(GLOBAL_FLAGS, 0x0A)),
    ("maku-tree", (("00:68", None), ("00:48", "Enter the door or stairs."), ("00:38", "Talk to the character.")),
     "Go north.", _flag(GLOBAL_FLAGS, 0x0C)),
    ("passado", (("00:39", "Walk into the event."),), "Go south.", _flag(GLOBAL_FLAGS, 0x41)),
    ("pa", (("01:76", "Enter the door or stairs."),), "Go to a new room or talk to the character.",
     _flag(TREASURES, 0x15)),
    ("maku-tree-salva", (("01:48", "Use the item on the ground or enter the door or stairs."),),
     "Go to a new room.",
     _flag(GLOBAL_FLAGS, 0x12)),
    ("chave-do-cemiterio", (("01:39", "Walk into the event."), ("00:38", "Talk to the character."),
                            ("00:7c", "Enter the door or stairs.")),
     "Enter the door or stairs.", _flag(TREASURES, 0x42)),
    ("dungeon-1", (("00:8d", "Enter the door or stairs."),), "Enter the door or stairs.",
     lambda pyboy: bool(pyboy.memory[GROUP4_ROOM_FLAGS + 0x24] & ROOM_VISITED)),
    ("essencia-1", (), "Go to a new room.", lambda pyboy: bool(pyboy.memory[ESSENCES] & 1)),
    ("oito-essencias", (), "Go to a new room.", lambda pyboy: pyboy.memory[ESSENCES] == 0xFF),
)


def heading(room, target):
    """Compass words from one overworld screen to another. None across maps."""
    if room[:2] != target[:2] or room == target:
        return None
    here, there = int(room[3:], 16), int(target[3:], 16)
    dy, dx = there // 16 - here // 16, there % 16 - here % 16
    vertical = "north" if dy < 0 else "south" if dy > 0 else ""
    horizontal = "west" if dx < 0 else "east" if dx > 0 else ""
    # The longer leg first: the goal names one direction, and this is the order to try.
    words = [vertical, horizontal] if abs(dy) >= abs(dx) else [horizontal, vertical]
    return " or ".join(word for word in words if word)


def node_of(room, options):
    """A room can have areas that do not connect. Exits tell them apart."""
    exits = sorted(option.destination for option in options if option.kind == "exit")
    return f"{room}@{'+'.join(exits)}"


class Memory:
    """What was tried where. One record per story state, so a toggled flag cannot reset it."""

    def __init__(self):
        self.epochs = {}
        self.edges = {}  # node -> {option_id: node reached}
        self.banned = set()  # (node, option_id): led to death or left Link without control
        self.landmarks = {}  # objective -> which step it is on
        self.decisions = 0  # carried across sessions, so a resumed trace keeps counting
        self.epoch = None
        self.current = None
        self.enter(b"")

    def enter(self, key):
        key = hashlib.sha256(key).hexdigest()[:16]
        changed = key != self.epoch
        self.epoch = key
        if key not in self.epochs:
            # The map is explored again after progress. Talks, pushes and events are
            # identified by their outcome, so the ones already done stay done.
            kept = {name: count for name, count in (self.current["tried"] if self.epochs else {}).items()
                    if not name.split("|", 1)[1].startswith("exit:")}
            self.epochs[key] = {"tried": kept, "visited": [], "pending": {}, "depth": {}}
        self.current = self.epochs[key]
        return changed

    def tries(self, node, option_id):
        return self.current["tried"].get(f"{node}|{option_id}", 0)

    def fresh(self, node, options):
        """Options worth trying now: not dropped and not tried here in this story state."""
        def chatty(option):
            # Some characters cycle through many lines. Three talks each are enough.
            if not option.id.startswith("interact:slot"):
                return False
            prefix = f"{node}|{':'.join(option.id.split(':')[:2])}:"
            return sum(key.startswith(prefix) for key in self.current["tried"]) >= TALKS_PER_CHARACTER

        def tool_use(name):
            return name.startswith("item:") or (name.startswith("interact:") and name.endswith(":event")
                                                and not name.startswith("interact:slot"))

        # A tool can act on every tile of a room. After enough tries in one area with no
        # progress, more of the same is not something new.
        worn = sum(count for key, count in self.current["tried"].items()
                   if key.startswith(f"{node}|") and tool_use(key.split("|", 1)[1])) >= TOOL_USES_PER_AREA

        return [option for option in options
                if (node, option.id) not in self.banned and not self.tries(node, option.id)
                and not chatty(option) and not (worn and tool_use(option.id))]

    def arrive(self, node, options, origin=None, via=None):
        """Record the area Link is in, and how he got here."""
        if origin and via:
            self.edges.setdefault(origin, {})[via] = node
            back = f"exit:{origin.split('@')[0]}"
            if origin != node and node not in self.current["visited"] and any(o.id == back for o in options):
                # Screen edges normally work both ways. Do not spend a decision confirming it.
                self.edges.setdefault(node, {}).setdefault(back, origin)
                self.current["tried"].setdefault(f"{node}|{back}", 1)
        if node not in self.current["visited"]:
            self.current["visited"].append(node)
        self.current["pending"][node] = [option.id for option in self.fresh(node, options)]

    def record(self, node, option_id):
        key = f"{node}|{option_id}"
        self.current["tried"][key] = self.current["tried"].get(key, 0) + 1
        pending = self.current["pending"].get(node, [])
        if option_id in pending:
            pending.remove(option_id)

    def hop(self, node, options):
        """First step of the shortest known path to an area that still has untried options."""
        available = {option.id for option in options if (node, option.id) not in self.banned}
        queue = deque((destination, option_id) for option_id, destination in self.edges.get(node, {}).items()
                      if option_id in available and destination != node)
        seen = {node}
        while queue:
            current, first = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            if self.current["pending"].get(current):
                return first
            queue.extend((destination, first) for destination in self.edges.get(current, {}).values())
        return None

    def dump(self):
        return {"format": MEMORY_FORMAT, "epochs": self.epochs, "edges": self.edges,
                "banned": sorted(map(list, self.banned)), "epoch": self.epoch, "landmarks": self.landmarks,
                "decisions": self.decisions}

    @classmethod
    def load(cls, data):
        if data.get("format") != MEMORY_FORMAT:
            raise ValueError(f"Formato de memória incompatível: {data.get('format')}")
        memory = cls()
        memory.epochs, memory.edges = data["epochs"], data["edges"]
        memory.banned = {tuple(item) for item in data["banned"]}
        memory.epoch = data["epoch"]
        memory.landmarks = data.get("landmarks", {})
        memory.decisions = data.get("decisions", 0)
        memory.current = memory.epochs[memory.epoch]
        return memory


class BaselinePolicy:
    """Stand-in for Laya with the same candidates, to measure what its choices add."""

    def __init__(self, kind, seed=0):
        self.kind = kind
        self.rng = random.Random(seed)
        self.model = {"id": f"baseline:{kind}", "seed": seed}

    def choose(self, context, criteria):
        # Candidates arrive ordered by route length, so the first key is the nearest one.
        keys = list(criteria)
        return (self.rng.choice(keys) if self.kind == "random" else keys[0]), {"baseline": self.kind}

    def __call__(self, goal, observation, candidates, trace):
        return "interact", {"baseline": self.kind}


class Agent:
    def __init__(self, pyboy, surveyor, policy, *, supervisor=None, memory=None, watch=False,
                 log=None, stall=20, patience=6):
        self.pyboy = pyboy
        self.surveyor = surveyor
        self.policy = policy
        self.supervisor = supervisor
        self.memory = memory or Memory()
        self.watch = watch
        self.log = log
        self.stall = stall  # decisions without story progress before asking the supervisor
        self.patience = patience  # fallback decisions with nothing new before stopping
        self.decisions = 0
        self.since_progress = 0
        self.idle = 0
        self.recent = deque(maxlen=3)
        self.origins = {}
        self.deaths = 0
        self.empty = 0
        self.scenes = 0
        self.damage = 0
        self.arrival = (None, None)  # (node left, option taken) for the last decision
        self.done = [item[0] for item in OBJECTIVES if item[3](pyboy)]

    def objective(self, room=None):
        """Current objective and a short goal: a direction to the next landmark, or what to do."""
        for name, steps, elsewhere, reached in OBJECTIVES:
            if reached(self.pyboy):
                continue
            state = self.memory.landmarks.setdefault(name, {"step": 0, "arrived": False})
            while room and state["step"] < len(steps):
                target, task = steps[state["step"]]
                last = state["step"] == len(steps) - 1
                if room == target:
                    if task is None and not last:
                        state["step"] += 1  # a waypoint: nothing to do here
                        continue
                    state["arrived"] = True
                    return name, task or elsewhere
                if state["arrived"] and room[:2] != target[:2] and not last:
                    # The task here was to go through something, and Link did.
                    state.update(step=state["step"] + 1, arrived=False)
                    continue
                where = heading(room, target)
                return name, (f"Go {where}." if where else elsewhere)
            return name, elsewhere
        return None, "Explore."

    def status(self, text):
        if self.watch:
            show_status(self.pyboy, f"Laya | {text}")

    def settle(self, budget=2400):
        """Run cutscenes and dialogue until Link is controllable again."""
        quiet = 0
        for _ in range(budget):
            obs = observe(self.pyboy)
            if obs.mode == "playing":
                quiet += 1
                # Scenes return to normal mode between lines while inputs are still ignored.
                if quiet > 8 and (self.surveyor.can_move(self.pyboy) or quiet > 120):
                    return True
            else:
                quiet = 0
            action = "wait"
            if obs.mode == "dialogue" and (obs.dialogue_ready or self.pyboy.memory[TEXT_DISPLAY_STATE] in (2, 4, 10)):
                action = "interact"
                if obs.dialogue_ready and self.policy:
                    action, _ = self.policy(
                        "Continue the current story dialogue. Confirm and advance the text.",
                        obs, ("interact", "cancel"), (),
                    )
            execute(self.pyboy, action, render=self.watch)
        return False

    def context(self, obs, hint):
        return {
            "goal": hint,
            "room": obs.room,
            "link position": f"x={obs.x} y={obs.y} facing {obs.facing}",
            "rooms visited since last progress": len(self.memory.current["visited"]),
            "decisions since last progress": self.since_progress,
            "health": f"{self.pyboy.memory[HEALTH] / 4:g} of {self.pyboy.memory[HEALTH + 1] / 4:g} hearts",
            "recent": "; ".join(self.recent) or "nothing yet",
        }

    def decide(self, obs, room, options, hint):
        """Return (option, origin, details). The candidate set is what prevents loops."""
        usable = [option for option in options if (room, option.id) not in self.memory.banned]
        fresh = self.memory.fresh(room, options)
        impasse = not fresh
        if impasse:
            first = self.memory.hop(room, options)
            if first:
                return next(option for option in usable if option.id == first), "frontier", {}
        candidates = sorted(fresh or usable, key=lambda option: len(option.route))[:12]
        if not candidates:
            return None, "none", {}
        context = self.context(obs, hint)
        if self.supervisor and len(candidates) > 1 and (impasse or self.since_progress >= self.stall):
            annotated = [(option.id, option.description + (
                "" if not self.memory.tries(room, option.id) else " (already tried)")) for option in candidates]
            choice, record = self.supervisor.consult(context, annotated, self.decisions)
            if choice:
                return next(option for option in candidates if option.id == choice), "supervisor", record
            details = record
        else:
            details = {}
        if impasse:
            # Nothing new anywhere known: least-tried first, so repeats rotate instead of sticking.
            option = min(candidates, key=lambda option: (self.memory.tries(room, option.id), len(option.route)))
            return option, "fallback", details
        if len(candidates) == 1:
            return candidates[0], "forced", details
        keys = {f"option_{index + 1}": option for index, option in enumerate(candidates)}
        # Laya matches short text well and long text at chance, so it gets only the goal.
        seen = {name.split("@")[0] for name in self.memory.current["visited"]}

        def brief(option):
            text = option.short or option.description
            # An exit to a room not seen in this story state says so: goals can ask for it.
            fresh_room = option.kind == "exit" and option.destination not in seen
            return f"{text} to a new room" if fresh_room and text.startswith("Go ") else text

        criteria = {key: brief(option) for key, option in keys.items()}
        # Laya follows one direction far better than two. Name the first that has an exit.
        if " or " in hint and hint.startswith("Go "):
            wanted = hint[3:-1].split(" or ")
            offered = [way for way in wanted if any(text.startswith(f"Go {way}") for text in criteria.values())]
            hint = f"Go {(offered or wanted)[0]}."
        key, laya = self.policy.choose({"goal": hint}, criteria)
        # The origin names who chose, so a comparison run is never attributed to Laya.
        return keys[key], getattr(self, "label", "laya"), {**details, "laya": laya}

    def step(self):
        """One decision. Returns False when there is nothing left to try."""
        if not self.settle():
            self.write({"event": "stuck_outside_control", "mode": observe(self.pyboy).mode})
            return False
        obs = observe(self.pyboy)
        if self.memory.enter(progress(self.pyboy)) and self.decisions:
            self.since_progress = 0
            self.idle = 0
            if self.supervisor:
                self.supervisor.progressed()
        name, hint = self.objective(obs.room)
        started = time.perf_counter()
        # A quick pass on 16-pixel steps first. The slower passes run only when the area
        # has nothing new, or still owes an option that only they can route to.
        options = self.surveyor.options(self.pyboy, **SURVEY_LEVELS[0])
        node = node_of(obs.room, options)
        # Record the arrival first: it marks the way back as known, and the decision to
        # look deeper must not count that exit as something new.
        self.memory.arrive(node, options, *self.arrival)
        self.arrival = (None, None)
        depth = self.memory.current.setdefault("depth", {})
        level = 0
        # How closely an area was examined holds only while its terrain is the same:
        # a door that opens after a fight must be looked for again.
        terrain = bytes(self.pyboy.memory[0xCE00:0xCEC0]) + room_layout(self.pyboy)
        examined = f"{node}#{hashlib.sha1(terrain).hexdigest()[:8]}"
        # An area with a single way out looks like a dead end. Narrow exits are what the
        # quick pass misses, so look closer once before accepting that.
        dead_end = sum(option.kind == "exit" for option in options) <= 1 and not depth.get(examined)
        while level < len(SURVEY_LEVELS) - 1 and (dead_end or not self.memory.fresh(node, options)):
            dead_end = False
            found = {option.id for option in options}
            owed = [item for item in self.memory.current["pending"].get(node, []) if item not in found]
            if depth.get(examined, 0) > level and not owed:
                break  # the deeper passes already ran here and left nothing to do
            if level == len(SURVEY_LEVELS) - 2 and not owed and self.memory.hop(node, options):
                break  # the finest pass is slow: keep it for when no other area has options
            level += 1
            depth[examined] = max(depth.get(examined, 0), level)
            options += [option for option in self.surveyor.options(self.pyboy, **SURVEY_LEVELS[level])
                        if option.id not in found]
        survey_seconds = time.perf_counter() - started
        # A scene that continues by itself is not a choice. Let it play and look again.
        scene = next((option for option in self.memory.fresh(node, options)
                      if option.id.startswith("trigger:wait:") and len(option.route) == 1), None)
        if scene:
            self.memory.record(node, scene.id)
            run_route(self.pyboy, scene.route, render=self.watch)
            self.scenes += 1
            self.write({"event": "scene", "room": obs.room, "id": scene.id})
            return True
        self.memory.arrive(node, options)
        started = time.perf_counter()
        option, origin, details = self.decide(obs, node, options, hint)
        choice_seconds = time.perf_counter() - started
        if option is None:
            # Usually a scene that started between two checks. Let it play, then look again.
            self.empty += 1
            self.write({"event": "no_options", "room": obs.room, "xy": [obs.x, obs.y], "streak": self.empty})
            for _ in range(10):
                execute(self.pyboy, "wait", render=self.watch)
            return self.empty <= 12
        self.empty = 0
        if origin == "fallback":
            self.idle += 1
            if self.idle > self.patience:
                self.write({"event": "impasse", "room": obs.room, "xy": [obs.x, obs.y], "objective": name})
                return False
        self.decisions += 1
        self.since_progress += 1
        self.origins[origin] = self.origins.get(origin, 0) + 1
        self.status(f"{name} | {option.description}")
        before = BytesIO()
        self.pyboy.save_state(before)
        health, story = self.pyboy.memory[HEALTH], progress(self.pyboy)
        self.memory.record(node, option.id)
        run_route(self.pyboy, option.route, render=self.watch)
        controllable = self.settle()
        after = observe(self.pyboy)
        outcome = "nothing new"
        if self.pyboy.memory[HEALTH] == 0 or not controllable:
            # Retry from this agent's own state and never take this option here again.
            self.memory.banned.add((node, option.id))
            self.pyboy.load_state(BytesIO(before.getvalue()))
            self.deaths += 1
            outcome = "failed, option dropped"
        elif progress(self.pyboy) != story:
            outcome = "story progressed"
        elif option.kind == "fight":
            outcome = "enemy defeated"
        elif after.room != obs.room:
            outcome = f"moved to room {after.room}"
        lost = health - self.pyboy.memory[HEALTH]
        if lost > 0 and self.pyboy.memory[HEALTH]:
            self.damage += lost
            outcome += f", lost {lost / 4:g} heart"
        if outcome != "failed, option dropped":
            self.arrival = (node, option.id)
        self.recent.append(f"{option.description} -> {outcome}")
        reached = [item[0] for item in OBJECTIVES if item[3](self.pyboy) and item[0] not in self.done]
        self.done.extend(reached)
        self.write({
            "decision": self.decisions, "objective": name, "room": obs.room, "xy": [obs.x, obs.y],
            "options": [item.id for item in options], "choice": option.id, "description": option.description,
            "origin": origin, "outcome": outcome, "after_room": after.room, "inputs": len(option.route),
            "survey_s": round(survey_seconds, 2), "survey_level": level, "choice_ms": round(choice_seconds * 1000, 1),
            "node": node, "tries_here": self.memory.tries(node, option.id), "reached": reached,
            "health": [self.pyboy.memory[HEALTH], self.pyboy.memory[HEALTH + 1]], **details,
        })
        if self.watch:
            print(f"{self.decisions}: [{origin}] {option.description} → {outcome}", flush=True)
        return True

    def write(self, record):
        if self.log:
            self.log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.log.flush()

    def summary(self):
        tried = [count for epoch in self.memory.epochs.values() for count in epoch["tried"].values()]
        obs = observe(self.pyboy)
        return {
            "decisions": self.decisions, "origins": self.origins, "objectives_reached": self.done,
            "essences": bin(self.pyboy.memory[ESSENCES]).count("1"), "room": obs.room, "xy": [obs.x, obs.y],
            "rooms_visited": len({node.split("@")[0] for epoch in self.memory.epochs.values()
                                  for node in epoch["visited"]}),
            "story_states": len(self.memory.epochs), "deaths_or_retries": self.deaths,
            "scenes_waited": self.scenes, "health": [self.pyboy.memory[HEALTH], self.pyboy.memory[HEALTH + 1]],
            "quarter_hearts_lost": self.damage,
            "max_repeats_of_one_option_in_one_story_state": max(tried, default=0),
            "supervisor": self.supervisor.stats if self.supervisor else None,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common(parser)
    parser.add_argument("--seed-state", type=Path, help="Ponto de partida. Padrão: output/inicio.state")
    parser.add_argument("--directory", type=Path, help="Sessão (estado, memória, trace). Padrão: output/agent")
    parser.add_argument("--decisions", type=int, default=200, help="Orçamento de decisões desta execução")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--fresh", action="store_true", help="Ignora a sessão salva e recomeça do seed")
    parser.add_argument("--supervisor", metavar="MODELO", help="Modelo Ollama local consultado em impasses")
    parser.add_argument("--supervisor-timeout", type=float, default=20.0)
    parser.add_argument("--stall", type=int, default=20,
                        help="Decisões sem progresso na história antes de consultar o supervisor")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--policy", choices=("laya", "random", "shortest"), default="laya",
                        help="Quem escolhe entre as opções novas. random e shortest são comparação")
    parser.add_argument("--seed", type=int, default=0, help="Semente de --policy random")
    args = resolve_common(parser, parser.parse_args())
    seed = args.seed_state or paths.output_path("inicio.state")
    directory = args.directory or paths.output_path("agent")
    latest, memory_file = directory / "latest.state", directory / "memory.json"
    resume = latest.is_file() and memory_file.is_file() and not args.fresh
    start = latest if resume else seed
    if not start.is_file():
        parser.exit(1, f"Seed ausente: {start}. Gere com: {paths.venv_python()} -m zelda_env seed\n")

    supervisor = None
    if args.supervisor:
        from .supervisor import OllamaBackend, Supervisor, SupervisorUnavailable

        backend = OllamaBackend(args.supervisor)
        try:
            backend.check()
        except SupervisorUnavailable as error:
            # The supervisor is optional. Without it the agent uses its own recovery.
            print(f"Supervisor desligado: {error}", flush=True)
        else:
            supervisor = Supervisor(backend, timeout=args.supervisor_timeout)

    if args.policy == "laya":
        from .laya_policy import LayaPolicy

        try:
            policy = LayaPolicy(args.device, "text", False)
        except RuntimeError as error:
            parser.exit(1, f"{error}\n")
    else:
        policy = BaselinePolicy(args.policy, args.seed)

    from pyboy import PyBoy

    pyboy = PyBoy(str(args.rom), window="null" if args.headless else "SDL2",
                  ram_file=BytesIO(bytes(paths.SRAM_BYTES)), sound_volume=0)
    pyboy.set_emulation_speed(0 if args.headless else 2)
    surveyor = Surveyor(args.rom)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with paths.ProfileLock(latest):
            with start.open("rb") as stream:
                pyboy.load_state(stream)
            memory = Memory.load(json.loads(memory_file.read_text(encoding="utf-8"))) if resume else None
            print(f"Sessão {'retomada' if resume else 'iniciada'} de {start}", flush=True)
            with (directory / "trace.jsonl").open("a" if resume else "w", encoding="utf-8") as log:
                agent = Agent(pyboy, surveyor, policy, supervisor=supervisor, memory=memory,
                              watch=not args.headless, log=log, stall=args.stall)
                agent.label = args.policy
                agent.decisions = agent.memory.decisions
                budget = agent.decisions + args.decisions
                reason = "orçamento de decisões"
                started = time.perf_counter()
                try:
                    while agent.decisions < budget:
                        reached = len(agent.done)
                        if not agent.step():
                            reason = "impasse"
                            break
                        if agent.decisions % 5 == 0 or len(agent.done) > reached:
                            save(pyboy, agent, latest, memory_file)
                            for name in agent.done[reached:]:
                                save(pyboy, agent, directory / f"objetivo-{name}.state", None)
                                print(f"Objetivo concluído: {name}", flush=True)
                except (InterruptedError, KeyboardInterrupt):
                    reason = "interrompido"
                else:
                    save(pyboy, agent, latest, memory_file)
                report = {
                    **agent.summary(), "stopped": reason, "seconds": round(time.perf_counter() - started, 1),
                    "rom_sha1": paths.AGES_SHA1, "pyboy": version("pyboy"), "python": platform.python_version(),
                    "system": f"{platform.system()} {platform.machine()}", "policy": args.policy, "model": policy.model,
                    "device": args.device,
                }
                paths.atomic_write(directory / "summary.json",
                                   (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
                print(json.dumps(report, indent=2, ensure_ascii=False))
    except paths.ProfileBusy as error:
        parser.exit(1, f"{error}\n")
    finally:
        surveyor.close()
        pyboy.stop(save=False)


def save(pyboy, agent, state_path, memory_path):
    stream = BytesIO()
    pyboy.save_state(stream)
    paths.atomic_write(state_path, stream.getvalue())
    if memory_path:
        agent.memory.decisions = agent.decisions
        paths.atomic_write(memory_path, json.dumps(agent.memory.dump()).encode("utf-8"))


if __name__ == "__main__":
    main()
