"""The agent: Laya presses one button at a time and the supervisor says what to do.

The models decide and the code only reads the game and presses what was chosen:

- the supervisor (a local LLM) reads the state as text, with a character map of the
  screen, and writes the goal of the moment in a few words;
- Laya reads that goal and picks one input: up, down, left, right, A or B;
- nothing is simulated ahead, no option is listed, no puzzle is solved and no loop is cut.

  python -m zelda_env.player --headless --steps 600 --until espada

zelda_env.agent is the baseline this is compared with: there the code simulates the room
and hands Laya ready-made choices.
"""

import argparse
import json
import platform
import re
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


_TEXTS = None


def game_text(index):
    """What a text box says, by the game's own text number.

    The words come from the text table of the disassembly that the ROM was built from, when
    that checkout is on this machine. Without it the supervisor is not told the words.
    """
    global _TEXTS
    if _TEXTS is None:
        _TEXTS = {}
        try:
            import yaml

            source = next(paths.cache_path("rom-build").glob("**/text/ages/text.yaml"))
            for group in yaml.safe_load(source.read_text(encoding="utf-8"))["groups"]:
                for entry in group.get("data", ()):
                    numbers = entry.get("index", ())
                    words = " ".join(re.sub(r"\\[a-zA-Z]+(\([^)]*\))?", " ", str(entry.get("text", ""))).split())
                    for number in numbers if isinstance(numbers, list) else [numbers]:
                        _TEXTS[(group["group"] << 8) | number] = words[:220]
        except (ImportError, StopIteration, OSError, ValueError, KeyError, TypeError):
            pass
    return _TEXTS.get(index)


MEMORY_RULES = (
    " You have a memory. 'Journal' lists your last goals and what each one did. 'Tried on this screen' is kept "
    "even after Link leaves and comes back. 'Your note' is what you wrote to yourself last time. Use them: do not "
    "give again a goal that did nothing or that took Link back and forth. In the answer, add a 'note' of at most "
    "twenty words with what you learned and what to try next."
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
        self.note = None  # what the supervisor last wrote to itself

    def goal(self, state, memory=False):
        """The goal and the reason. With `memory`, the supervisor also writes a note to itself,
        kept in `self.note` and shown to it on the next call."""
        schema = {"type": "object", "properties": {"goal": {"type": "string"}, "reason": {"type": "string"}},
                  "required": ["goal"]}
        if memory:
            schema["properties"]["note"] = {"type": "string"}
        user = "\n".join(f"{key}:\n{value}" if "\n" in str(value) else f"{key}: {value}"
                         for key, value in state.items())
        started = time.perf_counter()
        self.stats["calls"] += 1
        try:
            reply = self.backend._post("/api/chat", {
                "model": self.backend.model, "stream": False, "format": schema, "keep_alive": "30m",
                "options": {"temperature": 0, "num_predict": 120},
                "messages": [{"role": "system", "content": SYSTEM + (MEMORY_RULES if memory else "")},
                             {"role": "user", "content": user}],
            }, self.timeout)
            data = json.loads(reply.get("message", {}).get("content", ""))
            goal = " ".join(str(data["goal"]).split())[:120]
            reason = str(data.get("reason", ""))[:200]
            if memory and data.get("note"):
                self.note = " ".join(str(data["note"]).split())[:200]
        except (OSError, ValueError, KeyError, TypeError):
            self.stats["failed"] += 1
            goal, reason = None, None
        self.stats["seconds"] += time.perf_counter() - started
        return goal, reason


class Player:
    def __init__(self, pyboy, policy, planner, *, objectives, watch=False, log=None, history=False):
        self.pyboy, self.policy, self.planner = pyboy, policy, planner
        # With the screen history in the state, the 4B supervisor did worse in the first
        # measurement (it paced left and right on one screen), so it is off unless asked for.
        self.history = history
        self.objectives, self.watch, self.log = objectives, watch, log
        self.steps = 0
        self.goal, self.reason, self.goal_age = None, None, PLAN_EVERY
        self.recent = deque(maxlen=8)
        self.still = 0  # inputs in a row with no effect; told to the supervisor as it is
        self.failed_goals = deque(maxlen=4)  # goals that changed nothing on this screen
        # What the supervisor is told about where Link has been. It is history, not a plan.
        self.visits, self.leaves, self.path = {}, {}, deque(maxlen=8)
        self.said, self.text_index = deque(maxlen=3), None  # what the game's text boxes said lately
        # The supervisor's memory: its last goals with what each did, the same per screen, and
        # the note it writes to itself. Everything in it comes from the supervisor's own goals.
        self.journal, self.by_screen, self.tally = deque(maxlen=6), {}, None
        self.memory, self.texts = False, False
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
            **({"times link has been on this screen": self.visits.get(seen.room, 0) + 1,
                "how link left this screen before": ", ".join(
                    f"{side} {count}x" for side, count in sorted(self.leaves.get(seen.room, {}).items()))
                or "never left it",
                "screens visited lately": " > ".join(self.path) or "only this one"} if self.history else {}),
            **({"what the game said lately": " / ".join(self.said) or "nothing yet"} if self.texts else {}),
            **({"journal": "\n".join(self.journal) or "empty",
                "tried on this screen": "\n".join(self.by_screen.get(seen.room, ())) or "nothing yet",
                "your note": (self.planner.note if self.planner else None) or "none"} if self.memory else {}),
            "map": screen_map(self.pyboy) or "no map (a scene or a menu)",
        }
        self.close_goal(seen.room)
        goal, reason = self.planner.goal(state, self.memory) if self.planner else (None, None)
        self.tally = {"room": seen.room, "events": {}}
        self.goal = goal or self.goal or "Explore: walk to a part of the screen you have not been to."
        self.reason, self.goal_age = reason, 0
        self.write({"event": "goal", "step": self.steps, "room": seen.room, "goal": self.goal, "reason": reason,
                    "from_supervisor": bool(goal)})

    def close_goal(self, room):
        """Write down what the goal that just ended did, for the journal."""
        if not self.tally or not self.goal:
            return
        did = ", ".join(f"{event} {count}x" for event, count in sorted(self.tally["events"].items())) or "nothing"
        where = "" if self.tally["room"] == room else f", ended on screen {room}"
        line = f"'{self.goal}' on screen {self.tally['room']}: {did}{where}"
        self.journal.append(line)
        tried = self.by_screen.setdefault(self.tally["room"], deque(maxlen=5))
        tried.append(f"'{self.goal}': {did}{where}")

    def step(self):
        seen = observe(self.pyboy)
        name = self.objective()
        if seen.mode == "dialogue":
            # The player reads the text on screen. The supervisor gets the same words.
            index = (self.pyboy.memory[0xCBA3] << 8) | self.pyboy.memory[0xCBA2]
            if index != self.text_index:
                self.text_index = index
                words = game_text(index) if self.texts else None
                if words and words not in self.said:
                    self.said.append(words)
        # The text box takes a press when a page is full, and in the states where it waits
        # for one before going on. In between it is writing and ignores the buttons.
        writing = (seen.mode == "dialogue" and not seen.dialogue_ready
                   and self.pyboy.memory[7, 0xD0C0] not in (2, 4, 10))
        if writing or (seen.mode in ("transition", "unknown", "locked", "menu") and not seen.dialogue_ready):
            # Nothing to choose while the game has the controls or the text is still being
            # written: a button pressed now does nothing, so it is not counted as an input.
            execute(self.pyboy, "wait", render=self.watch)
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
        if self.tally:
            self.tally["events"][event] = self.tally["events"].get(event, 0) + 1
        if after.room != seen.room and seen.room and after.room:
            self.goal_age = PLAN_EVERY  # a new screen needs a new goal
            self.failed_goals.clear()
            self.visits[seen.room] = self.visits.get(seen.room, 0) + 1
            side = {"up": "north", "down": "south", "left": "west", "right": "east"}.get(key, "door or stairs")
            self.leaves.setdefault(seen.room, {})[side] = self.leaves.get(seen.room, {}).get(side, 0) + 1
            self.path.append(seen.room)
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
    parser.add_argument("--directory", type=Path, help="Sessão (estado, trace). Padrão: output/player")
    parser.add_argument("--steps", type=int, default=400, help="Orçamento de inputs desta execução")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--supervisor", metavar="MODELO", default=DEFAULT_SUPERVISOR)
    parser.add_argument("--no-supervisor", action="store_true", help="Sem metas do supervisor (comparação)")
    parser.add_argument("--memory", action="store_true",
                        help="Memória do supervisor: diário das últimas metas, o que foi tentado em cada tela "
                             "e a nota que ele escreve para si mesmo")
    parser.add_argument("--texts", action="store_true",
                        help="Passa ao supervisor as falas que o jogo mostrou")
    parser.add_argument("--history", action="store_true",
                        help="Inclui no texto do supervisor as telas visitadas e por onde Link saiu de cada uma")
    parser.add_argument("--until", metavar="OBJETIVO", choices=[item[0] for item in OBJECTIVES])
    parser.add_argument("--until-room", metavar="SALA")
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    args = resolve_common(parser, parser.parse_args())
    start = args.seed_state or paths.output_path("inicio.state")
    directory = args.directory or paths.output_path("player")
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
            agent = Player(pyboy, policy, planner, objectives=OBJECTIVES, watch=not args.headless, log=log,
                               history=args.history)
            agent.memory, agent.texts = args.memory, args.texts
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
                      "agent": "player", "rom_sha1": paths.AGES_SHA1, "pyboy": version("pyboy"),
                      "python": platform.python_version(), "model": policy.model,
                      "supervisor": getattr(planner.backend, "name", None) if planner else None}
            paths.atomic_write(directory / "summary.json",
                               (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
            print(json.dumps(report, indent=2, ensure_ascii=False))
    finally:
        pyboy.stop(save=False)


if __name__ == "__main__":
    main()
