"""Discover what Link can do in the current room by trying inputs in a headless copy."""

import hashlib
from collections import deque
from dataclasses import dataclass, field
from io import BytesIO

from .adapter import DIRECTIONS, enemies, execute, observe, room_layout

DELTA = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
COMPASS = {"up": "north", "right": "east", "down": "south", "left": "west"}
ENTITY_NAMES = {"Impa": "Impa", "monkey": "a monkey"}

# Save-file fields that only change when the story advances (pinned Ages US layout).
PROGRESS_RANGES = (
    (0xC672, 0xC682),  # small keys per dungeon
    (0xC69A, 0xC6AA),  # obtained treasures
    (0xC6AB, 0xC6AC),  # max health
    (0xC6BF, 0xC6C0),  # essences
    (0xC6D0, 0xC6E0),  # global flags
    (0xC6E8, 0xC6E9),  # Maku Tree state
)
ROOM_FLAGS = 0xC700  # four 256-byte tables: present, past, groups 4 and 5
ROOM_VISITED = 0x10
HEALTH = 0xC6AA
ESSENCES = 0xC6BF
TEXT_INDEX = 0xCBA2
COLLISIONS = 0xCE00  # same 16-byte row stride as the layout
INVENTORY_B, INVENTORY_A = 0xC688, 0xC689
STORAGE = 0xC68A  # sixteen item slots shown in the menu
SWORD = 0x05
HEART = 4  # health is counted in quarter hearts
OVERWORLD = ("00", "01")  # present and past; other groups are interiors and dungeons
TOOL_OPTIONS = 4
# (frames per step, reach in pixels, steps to back away after a swing, style, detour side)
# "chase" walks to the enemy and steps around what blocks the way. "ambush" stands still,
# turns toward the enemy and swings when it comes close: it suits enemies that fly in.
TACTICS = (
    (6, 18, 0, "chase", 1), (4, 22, 0, "chase", -1), (8, 16, 0, "chase", 1), (6, 20, 2, "chase", -1),
    (6, 22, 0, "ambush", 1), (4, 26, 0, "ambush", 1), (4, 16, 3, "chase", 1), (12, 22, 1, "chase", -1),
    (8, 30, 0, "ambush", 1),
)
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}
TURN = {"up": ("left", "right"), "down": ("right", "left"), "left": ("down", "up"), "right": ("up", "down")}


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
    short: str = None  # the few words Laya reads; it matches short text far better


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
        if action != "wait" and not action.startswith("press_") and after.mode != "playing":
            break
        after, event, _ = execute(pyboy, action, render=render, hold_frames=hold)
    return after, event


class Surveyor:
    def __init__(self, rom):
        from pyboy import PyBoy

        self.shadow = PyBoy(str(rom), window="null", ram_file=BytesIO(bytes(8192)), sound_volume=0)
        self.shadow.set_emulation_speed(0)
        self.volatile = False

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
                or (not self.volatile and room_layout(self.shadow) != before_layout))

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

    def _pushed(self, entity, after, base_progress, base_layout):
        """A push moved something: a tile, a character, or the save data.

        Leaving normal control alone only counts against a character. Against plain
        terrain it is some other event that walking there would also start.
        """
        if progress(self.shadow) != base_progress:
            return True
        if not self.volatile and room_layout(self.shadow) != base_layout:
            return True
        return bool(entity) and self._effect(entity, after, base_progress, base_layout)

    def _effect_name(self, base_progress, base_layout):
        """A short, stable name for what a probe did: new save data, or how one tile changed."""
        after = progress(self.shadow)
        if after != base_progress:
            return hashlib.sha1(after).hexdigest()[:4]
        layout = room_layout(self.shadow)
        for index, tile in enumerate(layout):
            if tile != base_layout[index]:
                return f"{base_layout[index]:02x}{tile:02x}"
        return observe(self.shadow).mode[:4]

    def _hurt_after(self, floor, frames=40):
        """Falls and drowning take the health a moment later. Wait before trusting it."""
        if self.shadow.memory[HEALTH] < floor:
            return True
        run_route(self.shadow, (("wait", frames),))
        return self.shadow.memory[HEALTH] < floor

    def equip_route(self, root, item):
        """Menu presses that put a stored item on the A button, found by trying them."""
        for moves in range(16):
            route = (("press_start", 60), *((("press_right", 10),) * (moves % 4)),
                     *((("press_down", 10),) * (moves // 4)), ("press_a", 10), ("press_start", 60))
            self._load(root)
            run_route(self.shadow, route)
            if self.shadow.memory[INVENTORY_A] == item and observe(self.shadow).mode == "playing":
                return route
        return None

    def sword_action(self, pyboy):
        if pyboy.memory[INVENTORY_A] == SWORD:
            return "interact"  # A is the item button outside dialogue
        return "use_b" if pyboy.memory[INVENTORY_B] == SWORD else None

    def fight(self, state, action, *, max_loss, steps=160):
        """Simulate a sword fight. Return the inputs that kill one enemy, or None.

        The copy starts from the exact state of the game, so a fight that works here
        replays the same way in the main emulator.
        """
        for hold, reach, retreat, style, side_sign in TACTICS:
            self._load(state)
            start = observe(self.shadow)
            count, health = len(enemies(self.shadow)), self.shadow.memory[HEALTH]
            route, away, detour, previous = [], 0, 0, None
            for _ in range(steps):
                obs = observe(self.shadow)
                foes = enemies(self.shadow)
                if obs.mode != "playing" or obs.room != start.room:
                    break  # leaving the room also empties the enemy list; that is not a win
                if len(foes) < count:
                    return tuple(route), health - self.shadow.memory[HEALTH]
                if self.shadow.memory[HEALTH] < health - max_loss:
                    break
                foe = min(foes, key=lambda item: abs(item["x"] - obs.x) + abs(item["y"] - obs.y))
                dx, dy = foe["x"] - obs.x, foe["y"] - obs.y
                toward = ("right" if dx > 0 else "left") if abs(dx) >= abs(dy) else ("down" if dy > 0 else "up")
                side = abs(dy) if toward in ("left", "right") else abs(dx)
                close = max(abs(dx), abs(dy)) <= reach and side <= 10
                stuck = previous is not None and previous == (obs.x, obs.y, "move")
                if stuck and not detour:
                    detour = 3  # something is in the way: step around it
                moving = True
                if away:
                    away -= 1
                    step = (OPPOSITE[toward], hold)
                elif close and obs.facing == toward:
                    step, moving, away = (action, 1), False, retreat
                elif close:
                    step, moving = (toward, 2), False
                elif style == "ambush":
                    step, moving = ("wait", hold), False
                elif detour:
                    detour -= 1
                    step = (TURN[toward][0 if side_sign > 0 else 1], hold)
                elif side > 6:
                    # Line up on the other axis first, so the swing connects.
                    step = (("down" if dy > 0 else "up") if toward in ("left", "right")
                            else ("right" if dx > 0 else "left"), min(hold, side))
                else:
                    step = (toward, hold)
                previous = (obs.x, obs.y, "move" if moving else "act")
                route.append(step)
                execute(self.shadow, step[0], hold_frames=step[1])
        return None

    def options(self, pyboy, *, grid=8, limit=700, tolerance=0, stride=12, pushes=True):
        """Flood the room with short moves. Return one Option per distinct outcome."""
        start = observe(pyboy)
        if start.mode != "playing":
            return []
        stream = BytesIO()
        pyboy.save_state(stream)
        root = stream.getvalue()
        base_progress, base_layout = progress(pyboy), room_layout(pyboy)
        # Some rooms change their tiles by themselves. There, a changed tile proves nothing.
        self._load(root)
        run_route(self.shadow, (("wait", 30),))
        self.volatile = room_layout(self.shadow) != base_layout
        # The same for save data: a flag the room sets by itself is not an effect of a probe.
        base_progress = progress(self.shadow)
        health = pyboy.memory[HEALTH]
        found = {}
        poked = set()
        lingered = set()
        seen = {(start.x // grid, start.y // grid)}
        queue = deque([(root, ())])
        expanded = 0

        def add(option_id, kind, description, route, destination=None, short=None):
            if option_id not in found:
                found[option_id] = Option(option_id, kind, description, route, destination, short or description)

        def linger(state, route, here):
            self._load(state)
            before_wait = (progress(self.shadow), room_layout(self.shadow))
            probe = (("wait", 150),)
            waited, _ = run_route(self.shadow, probe)
            if self.shadow.memory[HEALTH] >= health - tolerance and waited.room == start.room and self._changed(
                    *before_wait, "playing"):
                # Named by the effect, so one event seen from many spots is one option.
                effect = hashlib.sha1(progress(self.shadow) + waited.mode.encode()).hexdigest()[:6]
                spot = f"text{self._text():04x}" if waited.mode == "dialogue" else effect
                add(f"trigger:wait:{spot}", "trigger",
                    f"Go to the spot {bearing(start, here.x, here.y)} and wait there for something to happen",
                    (*route, *probe), short="Wait for the event")

        # One kit per usable item: (item, button, action, menu presses to equip it first).
        # Stored items are tried by setting the button in the copy. A real option always
        # carries the menu presses, and is replayed from the start before it is offered.
        kits = [(pyboy.memory[INVENTORY_A], "a", "interact", ()), (pyboy.memory[INVENTORY_B], "b", "use_b", ())]
        for item in dict.fromkeys(pyboy.memory[STORAGE:STORAGE + 16]):
            menu = self.equip_route(root, item) if item else None
            if menu:
                kits.append((item, "a", "interact", menu))
        tools = tuple(kit for kit in kits if kit[0] not in (0, SWORD))

        def wield(kit):
            if kit[3]:
                self.shadow.memory[INVENTORY_A] = kit[0]

        def confirmed(kit, route):
            """A stored item only counts if the whole route works with real menu presses."""
            if not kit[3]:
                return True
            self._load(root)
            run_route(self.shadow, route)
            return not self._hurt_after(health - tolerance) and (
                room_layout(self.shadow) != base_layout or self._changed(base_progress, base_layout, "playing"))

        dug = set()
        stretches = set()
        push_tries = {}
        base_collisions = bytes(pyboy.memory[COLLISIONS:COLLISIONS + 0xC0])
        foes = enemies(pyboy)
        sword = self.sword_action(pyboy)
        if foes and sword:
            # Prefer a fight without damage. Accept up to one heart while two remain after it.
            for max_loss in (0, HEART):
                if max_loss and health - max_loss < 2 * HEART:
                    break
                won = self.fight(root, sword, max_loss=max_loss)
                if won:
                    nearest = min(foes, key=lambda item: abs(item["x"] - start.x) + abs(item["y"] - start.y))
                    cost = "" if not won[1] else ", taking some damage"
                    add(f"fight:{len(foes)}:{nearest['id']:02x}", "fight",
                        f"Attack the enemy {bearing(start, nearest['x'], nearest['y'])} with the sword{cost}", won[0],
                        short="Attack the enemy")
                    break

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
                # Every probe is judged against the moment right before it, not against the
                # start of the survey: a door that shuts behind Link is not an effect of a probe.
                before_step = progress(self.shadow)
                after, event, _ = execute(self.shadow, direction, hold_frames=stride)
                responded |= event != "blocked" or after.mode != "playing"
                base_progress, base_layout = progress(self.shadow), room_layout(self.shadow)
                step = (*route, (direction, stride))
                if self.shadow.memory[HEALTH] < health - tolerance:
                    continue  # do not plan a route that costs more health than allowed
                # A scene or a slow transition hides the room for a while. Wait for it to
                # come back before deciding whether this was an exit or an event.
                waits = 0
                while after.room is None and waits < 90:
                    after, _, _ = execute(self.shadow, "wait")
                    waits += 1
                # Walking out of a door keeps Link out of control for a moment in the old
                # room before the new one loads. Let that finish, so it is seen as an exit.
                while after.room == start.room and after.mode in ("transition", "locked", "unknown") and waits < 60:
                    after, _, _ = execute(self.shadow, "wait")
                    waits += 1
                    while after.room is None and waits < 90:
                        after, _, _ = execute(self.shadow, "wait")
                        waits += 1
                step = (*step, *((("wait", 12),) * waits))
                if after.room is None:
                    add(f"trigger:{after.mode}:{direction}", "trigger",
                        f"Walk to the spot {bearing(start, before.x, before.y)} where a scene starts", step,
                        short="Walk into the event")
                    continue
                if after.room != start.room:
                    same_map = after.room[:2] == start.room[:2]
                    where = (f"the {COMPASS[direction]} edge of this screen" if same_map
                             else f"the doorway or stairs {bearing(start, before.x, before.y)}")
                    name = f"exit:{after.room}"
                    if same_map:
                        # Two gaps on one edge can lead to parts of the next screen that do not
                        # connect. Name the exit by where its landing strip begins: walk along
                        # the edge on the far side until something blocks. One open edge gets
                        # one name wherever Link crosses it; separate gaps get separate names.
                        upright = direction in ("up", "down")
                        stretch = (after.room, direction, (before.x if upright else before.y) // 40)
                        if stretch in stretches:
                            continue
                        stretches.add(stretch)
                        landed = after
                        for _ in range(20):
                            if landed.mode != "playing":
                                break
                            moved, slid, _ = execute(self.shadow, "left" if upright else "up")
                            if slid != "moved" or moved.room != after.room or moved.mode != "playing":
                                break
                            landed = moved
                        name = f"exit:{after.room}/{(landed.x if upright else landed.y) // 16}"
                    add(name, "exit", f"Leave through {where}", step, after.room,
                        short=(f"Go {COMPASS[direction]}" if same_map else
                               "Go outside" if after.room[:2] in OVERWORLD and start.room[:2] not in OVERWORLD
                               else "Enter the door or stairs"))
                    continue
                if after.mode != "playing":
                    # One option per event: a line of trigger tiles is a single thing to do.
                    spot = f"text{self._text():04x}" if after.mode == "dialogue" else direction
                    add(f"trigger:{spot}", "trigger",
                        f"Walk to the spot {bearing(start, before.x, before.y)} where something happens", step,
                        short="Walk into the event")
                    continue
                dx, dy = DELTA[direction]
                if event == "moved":
                    changed = base_progress
                    if changed != before_step:
                        # The save data changed on this step. If standing still does the same,
                        # the room did it by itself (a flag set a moment after entering): take
                        # that as the new baseline. Otherwise Link picked something up here.
                        moved_here = self._capture()
                        self._load(state)
                        run_route(self.shadow, (("wait", stride),))
                        drifted = progress(self.shadow)
                        self._load(moved_here)
                        if drifted == before_step:
                            effect = hashlib.sha1(changed).hexdigest()[:6]
                            add(f"collect:{effect}", "trigger", f"Pick up the item {bearing(start, after.x, after.y)}",
                                step, short="Pick up the item")
                            continue
                    # A step cut short ends against something, often a doorway. Keep that
                    # exact spot even when its grid cell was seen, so the search can go on from it.
                    short = abs(after.x - before.x) + abs(after.y - before.y) < stride - 2
                    key = ("edge", after.x // 2, after.y // 2) if short else (after.x // grid, after.y // grid)
                    if key not in seen:
                        seen.add(key)
                        queue.append((self._capture(), step))
                    # Items such as the shovel act on open ground. Try each kind of tile once.
                    ahead = ((after.y + dy * 16) // 16) * 16 + (after.x + dx * 16) // 16
                    for kit in tools:
                        item, button, action, menu = kit
                        if not 0 <= ahead < len(base_layout):
                            continue
                        # Solid tiles are probed one by one; open ground once per kind of tile.
                        kind = (item, ahead) if base_collisions[ahead] else (item, base_layout[ahead])
                        if kind in dug:
                            continue
                        dug.add(kind)
                        moved_state = self._capture()
                        wield(kit)
                        probe = ((action, 1), ("wait", 20))
                        ended, _ = run_route(self.shadow, probe)
                        layout = room_layout(self.shadow)
                        if (not self.volatile and layout != base_layout and ended.mode == "playing"
                                and self.shadow.memory[HEALTH] >= health - tolerance):
                            spot = ahead if layout[ahead] != base_layout[ahead] else next(
                                index for index in range(len(layout)) if layout[index] != base_layout[index])
                            # A dig that opens a blocked tile is named by the tile, so a row of
                            # them can be cleared one by one. An ordinary hole counts once per area.
                            opened_way = self.shadow.memory[COLLISIONS + spot] != base_collisions[spot]
                            where = f":{spot:02x}" if opened_way else ""
                            full = (*menu, *step, *probe)
                            name = f"item:{item:02x}:{layout[spot]:02x}{where}"
                            if name not in found and confirmed(kit, full):
                                add(name, "interact", "Use the item on the ground "
                                    f"{bearing(start, after.x + dx * 16, after.y + dy * 16)}",
                                    full, short="Use the item on the ground")
                        self._load(moved_state)
                    # A step cut short stopped against something: probe it like a blocked step.
                    cut_short = abs(after.x - before.x) + abs(after.y - before.y) < stride - 2
                    # Link slides around round characters, so a walk toward one may never block.
                    if not cut_short and not any(0 < (item["x"] - after.x) * dx + (item["y"] - after.y) * dy <= 26
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
                for kit in kits:
                    item, button, action, menu = kit
                    self._load(blocked)
                    wield(kit)
                    probe = ((action, 1), ("wait", 20))
                    run_route(self.shadow, probe)
                    if self.shadow.memory[HEALTH] < health - tolerance:
                        continue
                    if not self._changed(base_progress, base_layout, "playing"):
                        continue
                    probed = observe(self.shadow)
                    opened = probed.mode == "dialogue"
                    if (event == "moved" and not opened and probed.mode == "playing"
                            and kit in tools and progress(self.shadow) == base_progress):
                        continue  # only the tool hitting open ground; listed with the ground options
                    # The id carries what would happen now. A character with something
                    # new to say is a new option; the same line again is not.
                    # Two different effects on one tile (touching a chest, then opening it)
                    # must not share a name, or the second would never be tried.
                    result = f"text{self._text():04x}" if opened else f"event{self._effect_name(base_progress, base_layout)}"
                    if opened and entity:
                        name = ENTITY_NAMES.get(entity["kind"], "the character")
                        text = f"Talk to {name} {where}"
                    elif opened:
                        text = f"Read or inspect the object {where}"
                    elif entity:
                        text = f"Talk to the character {where}, who reacts"
                    else:
                        text = f"Use the item on the obstacle {where}"
                    brief = ("Talk to the character" if entity else "Read the sign" if opened
                             else "Use the item on the obstacle")
                    full = (*menu, *step, *probe)
# A talk is the same whatever Link holds. An item effect is named by the item.
                    name = f"interact:{target}:{'talk' if opened else f'{item:02x}'}:{result}"
                    if name in found or not confirmed(kit, full):
                        continue
                    add(name, "interact", text, full, short=brief)
                    break
                if not pushes:
                    continue  # the push probe is the slowest; the quick pass leaves it out
                if f"push:{target}:{direction}" in found or push_tries.get((target, direction), 0) >= 2:
                    continue  # known, or tried from two standing spots already
                push_tries[(target, direction)] = push_tries.get((target, direction), 0) + 1
                # Pushing needs Link lined up with the tile. Try as he stands, then nudged
                # to the middle of it. Hold only as long as needed: after the object moves,
                # Link keeps walking, and the next tile may be a pit.
                if dx:
                    offset, sideways = tile[1] * 16 + 8 - after.y, ("down", "up")
                else:
                    offset, sideways = tile[0] * 16 + 8 - after.x, ("right", "left")
                nudges = [()]
                if 0 < abs(offset) <= 8:
                    nudges.append(((sideways[0] if offset > 0 else sideways[1], abs(offset)),))
                for nudge in nudges:
                    for hold in (32, 44, 60):
                        self._load(blocked)
                        probe = (*nudge, (direction, hold), ("wait", 30))
                        pushed, _ = run_route(self.shadow, probe)
                        if self.shadow.memory[HEALTH] < health - tolerance:
                            break
                        if pushed.room != start.room:
                            break  # walked off the screen: that is an exit, not a push
                        if not self._pushed(entity, pushed, base_progress, base_layout):
                            continue
                        if self._hurt_after(health - tolerance):
                            break  # it moved, but Link then walked into a pit
                        # Rule out things that happen anyway, such as a character walking by.
                        self._load(blocked)
                        idle, _ = run_route(self.shadow, (("wait", hold), ("wait", 30)))
                        if not self._pushed(entity, idle, base_progress, base_layout):
                            add(f"push:{target}:{direction}", "push",
                                f"Push the object {where} toward the {COMPASS[direction]}", (*step, *probe),
                                short="Push the object")
                        break
                    if f"push:{target}:{direction}" in found:
                        break
            if route and not responded:
                # Controls that stop answering right after a walk mean a scene is about to start.
                linger(state, route, here)
        # Tools can act on many tiles of a room. Keep the nearest few, so they do not
        # crowd out the rest. The others show up again after these are used.
        tool_uses = sorted((option for option in found.values() if option.short and option.short.startswith(
            "Use the item")), key=lambda option: len(option.route))
        for option in tool_uses[TOOL_OPTIONS:]:
            del found[option.id]
        return list(found.values())
