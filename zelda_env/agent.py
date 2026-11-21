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
from collections import Counter, deque
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

from . import paths
from .__main__ import add_common, resolve_common
from .adapter import enemies, execute, observe, room_layout, show_status
from .survey import ESSENCES, HEALTH, OVERWORLD, Surveyor, progress, run_route

GLOBAL_FLAGS = 0xC6D0
TREASURES = 0xC69A
TEXT_DISPLAY_STATE = (7, 0xD0C0)
MEMORY_FORMAT = 6
TALKS_PER_CHARACTER = 3
TOOL_USES_PER_AREA = 10
GOAL_REUSES = 2  # times a known exit toward the goal is offered again per story state
TASK_REDOS = 30  # decisions per area and story state that may redo what the task asks
ROOM_REVISITS = 8  # times per story state a dungeon room's actions become available again
LONG_WINDOW, LONG_REPEATS = 80, 6  # one move made this many times within that many decisions
LOOP_WINDOW, LOOP_MOVES = 12, 4  # that many decisions made of at most this many distinct moves
RECIPE_STEPS = 12
SWEEP_LIMIT = 80  # sweep decisions without story progress before declaring an impasse
MAX_HOPS = 14  # consecutive trips to a pending area with nothing new found
SURVEY_LEVELS = (
    {"grid": 16, "stride": 16, "limit": 400, "pushes": False},
    {"grid": 8, "stride": 12, "limit": 700},
    {"grid": 4, "stride": 12, "limit": 1500},
)


def _flag(base, index):
    return lambda pyboy: bool(pyboy.memory[base + index // 8] & (1 << index % 8))


ROOM_VISITED = 0x10
DUNGEON_INDEX = 0xCC39  # 0xFF outside a mapped area
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
     _flag(GLOBAL_FLAGS, 0x12), 0x0D),
    ("chave-do-cemiterio", (("01:39", "Walk into the event."), ("00:38", "Talk to the character."),
                            ("00:7c", "Enter the door or stairs.")),
     "Enter the door or stairs.", _flag(TREASURES, 0x42)),
    ("dungeon-1", (("00:8d", "Enter the door or stairs."),), "Enter the door or stairs.",
     lambda pyboy: bool(pyboy.memory[GROUP4_ROOM_FLAGS + 0x24] & ROOM_VISITED)),
    ("essencia-1", (), "Go to a new room.", lambda pyboy: bool(pyboy.memory[ESSENCES] & 1), 0x01),
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
        self.areas = {}  # room -> exit sets of its separate parts
        self.opened = {}  # "area|option" -> exits that appeared after taking it
        self.dungeons = {}  # room -> dungeon index read when Link was there (255 outside one)
        self.recipes = {}  # "room|entered from|exit" -> what was done in the room to cross it
        self.last_seen = {}  # room -> decision count when Link was last there
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
            self.epochs[key] = {"tried": kept, "visited": [], "pending": {}, "depth": {}, "reused": {}}
        self.current = self.epochs[key]
        return changed

    def area(self, room, options):
        """A stable name for the part of a room Link is in.

        Parts of a room that do not connect have different exits. Two surveys of the same
        part can find more or fewer of its exits, so sets that share an exit are one area.
        A survey that links two known areas (a block was pushed aside) joins them.
        """
        exits = {option.destination for option in options if option.kind == "exit"}
        known = self.areas.setdefault(room, [])
        matches = [index for index, seen in enumerate(known)
                   if seen is not None and (set(seen) & exits or (not seen and not exits))]
        if not matches:
            known.append(sorted(exits))
            return f"{room}@{len(known) - 1}"
        keep = matches[0]
        for index in matches[1:]:
            exits |= set(known[index])
            known[index] = None
            self._join(f"{room}@{index}", f"{room}@{keep}")
        known[keep] = sorted(set(known[keep]) | exits)
        return f"{room}@{keep}"

    def _join(self, old, new):
        """Move everything recorded under one area name to another."""
        for epoch in self.epochs.values():
            for key in [key for key in epoch["tried"] if key.startswith(f"{old}|")]:
                target = f"{new}|{key.split('|', 1)[1]}"
                epoch["tried"][target] = epoch["tried"].get(target, 0) + epoch["tried"].pop(key)
            epoch["pending"].pop(old, None)
            epoch["visited"] = list(dict.fromkeys(new if name == old else name for name in epoch["visited"]))
        self.edges.setdefault(new, {}).update(self.edges.pop(old, {}))
        for links in self.edges.values():
            for option_id, destination in links.items():
                if destination == old:
                    links[option_id] = new
        for key in [key for key in self.opened if key.startswith(f"{old}|")]:
            self.opened[f"{new}|{key.split('|', 1)[1]}"] = self.opened.pop(key)
        self.banned = {(new if node == old else node, option_id) for node, option_id in self.banned}

    def unlocked(self, node, option_id, exits):
        """Remember that an option made these exits appear (a block pushed out of the way)."""
        self.opened[f"{node}|{option_id}"] = sorted(set(self.opened.get(f"{node}|{option_id}", [])) | set(exits))

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
            return name.startswith("item:") or (name.startswith("interact:") and ":event" in name)

        # A tool can act on every tile of a room. After enough tries in one area with no
        # progress, more of the same is not something new.
        worn = sum(count for key, count in self.current["tried"].items()
                   if key.startswith(f"{node}|") and tool_use(key.split("|", 1)[1])) >= TOOL_USES_PER_AREA

        offered = {option.id for option in options}

        def reopens(option):
            # Some rooms reset when Link leaves. What opened a way before is worth doing
            # again whenever that way is closed.
            if f"{node}|{option.id}" in self.current.get("stale", []):
                return False  # it was part of a loop: no longer something to redo
            ways = self.opened.get(f"{node}|{option.id}")
            return bool(ways) and not set(ways) <= offered

        return [option for option in options
                if (node, option.id) not in self.banned and (reopens(option) or (
                    not self.tries(node, option.id) and not chatty(option)
                    and not (worn and tool_use(option.id))))]

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

    def revisit(self, node):
        """Rooms of a dungeon reset when Link leaves. On coming back, what was done in the
        room counts as not done, a limited number of times per story state."""
        visits = self.current.setdefault("visits", {})
        visits[node] = visits.get(node, 0) + 1
        if visits[node] > ROOM_REVISITS:
            return
        for key in [key for key in self.current["tried"]
                    if key.startswith(f"{node}|") and not key.split("|", 1)[1].startswith("exit:")
                    and key not in self.current.get("stale", [])]:
            del self.current["tried"][key]

    def record(self, node, option_id):
        key = f"{node}|{option_id}"
        self.current["tried"][key] = self.current["tried"].get(key, 0) + 1
        pending = self.current["pending"].get(node, [])
        if option_id in pending:
            pending.remove(option_id)

    def hop(self, node, options, allowed=None, leaving=False, to=None):
        """First step of the shortest known path to somewhere worth going.

        By default that is an area with untried options, limited to rooms that pass
        `allowed`. With `leaving`, it is any area that has a known exit to the overworld.
        With `to`, it is that room.
        """
        available = {option.id for option in options if (node, option.id) not in self.banned}
        queue = deque((destination, option_id) for option_id, destination in self.edges.get(node, {}).items()
                      if option_id in available and destination != node)
        seen = {node}
        while queue:
            current, first = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            room = current.split("@")[0]
            if to:
                if room == to:
                    return first
            elif leaving:
                if room[:2] in OVERWORLD:
                    return first
            elif self.current["pending"].get(current) and (allowed is None or allowed(room)):
                return first
            queue.extend((destination, first) for destination in self.edges.get(current, {}).values())
        return None

    def learn(self, room, entered_from, exit_id, steps):
        """Remember what was done in a room between coming in one way and leaving another.
        Dungeon rooms reset, so crossing them again means doing the same things again."""
        key = f"{room}|{entered_from}|{exit_id}"
        steps = [step for step in steps if not step.startswith("exit:")][-RECIPE_STEPS:]
        if key not in self.recipes or len(steps) < len(self.recipes[key]):
            self.recipes[key] = steps

    def recipe(self, room, entered_from, exit_id):
        exact = self.recipes.get(f"{room}|{entered_from}|{exit_id}")
        if exact is not None:
            return exact
        others = [steps for key, steps in self.recipes.items()
                  if key.startswith(f"{room}|") and key.endswith(f"|{exit_id}")]
        return min(others, key=len) if others else None

    def room_hop(self, room, wanted):
        """First exit of the shortest path, room by room, to a room that `wanted` accepts.
        It uses every exit ever seen in a room, whether or not it is open right now."""
        links = {}
        for node, exits in self.edges.items():
            for option_id, destination in exits.items():
                if option_id.startswith("exit:"):
                    links.setdefault(node.split("@")[0], {})[option_id] = destination.split("@")[0]
        queue = deque((destination, option_id) for option_id, destination in links.get(room, {}).items())
        seen = {room}
        while queue:
            current, first = queue.popleft()
            if current in seen:
                continue
            seen.add(current)
            if wanted(current):
                return first
            queue.extend((destination, first) for destination in links.get(current, {}).values())
        return None

    def dump(self):
        return {"format": MEMORY_FORMAT, "epochs": self.epochs, "edges": self.edges,
                "banned": sorted(map(list, self.banned)), "epoch": self.epoch, "landmarks": self.landmarks,
                "decisions": self.decisions, "areas": self.areas, "opened": self.opened,
                "dungeons": self.dungeons, "recipes": self.recipes,
                "last_seen": self.last_seen}

    @classmethod
    def load(cls, data):
        if data.get("format") != MEMORY_FORMAT:
            raise ValueError(f"Formato de memória incompatível: {data.get('format')}")
        memory = cls()
        memory.epochs, memory.edges = data["epochs"], data["edges"]
        for epoch in memory.epochs.values():
            epoch["depth"] = {}  # only a cache of how closely each area was examined
        memory.banned = {tuple(item) for item in data["banned"]}
        memory.epoch = data["epoch"]
        memory.landmarks = data.get("landmarks", {})
        memory.decisions = data.get("decisions", 0)
        memory.areas = data.get("areas", {})
        memory.opened = data.get("opened", {})
        memory.dungeons = data.get("dungeons", {})
        memory.recipes = data.get("recipes", {})
        memory.last_seen = data.get("last_seen", {})
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
        self.last = None
        self.hops = 0
        self.trail = []
        self.undo = None
        self.sweeps = 0
        self.entered_from = "start"  # the room Link was in before this one
        self.here = None
        self.done_here = []  # what was done in this room since coming in
        self.loops = 0
        self.damage = 0
        self.arrival = (None, None)  # (node left, option taken) for the last decision
        self.done = [item[0] for item in OBJECTIVES if item[3](pyboy)]

    def objective(self, room=None):
        """Current objective and a short goal: a direction to the next landmark, or what to do."""
        self.target = None
        for name, steps, elsewhere, reached, *where in OBJECTIVES:
            if reached(self.pyboy):
                continue
            # An objective can name its dungeon. In any other interior, the goal is to leave.
            self.focus = where[0] if where else None
            if where and room and room[:2] not in OVERWORLD and self.pyboy.memory[DUNGEON_INDEX] != where[0]:
                elsewhere = "Go outside."
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
                self.target = target if where else None
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
                # With an enemy on screen, standing still is how Link gets hit: decide sooner.
                calm = 2 if enemies(self.pyboy) else 8
                if quiet > calm and (self.surveyor.can_move(self.pyboy) or quiet > 120):
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
        seen = {name.split("@")[0] for name in self.memory.current["visited"]}
        focus = getattr(self, "focus", None)
        if focus is not None:
            def into_focus(option):
                return option.kind == "exit" and self.memory.dungeons.get(option.destination) == focus

            if self.pyboy.memory[DUNGEON_INDEX] == focus:
                # The objective is in this dungeon. Leaving it is not a candidate while
                # anything else can be done here.
                # Going back out the way Link came in is what this prevents. An exit to an
                # overworld room he has never been to is the way forward, and stays.
                stay = [option for option in usable
                        if not (option.kind == "exit" and option.destination[:2] in OVERWORLD
                                and option.destination in self.memory.dungeons)]
                if stay:
                    usable, fresh = stay, [option for option in fresh if option in stay]
            else:
                # A known way into the dungeon of the objective is taken at once.
                door = next((option for option in usable if into_focus(option)), None)
                if door:
                    return door, "route", {}

        def brief(option):
            text = option.short or option.description
            # An exit to a room not seen in this story state says so: goals can ask for it.
            fresh_room = option.kind == "exit" and option.destination not in seen
            return f"{text} to a new room" if fresh_room and text.startswith("Go ") else text

        def toward(option, goal):
            text = brief(option)
            return text == goal or text.startswith(f"{goal} ")

        # A known exit that points at the goal can be used again, a limited number of
        # times per story state. Without this, Link could not walk back the way he came.
        reused = self.memory.current.setdefault("reused", {})
        ways = [option for option in usable if option.kind == "exit" and option not in fresh
                and reused.get(f"{room}|{option.id}", 0) < GOAL_REUSES]
        target = getattr(self, "target", None)
        if target and self.hops < MAX_HOPS:
            # Link has been to the landmark before: follow the map he built, not the compass.
            first = self.memory.hop(room, options, to=target)
            if first:
                self.hops += 1
                return next(option for option in usable if option.id == first), "route", {}
            first = self.memory.room_hop(obs.room, lambda place: place == target)
            step = first and next((option for option in usable if option.id == first), None)
            if step:
                self.hops += 1
                return step, "route", {}
        if hint.startswith("Go "):
            wanted = hint[3:-1].split(" or ")
            if len(wanted) > 1:
                # Laya follows one direction far better than two. Name the first that has an
                # exit. With no exit either way, the way there goes around: explore instead.
                offered = [way for way in wanted if any(toward(option, f"Go {way}") for option in [*fresh, *ways])]
                hint = f"Go {offered[0]}." if offered else "Go to a new room."
            goal = hint[:-1]
            if not any(toward(option, goal) for option in fresh):
                fresh = [*fresh, *(option for option in ways if toward(option, goal))]
            if hint == "Go outside." and not any(toward(option, goal) for option in fresh):
                # The door is some rooms away. Follow the known map to it.
                first = self.memory.hop(room, options, leaving=True)
                if first:
                    return next(option for option in usable if option.id == first), "route", {}
        else:
            # At a landmark the goal is a task. What matches the task can be done again:
            # rooms reset when Link leaves, and the dirt he dug is back. Bounded per area.
            tasks = [part.strip().lower() for part in hint.rstrip(".").split(" or ")]
            again = [option for option in usable if option not in fresh and option.kind != "exit"
                     and any((option.short or "").lower().startswith(task[:16]) for task in tasks)]
            if again and not any((option.short or "").lower().startswith(task[:16])
                                 for option in fresh for task in tasks):
                done = self.memory.current.setdefault("redone", {})
                if done.get(room, 0) < TASK_REDOS:
                    done[room] = done.get(room, 0) + 1
                    fresh = [*fresh, *again]
        impasse = not fresh

        def by_recipe(exit_id):
            """The next thing to do here to get through an exit that is closed right now."""
            done = getattr(self, "done_here", ())
            steps = self.memory.recipe(obs.room, getattr(self, "entered_from", "start"), exit_id)
            for step in steps or ():
                if step not in done:
                    return next((option for option in usable if option.id == step), None)
            # No recipe yet. Use what is known to have opened this exit, then anything in
            # the room not done on this visit: one of them is what opens it.
            openers = [key.split("|", 1)[1] for key, ways in self.memory.opened.items()
                       if key.startswith(f"{obs.room}@") and exit_id in ways]
            untried = [option for option in usable if option.kind != "exit" and option.id not in done]
            return next((option for option in untried if option.id in openers), None) or next(
                (option for option in untried if option.kind == "push"), None) or next(iter(untried), None)

        def worth_a_trip(place):
            # While the objective is in one dungeon, other interiors do not attract trips,
            # and from inside it nothing outside does.
            if focus is None or self.memory.dungeons.get(place) == focus:
                return True
            return place[:2] in OVERWORLD and self.pyboy.memory[DUNGEON_INDEX] != focus

        if not impasse:
            self.hops = 0
        else:
            first = self.memory.hop(room, options, worth_a_trip)
            if first and self.hops >= MAX_HOPS:
                # Travelling this long without finding anything new means the map of what
                # is pending is wrong. Drop it, so the impasse rule takes over.
                self.memory.current["pending"].clear()
                first = None
            if first:
                self.hops += 1
                return next(option for option in usable if option.id == first), "frontier", {}
            if self.hops < MAX_HOPS:
                # No open path from this part of the room. Plan room by room, and reopen the
                # way with what worked before.
                pending_rooms = {name.split("@")[0] for name, items in self.memory.current["pending"].items()
                                 if items}
                first = self.memory.room_hop(obs.room, lambda place: place in pending_rooms and worth_a_trip(place))
                step = first and (next((option for option in usable if option.id == first), None)
                                  or by_recipe(first))
                if step:
                    self.hops += 1
                    return step, "recipe", {}
            # Nothing is known to be pending. Sweep: head for the known room Link has not
            # seen for the longest time, where a new look may find what changed.
            stale_rooms = sorted((place for place in self.memory.dungeons
                                  if place != obs.room and worth_a_trip(place)),
                                 key=lambda place: self.memory.last_seen.get(place, -1))
            for place in stale_rooms[:3]:
                first = self.memory.room_hop(obs.room, lambda name: name == place)
                step = first and (next((option for option in usable if option.id == first), None)
                                  or by_recipe(first))
                if step:
                    return step, "sweep", {}
        candidates = sorted(fresh or usable, key=lambda option: len(option.route))[:12]
        if not candidates:
            return None, "none", {}

        def chosen(option, origin, details):
            if self.memory.tries(room, option.id) and option.kind == "exit":
                reused[f"{room}|{option.id}"] = reused.get(f"{room}|{option.id}", 0) + 1
            return option, origin, details

        context = self.context(obs, hint)
        details = {}
        if self.supervisor and len(candidates) > 1 and (impasse or self.since_progress >= self.stall):
            annotated = [(option.id, option.description + (
                "" if not self.memory.tries(room, option.id) else " (already tried)")) for option in candidates]
            choice, details = self.supervisor.consult(context, annotated, self.decisions)
            if choice:
                return chosen(next(option for option in candidates if option.id == choice), "supervisor", details)
        if impasse:
            # Nothing new anywhere known: least-tried first, so repeats rotate instead of sticking.
            option = min(candidates, key=lambda option: (self.memory.tries(room, option.id), len(option.route)))
            return option, "fallback", details
        if len(candidates) == 1:
            return chosen(candidates[0], "forced", details)
        keys = {f"option_{index + 1}": option for index, option in enumerate(candidates)}
        # Laya matches short text well and long text at chance, so it gets only the goal.
        key, laya = self.policy.choose({"goal": hint}, {key: brief(option) for key, option in keys.items()})
        # The origin names who chose, so a comparison run is never attributed to Laya.
        return chosen(keys[key], getattr(self, "label", "laya"), {**details, "laya": laya})

    def step(self):
        """One decision. Returns False when there is nothing left to try."""
        if not self.settle():
            self.write({"event": "stuck_outside_control", "mode": observe(self.pyboy).mode})
            return False
        obs = observe(self.pyboy)
        if self.memory.enter(progress(self.pyboy)) and self.decisions:
            self.since_progress = 0
            self.idle = 0
            self.sweeps = 0
            if self.supervisor:
                self.supervisor.progressed()
        self.memory.dungeons[obs.room] = self.pyboy.memory[DUNGEON_INDEX]
        self.memory.last_seen[obs.room] = self.decisions
        if obs.room != self.here:
            self.entered_from, self.here, self.done_here = self.here or "start", obs.room, []
        name, hint = self.objective(obs.room)
        started = time.perf_counter()
        # A quick pass on 16-pixel steps first. The slower passes run only when the area
        # has nothing new, or still owes an option that only they can route to.
        options = self.surveyor.options(self.pyboy, **SURVEY_LEVELS[0])
        node = self.memory.area(obs.room, options)
        # Record the arrival first: it marks the way back as known, and the decision to
        # look deeper must not count that exit as something new.
        came_from = self.arrival[0]
        self.memory.arrive(node, options, *self.arrival)
        self.arrival = (None, None)
        back_in_dungeon = (came_from and came_from != node and getattr(self, "focus", None) is not None
                           and self.pyboy.memory[DUNGEON_INDEX] == self.focus)
        # Crossing a room that reset is done by recipe, not by treating everything as new.
        depth = self.memory.current.setdefault("depth", {})
        level = 0
        # How closely an area was examined holds only while its terrain is the same:
        # a door that opens after a fight must be looked for again.
        terrain = bytes(self.pyboy.memory[0xCE00:0xCEC0]) + room_layout(self.pyboy)
        examined = f"{node}#{hashlib.sha1(terrain).hexdigest()[:8]}"
        # An area with a single way out looks like a dead end. Narrow exits are what the
        # quick pass misses, so look closer once before accepting that.
        dead_end = sum(option.kind == "exit" for option in options) <= 1 and not depth.get(examined)
        # A dungeon room that reset needs the closer look again: pushes are only found there.
        dead_end = dead_end or bool(back_in_dungeon)
        while level < len(SURVEY_LEVELS) - 1 and (dead_end or not self.memory.fresh(node, options)):
            found = {option.id for option in options}
            owed = [item for item in self.memory.current["pending"].get(node, []) if item not in found]
            forced, dead_end = dead_end, False
            if depth.get(examined, 0) > level and not owed and not (forced and back_in_dungeon):
                break  # the deeper passes already ran here and left nothing to do
            if level == len(SURVEY_LEVELS) - 2 and not owed and self.memory.hop(node, options):
                break  # the finest pass is slow: keep it for when no other area has options
            level += 1
            extra = [option for option in self.surveyor.options(self.pyboy, **SURVEY_LEVELS[level])
                     if option.id not in found]
            options += extra
            if not extra:
                # Only a closer look that found nothing more can be skipped next time:
                # what it does find is not stored, so it has to be found again.
                depth[examined] = max(depth.get(examined, 0), level)
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
        if getattr(self, "focus", None) is not None and self.pyboy.memory[DUNGEON_INDEX] == self.focus:
            # Leaving the dungeon of the objective is not offered here, so it must not
            # count as something pending either, or it keeps calling Link back to the door.
            ways_out = {item.id for item in options if item.kind == "exit" and item.destination[:2] in OVERWORLD
                        and item.destination in self.memory.dungeons}
            self.memory.current["pending"][node] = [
                name for name in self.memory.current["pending"].get(node, []) if name not in ways_out]
        exits_now = {item.id for item in options if item.kind == "exit"}
        if self.last and self.last[0] == node and exits_now - self.last[2]:
            self.memory.unlocked(node, self.last[1], exits_now - self.last[2])
        started = time.perf_counter()
        option, origin, details = self.decide(obs, node, options, hint)
        choice_seconds = time.perf_counter() - started
        if option is not None:
            # Whatever the rules above say, the same few moves over and over is a loop.
            # Stop offering them as new, forget what is pending, and decide again.
            self.trail.append((node, option.id))
            window = self.trail[-LOOP_WINDOW:]
            # A longer cycle shows up as one move made many times over a longer stretch.
            often = Counter(self.trail[-LONG_WINDOW:]).most_common(1)[0][1] >= LONG_REPEATS
            if often:
                window = [move for move, count in Counter(self.trail[-LONG_WINDOW:]).items() if count >= 3]
            if often or (len(window) == LOOP_WINDOW and len(set(window)) <= LOOP_MOVES and origin != "fallback"):
                stale = self.memory.current.setdefault("stale", [])
                stale.extend(f"{place}|{name}" for place, name in set(window) if f"{place}|{name}" not in stale)
                self.memory.current["pending"].clear()
                self.trail.clear()
                self.loops += 1
                self.write({"event": "loop_cut", "room": obs.room, "moves": sorted(name for _, name in set(window))})
                option, origin, details = self.decide(obs, node, options, hint)
        if option is None:
            # Usually a scene that started between two checks. Let it play, then look again.
            self.empty += 1
            self.write({"event": "no_options", "room": obs.room, "xy": [obs.x, obs.y], "streak": self.empty})
            if self.empty >= 3 and self.undo:
                # Link is shut in (a block pushed the wrong way). Go back to before the
                # decision that did it, and never offer that decision there again.
                state, place, name = self.undo
                self.undo = None
                self.pyboy.load_state(BytesIO(state))
                self.memory.banned.add((place, name))
                self.deaths += 1
                self.empty = 0
                self.write({"event": "undone", "room": obs.room, "dropped": name})
                return True
            for _ in range(10):
                execute(self.pyboy, "wait", render=self.watch)
            return self.empty <= 12
        self.empty = 0
        if origin == "sweep":
            self.sweeps += 1
            if self.sweeps > SWEEP_LIMIT:
                # Every known room was looked at again, several times, with nothing new.
                self.write({"event": "impasse", "room": obs.room, "xy": [obs.x, obs.y], "objective": name,
                            "after": "sweeps"})
                return False
        if origin == "fallback":
            self.idle += 1
            # Dungeon rooms reset and have to be redone, so the rotation needs more room there.
            inside = getattr(self, "focus", None) is not None and self.pyboy.memory[DUNGEON_INDEX] == self.focus
            if self.idle > self.patience * (6 if inside else 1):
                self.write({"event": "impasse", "room": obs.room, "xy": [obs.x, obs.y], "objective": name})
                return False
        self.decisions += 1
        self.since_progress += 1
        self.origins[origin] = self.origins.get(origin, 0) + 1
        self.status(f"{name} | {option.description}")
        before = BytesIO()
        self.pyboy.save_state(before)
        health, story = self.pyboy.memory[HEALTH], progress(self.pyboy)
        self.undo = (before.getvalue(), node, option.id)
        self.memory.record(node, option.id)
        # Kept to notice, at the next survey, an option that makes new exits appear.
        self.last = (node, option.id, exits_now) if option.kind != "exit" else None
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
        if outcome != "failed, option dropped":
            if after.room != obs.room and option.kind == "exit":
                self.memory.learn(obs.room, self.entered_from, option.id, self.done_here)
            elif after.room == obs.room:
                self.done_here.append(option.id)
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
            "scenes_waited": self.scenes, "loops_cut": self.loops, "health": [self.pyboy.memory[HEALTH], self.pyboy.memory[HEALTH + 1]],
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
            memory = None
            if resume:
                try:
                    memory = Memory.load(json.loads(memory_file.read_text(encoding="utf-8")))
                except ValueError as error:
                    # The game state is still good. Only what was tried where is forgotten.
                    print(f"{error}. A sessão continua do estado salvo, com memória nova.", flush=True)
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
