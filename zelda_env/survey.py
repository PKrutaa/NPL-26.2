"""Discover what Link can do in the current room by trying inputs in a headless copy."""

from collections import deque
from dataclasses import dataclass, field
from io import BytesIO

from .adapter import DIRECTIONS, execute, observe, room_layout

DELTA = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
COMPASS = {"up": "north", "right": "east", "down": "south", "left": "west"}
ENTITY_NAMES = {"Impa": "Impa", "monkey": "a monkey"}

# Save-file fields that only change when the story advances (pinned Ages US layout).
PROGRESS_RANGES = (
    (0xC672, 0xC682),  # small keys per dungeon
    (0xC688, 0xC68A),  # equipped B and A items
    (0xC69A, 0xC6AA),  # obtained treasures
    (0xC6AB, 0xC6AC),  # max health
    (0xC6BF, 0xC6C0),  # essences
    (0xC6D0, 0xC6E0),  # global flags
    (0xC6E8, 0xC6E9),  # Maku Tree state
)
ROOM_FLAGS = 0xC700  # four 256-byte tables: present, past, groups 4 and 5
ROOM_VISITED = 0x10
HEALTH = 0xC6AA
TEXT_INDEX = 0xCBA2
ESSENCES = 0xC6BF


def progress(pyboy):
    """Bytes that change on story progress. Visiting a room alone does not count."""
    mem = pyboy.memory
    story = bytes(value for start, end in PROGRESS_RANGES for value in mem[start:end])
    rooms = bytes(value & ~ROOM_VISITED & 0xFF for value in mem[ROOM_FLAGS:ROOM_FLAGS + 0x400])
    return story + rooms


@dataclass(frozen=True)
class Option:
    id: str
    kind: str  # exit, interact, push, trigger
    description: str
    route: tuple = field(compare=False, repr=False)  # ((action, hold_frames), ...)
    destination: str = None


def bearing(obs, x, y):
    dx, dy = x - obs.x, y - obs.y
    if abs(dx) < 12 and abs(dy) < 12:
        return "right next to Link"
    vertical = "north" if dy < -abs(dx) / 2 else "south" if dy > abs(dx) / 2 else ""
    horizontal = "west" if dx < -abs(dy) / 2 else "east" if dx > abs(dy) / 2 else ""
    return f"to the {'-'.join(part for part in (vertical, horizontal) if part)}"


def run_route(pyboy, route, *, render=False):
    """Replay a surveyed route. Stop early if the game leaves normal control."""
    after, event = observe(pyboy), "no_change"
    for action, hold in route:
        if action != "wait" and after.mode != "playing":
            break
        after, event, _ = execute(pyboy, action, render=render, hold_frames=hold)
    return after, event


class Surveyor:
    def __init__(self, rom):
        from pyboy import PyBoy

        self.shadow = PyBoy(str(rom), window="null", ram_file=BytesIO(bytes(8192)), sound_volume=0)
        self.shadow.set_emulation_speed(0)

    def close(self):
        self.shadow.stop(save=False)

    def _capture(self):
        stream = BytesIO()
        self.shadow.save_state(stream)
        return stream.getvalue()

    def _load(self, state):
        self.shadow.load_state(BytesIO(state))

    def _changed(self, before_progress, before_layout, before_mode):
        """Did the last probe do anything other than bump into a wall?"""
        obs = observe(self.shadow)
        return (obs.mode != before_mode or progress(self.shadow) != before_progress
                or room_layout(self.shadow) != before_layout)

    def _text(self):
        return self.shadow.memory[TEXT_INDEX] | self.shadow.memory[TEXT_INDEX + 1] << 8

    def _effect(self, entity, after, base_progress, base_layout):
        moved = entity and not any(
            item["slot"] == entity["slot"] and (item["x"], item["y"]) == (entity["x"], entity["y"])
            for item in after.entities)
        return bool(moved) or self._changed(base_progress, base_layout, "playing")

    def can_move(self, pyboy):
        """Does any direction actually move Link right now?"""
        stream = BytesIO()
        pyboy.save_state(stream)
        for direction in DIRECTIONS:
            self._load(stream.getvalue())
            after, event, _ = execute(self.shadow, direction)
            if event in ("moved", "room_changed") or after.mode != "playing":
                return True
        return False

    def options(self, pyboy, *, grid=8, limit=700):
        """Flood the room with short moves. Return one Option per distinct outcome."""
        start = observe(pyboy)
        if start.mode != "playing":
            return []
        stream = BytesIO()
        pyboy.save_state(stream)
        root = stream.getvalue()
        base_progress, base_layout = progress(pyboy), room_layout(pyboy)
        health = pyboy.memory[HEALTH]
        found = {}
        poked = set()
        lingered = set()
        seen = {(start.x // grid, start.y // grid)}
        queue = deque([(root, ())])
        expanded = 0

        def add(option_id, kind, description, route, destination=None):
            if option_id not in found:
                found[option_id] = Option(option_id, kind, description, route, destination)

        def linger(state, route, here):
            self._load(state)
            probe = (("wait", 150),)
            waited, _ = run_route(self.shadow, probe)
            if self.shadow.memory[HEALTH] >= health and waited.room == start.room and self._changed(
                    base_progress, base_layout, "playing"):
                spot = f"text{self._text():04x}" if waited.mode == "dialogue" else f"{here.x // 32}:{here.y // 32}"
                add(f"trigger:wait:{spot}", "trigger",
                    f"Go to the spot {bearing(start, here.x, here.y)} and wait there for something to happen",
                    (*route, *probe))

        while queue and expanded < limit:
            state, route = queue.popleft()
            expanded += 1
            self._load(state)
            here = observe(self.shadow)
            cell = (here.x // 32, here.y // 32)
            if cell not in lingered:
                # Some events start a moment after Link reaches an area.
                lingered.add(cell)
                linger(state, route, here)
            responded = False
            for direction in DIRECTIONS:
                self._load(state)
                before = observe(self.shadow)
                after, event, _ = execute(self.shadow, direction)
                responded |= event != "blocked" or after.mode != "playing"
                step = (*route, (direction, 12))
                if self.shadow.memory[HEALTH] < health:
                    continue  # never plan a route that takes damage
                # A scene or a slow transition hides the room for a while. Wait for it to
                # come back before deciding whether this was an exit or an event.
                waits = 0
                while after.room is None and waits < 40:
                    after, _, _ = execute(self.shadow, "wait")
                    waits += 1
                step = (*step, *((("wait", 12),) * waits))
                if after.room is None:
                    add(f"trigger:{after.mode}:{direction}", "trigger",
                        f"Walk to the spot {bearing(start, before.x, before.y)} where a scene starts", step)
                    continue
                if after.room != start.room:
                    same_map = after.room[:2] == start.room[:2]
                    where = (f"the {COMPASS[direction]} edge of this screen" if same_map
                             else f"the doorway or stairs {bearing(start, before.x, before.y)}")
                    add(f"exit:{after.room}", "exit", f"Leave through {where}", step, after.room)
                    continue
                if after.mode != "playing":
                    # One option per event: a line of trigger tiles is a single thing to do.
                    spot = f"text{self._text():04x}" if after.mode == "dialogue" else direction
                    add(f"trigger:{spot}", "trigger",
                        f"Walk to the spot {bearing(start, before.x, before.y)} where something happens", step)
                    continue
                dx, dy = DELTA[direction]
                if event == "moved":
                    key = (after.x // grid, after.y // grid)
                    if key not in seen:
                        seen.add(key)
                        queue.append((self._capture(), step))
                    # Link slides around round characters, so a walk toward one may never block.
                    if not any(0 < (item["x"] - after.x) * dx + (item["y"] - after.y) * dy <= 26
                               and abs((item["x"] - after.x) * dy) + abs((item["y"] - after.y) * dx) <= 10
                               for item in after.entities):
                        continue
                # Probe the obstacle or character ahead once per standing position and direction.
                tile = ((after.x + dx * 12) // 16, (after.y + dy * 12) // 16)
                stand = (after.x // grid, after.y // grid, direction)
                if stand in poked:
                    continue
                poked.add(stand)
                blocked = self._capture()
                tx, ty = after.x + dx * 14, after.y + dy * 14
                near = sorted(after.entities, key=lambda item: abs(item["x"] - tx) + abs(item["y"] - ty))
                entity = near[0] if near and abs(near[0]["x"] - tx) + abs(near[0]["y"] - ty) <= 20 else None
                target = f"slot{entity['slot']}" if entity else f"{tile[0]}:{tile[1]}"
                where = bearing(start, tx, ty)
                for button, action in (("a", "interact"), ("b", "use_b")):
                    self._load(blocked)
                    probe = ((action, 1), ("wait", 20))
                    run_route(self.shadow, probe)
                    if not self._changed(base_progress, base_layout, "playing"):
                        continue
                    opened = observe(self.shadow).mode == "dialogue"
                    # The id carries what would happen now. A character with something
                    # new to say is a new option; the same line again is not.
                    result = f"text{self._text():04x}" if opened else "event"
                    if opened and entity:
                        name = ENTITY_NAMES.get(entity["kind"], "the character")
                        text = f"Talk to {name} {where}"
                    elif opened:
                        text = f"Read or inspect the object {where}"
                    elif entity:
                        text = f"Talk to the character {where}, who reacts"
                    else:
                        text = f"Use the {button.upper()} button item on the obstacle {where}"
                    add(f"interact:{target}:{button}:{result}", "interact", text, (*step, *probe))
                    break
                if f"push:{target}:{direction}" in found:
                    continue  # already known; alignment matters, so keep probing until then
                self._load(blocked)
                probe = ((direction, 60), ("wait", 30))
                pushed, _ = run_route(self.shadow, probe)
                if self._effect(entity, pushed, base_progress, base_layout):
                    # Rule out things that happen anyway, such as a character walking by.
                    self._load(blocked)
                    idle, _ = run_route(self.shadow, (("wait", 60), ("wait", 30)))
                    if not self._effect(entity, idle, base_progress, base_layout):
                        add(f"push:{target}:{direction}", "push",
                            f"Push the object {where} toward the {COMPASS[direction]}", (*step, *probe))
            if route and not responded:
                # Controls that stop answering right after a walk mean a scene is about to start.
                linger(state, route, here)
        return list(found.values())
