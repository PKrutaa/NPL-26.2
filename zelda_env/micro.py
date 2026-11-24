"""Micro mode: Laya presses one button at a time and the supervisor says what to do.

The options agent (zelda_env.agent) finds out what can be done in a room by simulating
it, and hands Laya ready-made choices. That measures the code more than the models. Here
the code only reads the game and presses what was chosen:

- the supervisor (a local LLM) reads the state as text, with a character map of the
  screen, and writes the goal of the moment in a few words;
- Laya reads that goal and picks one input: up, down, left, right, A or B;
- nothing is simulated ahead, no option is listed, no puzzle is solved and no loop is cut.

  python -m zelda_env.micro --headless --steps 600 --until espada
"""

import argparse
import json
import platform
import time
from collections import deque
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

from . import paths, puzzle
from .__main__ import add_common, resolve_common
from .adapter import enemies, execute, health, observe
from .supervisor import OllamaBackend, SupervisorUnavailable

STEP_FRAMES = 16  # one walking input moves Link about one tile
PLAN_EVERY = 8  # inputs between two goals from the supervisor
STUCK_AFTER = 4  # inputs with Link in the same place before the supervisor is asked again
BUTTONS = {
    "up": "Walk up", "down": "Walk down", "left": "Walk left", "right": "Walk right",
    "a": "Press A: use the A item, talk, read, open, or continue the text",
    "b": "Press B: use the B item (the sword when Link has it)",
}
# What each objective asks for, in the words a player would use. No rooms and no routes.
WHAT_FOR = {
    "espada": "Follow the story at the start of the game until Link has the wooden sword.",
    "maku-tree": "Reach the Maku Tree in Lynna City, in the present.",
    "passado": "Go through the time portal to the past.",
    "pa": "Get the shovel in the past.",
    "maku-tree-salva": "Save the Maku Tree in the past.",
    "sacola-de-sementes": "Go back to the present and get the Seed Satchel from the Maku Tree.",
    "chave-do-cemiterio": "Burn the sapling east of Lynna City with an ember seed and get the Graveyard Key in the graveyard.",
    "dungeon-1": "Open the graveyard gate with the key and enter the first dungeon, Spirit's Grave.",
    "essencia-1": "Finish Spirit's Grave: small keys, the mini-boss, the Power Bracelet, the boss, the essence.",
    "oito-essencias": "Collect the eight essences.",
}
SYSTEM = (
    "You guide a player of The Legend of Zelda: Oracle of Ages on the Game Boy Color. The player can only press "
    "one button at a time: up, down, left, right, A or B. You do not press buttons. You read the state and write "
    "the next small goal for the player, in at most twelve words. The goal must start with one of: 'Walk up', "
    "'Walk down', 'Walk left', 'Walk right', 'Press A', 'Press B', followed by what it is for. "
    "Columns are counted from the left starting at 0, rows from the top starting at 0. "
    "The map shows the screen: @ is Link, # is a wall or solid thing, . is floor, o is a hole, s is stairs, "
    "B is a block that can be pushed, C is a chest, b is a floor button, E is an enemy, N is a character or "
    "object. North is the top row, west is the left column. Link leaves a screen by walking off its edge where "
    "the edge is floor. To talk to a character, walk next to it, face it and press A. "
    "When the state says there is no text on screen, pressing A reads nothing. "
    "A goal listed as having changed nothing must not be given again: choose another direction or button. "
    "Prefer walking toward a part of the map Link has not reached, or toward a character, when unsure. "
    'Answer with JSON only: {"goal": "<instruction>", "reason": "<short reason>"}.'
)


def screen_map(pyboy):
    """The room as rows of characters, read from the game's memory. Nothing is simulated."""
    memory, seen = pyboy.memory, observe(pyboy)
    if seen.room is None:
        return None
    width, height = (15, 11) if memory[0xCD01] != 1 else (10, 8)
    # The block, chest and button tiles below are the ones of dungeons and interiors. On the
    # overworld the same numbers are trees and grass.
    indoors = memory[0xCC33] in (1, 2, 5)
    rows = []
    for y in range(height):
        row = []
        for x in range(width):
            tile, solid = memory[0xCF00 + y * 16 + x], memory[0xCE00 + y * 16 + x]
            special = ("B" if tile in puzzle.BLOCKS else "C" if tile == puzzle.CHEST else
                       "b" if tile == puzzle.BUTTON else None) if indoors else None
            row.append(special or ("." if solid == 0 else "s" if solid == 0x18 else "o" if solid == 0x10 else "#"))
        rows.append(row)

    def put(x, y, mark):
        if 0 <= y // 16 < height and 0 <= x // 16 < width:
            rows[y // 16][x // 16] = mark

    for item in seen.entities:
        put(item["x"], item["y"], "N")
    for item in enemies(pyboy):
        put(item["x"], item["y"], "E")
    put(seen.x, seen.y, "@")
    return "\n".join("".join(row) for row in rows)


def open_edges(pyboy):
    """Where the screen can be left: the sides whose border has floor, with the columns or rows."""
    lines = (screen_map(pyboy) or "").split("\n")
    if not lines[0]:
        return "unknown"
    walk = ".s@N"
    sides = {
        "north": [x for x, mark in enumerate(lines[0]) if mark in walk],
        "south": [x for x, mark in enumerate(lines[-1]) if mark in walk],
        "west": [y for y, line in enumerate(lines) if line[0] in walk],
        "east": [y for y, line in enumerate(lines) if line[-1] in walk],
    }
    parts = [f"{side} (at {'columns' if side in ('north', 'south') else 'rows'} {', '.join(map(str, cells))})"
             for side, cells in sides.items() if cells]
    return "; ".join(parts) or "none: this screen is left through a door or stairs"


def around(pyboy):
    """What is next to Link in each direction, from the same map."""
    seen, lines = observe(pyboy), (screen_map(pyboy) or "").split("\n")
    if seen.room is None or not lines[0]:
        return {}
    x, y = seen.x // 16, seen.y // 16
    names = {"#": "wall", ".": "floor", "o": "hole", "s": "stairs", "B": "block", "C": "chest", "b": "button",
             "E": "enemy", "N": "character", "@": "floor"}
    result = {}
    for name, (dx, dy) in puzzle.STEP.items():
        nx, ny = x + dx, y + dy
        inside = 0 <= ny < len(lines) and 0 <= nx < len(lines[0])
        result[name] = names[lines[ny][nx]] if inside else "edge of the screen"
    return result


class Planner:
    """Asks the supervisor for the goal of the moment. Never raises."""

    def __init__(self, backend, timeout=30.0):
        self.backend, self.timeout = backend, timeout
        self.stats = {"calls": 0, "failed": 0, "seconds": 0.0}

    def goal(self, state):
        schema = {"type": "object", "properties": {"goal": {"type": "string"}, "reason": {"type": "string"}},
                  "required": ["goal"]}
        user = "\n".join(f"{key}:\n{value}" if "\n" in str(value) else f"{key}: {value}"
                         for key, value in state.items())
        started = time.perf_counter()
        self.stats["calls"] += 1
        try:
            reply = self.backend._post("/api/chat", {
                "model": self.backend.model, "stream": False, "format": schema, "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 120},
                "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            }, self.timeout)
            data = json.loads(reply.get("message", {}).get("content", ""))
            goal = " ".join(str(data["goal"]).split())[:120]
            reason = str(data.get("reason", ""))[:200]
        except (OSError, ValueError, KeyError, TypeError):
            self.stats["failed"] += 1
            goal, reason = None, None
        self.stats["seconds"] += time.perf_counter() - started
        return goal, reason


class MicroAgent:
    def __init__(self, pyboy, policy, planner, *, objectives, watch=False, log=None):
        self.pyboy, self.policy, self.planner = pyboy, policy, planner
        self.objectives, self.watch, self.log = objectives, watch, log
        self.steps = 0
        self.goal, self.reason, self.goal_age = None, None, PLAN_EVERY
        self.recent = deque(maxlen=8)
        self.still = 0  # inputs in a row with no effect; told to the supervisor as it is
        self.failed_goals = deque(maxlen=4)  # goals that changed nothing on this screen
        self.done = [item[0] for item in objectives if item[3](pyboy)]
        self.inputs = {}

    def objective(self):
        return next((item[0] for item in self.objectives if not item[3](self.pyboy)), None)

    def write(self, record):
        if self.log:
            self.log.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.log.flush()

    def plan(self, seen, name):
        """A new goal when the old one is used up, Link is stuck, or the screen changed."""
        hearts = health(self.pyboy)
        state = {
            "objective": WHAT_FOR.get(name, name or "explore"),
            "text on screen": "yes, press A to continue it" if seen.mode == "dialogue" else "no",
            "link can walk": "yes" if seen.mode == "playing" else "no",
            "room": seen.room,
            "link": f"x={seen.x} y={seen.y} facing {seen.facing}" if seen.room else "not on screen",
            "health": f"{hearts[0] / 4:g} of {hearts[1] / 4:g} hearts",
            "link is at": f"column {seen.x // 16}, row {seen.y // 16} of the map" if seen.room else "unknown",
            "next to link": ", ".join(f"{side}: {what}" for side, what in around(self.pyboy).items()) or "unknown",
            "sides where the screen can be left": open_edges(self.pyboy),
            "inputs in a row that did not move link": self.still,
            "last inputs": "; ".join(self.recent) or "none yet",
            "last goal": self.goal or "none",
            "goals that changed nothing on this screen": "; ".join(self.failed_goals) or "none",
            "map": screen_map(self.pyboy) or "no map (a scene or a menu)",
        }
        goal, reason = self.planner.goal(state) if self.planner else (None, None)
        self.goal = goal or self.goal or "Explore: walk to a part of the screen you have not been to."
        self.reason, self.goal_age = reason, 0
        self.write({"event": "goal", "step": self.steps, "room": seen.room, "goal": self.goal, "reason": reason,
                    "from_supervisor": bool(goal)})

    def step(self):
        seen = observe(self.pyboy)
        name = self.objective()
        if seen.mode in ("transition", "unknown", "locked", "menu") and not seen.dialogue_ready:
            execute(self.pyboy, "wait", render=self.watch)  # nothing to choose while the game has the controls
            return
        stuck = self.still and self.still % STUCK_AFTER == 0
        if self.goal is None or self.goal_age >= PLAN_EVERY or stuck:
            if stuck and self.goal and self.goal not in self.failed_goals:
                self.failed_goals.append(self.goal)
            self.plan(seen, name)
        if seen.mode == "dialogue":
            choices = {"a": "Press A: continue the text or confirm", "b": "Press B: cancel"}
        else:
            choices = BUTTONS
        sides = around(self.pyboy)
        context = {"goal": self.goal}
        if seen.mode == "playing" and sides:
            context["facing"] = seen.facing
            context["next to link"] = ", ".join(f"{side}: {what}" for side, what in sides.items())
        key, details = self.policy.choose(context, choices)
        action = {"a": "interact" if seen.mode == "dialogue" else "use_a",
                  "b": "cancel" if seen.mode == "dialogue" else "use_b"}.get(key, key)
        before = (seen.room, seen.x, seen.y)
        after, event, _ = execute(self.pyboy, action, render=self.watch,
                                  hold_frames=STEP_FRAMES if key in puzzle.STEP else 12)
        moved = (after.room, after.x, after.y) != before or event not in ("blocked", "no_change")
        self.still = 0 if moved else self.still + 1
        self.steps += 1
        self.goal_age += 1
        self.inputs[key] = self.inputs.get(key, 0) + 1
        self.recent.append(f"{key} -> {event}")
        if after.room != seen.room:
            self.goal_age = PLAN_EVERY  # a new screen needs a new goal
            self.failed_goals.clear()
        reached = [item[0] for item in self.objectives if item[3](self.pyboy) and item[0] not in self.done]
        self.done.extend(reached)
        answer = details.get("answer") if isinstance(details, dict) else None
        hearts = health(self.pyboy)
        # Field names match the options agent, so the same metrics and reports read both.
        self.write({
            "decision": self.steps, "objective": name, "room": seen.room, "xy": [seen.x, seen.y],
            "node": f"{seen.room}@{(seen.x or 0) // 16}:{(seen.y or 0) // 16}", "goal": self.goal,
            "options": list(choices), "choice": key, "origin": "laya", "outcome": event, "after_room": after.room,
            "confidence": (answer or {}).get("answer_confidence"), "survey_s": 0.0, "reached": reached,
            "health": [hearts[0], hearts[1]],
        })
        if self.watch:
            print(f"{self.steps}: [{self.goal}] {key} → {event}", flush=True)

    def summary(self):
        seen = observe(self.pyboy)
        return {"steps": self.steps, "objectives_reached": self.done, "room": seen.room, "inputs": self.inputs,
                "planner": self.planner.stats if self.planner else None, "health": list(health(self.pyboy))}


def main():
    from .agent import DEFAULT_SUPERVISOR, OBJECTIVES

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_common(parser)
    parser.add_argument("--seed-state", type=Path, help="Ponto de partida. Padrão: output/inicio.state")
    parser.add_argument("--directory", type=Path, help="Sessão (estado, trace). Padrão: output/micro")
    parser.add_argument("--steps", type=int, default=400, help="Orçamento de inputs desta execução")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--supervisor", metavar="MODELO", default=DEFAULT_SUPERVISOR)
    parser.add_argument("--no-supervisor", action="store_true", help="Sem metas do supervisor (comparação)")
    parser.add_argument("--until", metavar="OBJETIVO", choices=[item[0] for item in OBJECTIVES])
    parser.add_argument("--until-room", metavar="SALA")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    args = resolve_common(parser, parser.parse_args())
    start = args.seed_state or paths.output_path("inicio.state")
    directory = args.directory or paths.output_path("micro")
    if not start.is_file():
        parser.exit(1, f"Seed ausente: {start}. Gere com: {paths.venv_python()} -m zelda_env seed\n")
    planner = None
    if not args.no_supervisor:
        backend = OllamaBackend(args.supervisor)
        try:
            backend.check()
            backend.warm()
            planner = Planner(backend)
            print(f"Supervisor ligado: {backend.name}", flush=True)
        except SupervisorUnavailable as error:
            print(f"Supervisor desligado: {error}", flush=True)

    from pyboy import PyBoy

    from .laya_policy import LayaPolicy

    policy = LayaPolicy(args.device, "text", False)
    pyboy = PyBoy(str(args.rom), window="null" if args.headless else "SDL2",
                  ram_file=BytesIO(bytes(paths.SRAM_BYTES)), sound_volume=0)
    pyboy.set_emulation_speed(0 if args.headless else 2)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        with start.open("rb") as stream:
            pyboy.load_state(stream)
        print(f"Sessão iniciada de {start}", flush=True)
        with (directory / "trace.jsonl").open("w", encoding="utf-8") as log:
            agent = MicroAgent(pyboy, policy, planner, objectives=OBJECTIVES, watch=not args.headless, log=log)
            reason, started = "orçamento de inputs", time.perf_counter()
            guard = 0
            try:
                while agent.steps < args.steps and guard < args.steps * 40:
                    guard += 1
                    reached = len(agent.done)
                    agent.step()
                    for name in agent.done[reached:]:
                        print(f"Objetivo concluído: {name}", flush=True)
                    if args.until in agent.done:
                        reason = "objetivo concluído"
                        break
                    if args.until_room and observe(pyboy).room == args.until_room:
                        reason = "sala alcançada"
                        break
            except (InterruptedError, KeyboardInterrupt):
                reason = "interrompido"
            stream = BytesIO()
            pyboy.save_state(stream)
            paths.atomic_write(directory / "latest.state", stream.getvalue())
            report = {**agent.summary(), "stopped": reason, "seconds": round(time.perf_counter() - started, 1),
                      "mode": "micro", "rom_sha1": paths.AGES_SHA1, "pyboy": version("pyboy"),
                      "python": platform.python_version(), "model": policy.model,
                      "supervisor": getattr(planner.backend, "name", None) if planner else None}
            paths.atomic_write(directory / "summary.json",
                               (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
