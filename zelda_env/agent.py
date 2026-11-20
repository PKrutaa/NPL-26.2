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
from .adapter import execute, observe, show_status
from .survey import ESSENCES, HEALTH, Surveyor, progress, run_route

GLOBAL_FLAGS = 0xC6D0
TREASURES = 0xC69A
TEXT_DISPLAY_STATE = (7, 0xD0C0)
MEMORY_FORMAT = 2


def _flag(base, index):
    return lambda pyboy: bool(pyboy.memory[base + index // 8] & (1 << index % 8))


# Hand-written hints orient the task. Each one ends on a fact read from the game.
OBJECTIVES = (
    ("espada", "Go north to find Impa and follow her. Help her, then meet Nayru in the forest clearing "
               "and talk to everyone there.", _flag(GLOBAL_FLAGS, 0x0A)),
    ("maku-tree", "Leave the forest, travel west to Lynna City, then go north to meet the Maku Tree.",
     _flag(GLOBAL_FLAGS, 0x0C)),
    ("passado", "Return to the forest clearing east of the Maku Tree and step into the time portal.",
     _flag(GLOBAL_FLAGS, 0x41)),
    ("pa", "In the past, travel south-west to the Black Tower and get the shovel from the workers inside.",
     _flag(TREASURES, 0x15)),
    ("essencia-1", "Go to the Maku Tree gate in the north of Lynna Village, save the Maku Tree, then find "
                   "the first dungeon and obtain the first Essence of Time.",
     lambda pyboy: bool(pyboy.memory[ESSENCES] & 1)),
    ("oito-essencias", "Obtain all eight Essences of Time.", lambda pyboy: pyboy.memory[ESSENCES] == 0xFF),
)


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
            self.epochs[key] = {"tried": kept, "visited": [], "pending": {}, "fine": []}
        self.current = self.epochs[key]
        return changed

    def tries(self, node, option_id):
        return self.current["tried"].get(f"{node}|{option_id}", 0)

    def fresh(self, node, options):
        """Options worth trying now: not dropped and not tried here in this story state."""
        return [option for option in options
                if (node, option.id) not in self.banned and not self.tries(node, option.id)]

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
                "banned": sorted(map(list, self.banned)), "epoch": self.epoch}

    @classmethod
    def load(cls, data):
        if data.get("format") != MEMORY_FORMAT:
            raise ValueError(f"Formato de memória incompatível: {data.get('format')}")
        memory = cls()
        memory.epochs, memory.edges = data["epochs"], data["edges"]
        memory.banned = {tuple(item) for item in data["banned"]}
        memory.epoch = data["epoch"]
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
        self.arrival = (None, None)  # (node left, option taken) for the last decision
        self.done = [name for name, _, reached in OBJECTIVES if reached(pyboy)]

    def objective(self):
        for name, hint, reached in OBJECTIVES:
            if not reached(self.pyboy):
                return name, hint
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
        candidates = sorted(fresh or usable, key=lambda option: len(option.route))[:8]
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
        key, laya = self.policy.choose(context, {key: option.description for key, option in keys.items()})
        return keys[key], "laya", {**details, "laya": laya}

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
        name, hint = self.objective()
        started = time.perf_counter()
        options = self.surveyor.options(self.pyboy)
        node = node_of(obs.room, options)
        if not self.memory.fresh(node, options) and node not in self.memory.current["fine"]:
            # Once per area: a finer grid finds narrow gaps the first pass can miss.
            self.memory.current["fine"].append(node)
            options = self.surveyor.options(self.pyboy, grid=4, limit=1500) or options
            node = node_of(obs.room, options)
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
        self.memory.arrive(node, options, *self.arrival)
        self.arrival = (None, None)
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
        elif after.room != obs.room:
            outcome = f"moved to room {after.room}"
        elif self.pyboy.memory[HEALTH] < health:
            outcome = "took damage"
        if outcome != "failed, option dropped":
            self.arrival = (node, option.id)
        self.recent.append(f"{option.description} -> {outcome}")
        reached = [item for item, _, check in OBJECTIVES if check(self.pyboy) and item not in self.done]
        self.done.extend(reached)
        self.write({
            "decision": self.decisions, "objective": name, "room": obs.room, "xy": [obs.x, obs.y],
            "options": [item.id for item in options], "choice": option.id, "description": option.description,
            "origin": origin, "outcome": outcome, "after_room": after.room, "inputs": len(option.route),
            "survey_s": round(survey_seconds, 2), "choice_ms": round(choice_seconds * 1000, 1),
            "node": node, "tries_here": self.memory.tries(node, option.id), "reached": reached, **details,
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
            "scenes_waited": self.scenes,
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
                reason = "orçamento de decisões"
                started = time.perf_counter()
                try:
                    while agent.decisions < args.decisions:
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
        paths.atomic_write(memory_path, json.dumps(agent.memory.dump()).encode("utf-8"))


if __name__ == "__main__":
    main()
