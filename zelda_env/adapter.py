"""Read the pinned Ages US WRAM layout and execute bounded controller inputs."""

from dataclasses import dataclass
from typing import Optional

# Addresses match include/wram.s and include/structs.s in the pinned disassembly.
DIRECTIONS = ("up", "right", "down", "left")
ACTIONS = {
    **{key: f"Walk a short distance {key}" for key in DIRECTIONS},
    "interact": "Press A to talk when facing a nearby character, or advance a textbox",
    "cancel": "Press B to cancel",
    "wait": "Wait briefly without pressing any button",
}


@dataclass(frozen=True)
class Observation:
    mode: str
    room: Optional[str] = None
    x: Optional[int] = None
    y: Optional[int] = None
    facing: Optional[str] = None
    dialogue_ready: bool = False
    dialogue_has_next_page: bool = False
    entities: tuple = ()
    collision_quadrants: Optional[tuple] = None


def observe(pyboy):
    mem = pyboy.memory
    if mem[0xCBCB]:
        return Observation("menu")
    if mem[0xC2EE] != 2 or not mem[1, 0xD000]:
        return Observation("unknown")
    if mem[0xCD00] & 0x0E:
        return Observation("transition")
    x, y = mem[1, 0xD00D], mem[1, 0xD00B]
    direction = mem[1, 0xD008]
    room = f"{mem[0xCC2D]:02x}:{mem[0xCC30]:02x}"
    mode = "playing"
    ready = False
    next_page = False
    if mem[0xCBA0]:
        mode = "dialogue"
        text_state = mem[7, 0xD0C0]
        ready = mem[0xCBA1] == 0 and text_state in (5, 15)
        next_page = ready and text_state == 5
    elif mem[0xCC8A] or mem[0xCC57] == 8 or mem[0xCBC3]:
        mode = "locked"
    # Small rooms use a 16-byte stride for each 10-tile row. The low nibble
    # describes collision quadrants, not whether an action will succeed.
    collisions = None
    if mem[0xCD01] == 1:
        collisions = tuple(
            tuple(value & 15 for value in mem[0xCE00 + row * 16:0xCE0A + row * 16])
            for row in range(8)
        )
    entities = []
    for slot, address in enumerate(range(0xD040, 0xE000, 0x100)):
        if mem[1, address] and mem[1, address + 0x1A] & 0x80:
            ex, ey = mem[1, address + 0x0D], mem[1, address + 0x0B]
            if ex < 160 and ey < 128:
                kind = {0x31: "Impa", 0x39: "monkey"}.get(mem[1, address + 1], "unknown")
                entities.append({"slot": slot, "kind": kind, "x": ex, "y": ey})
    return Observation(
        mode=mode, room=room, x=x, y=y,
        facing=DIRECTIONS[direction] if direction < 4 else None,
        dialogue_ready=ready, dialogue_has_next_page=next_page,
        entities=tuple(entities), collision_quadrants=collisions,
    )


def candidates(observation):
    if observation.mode == "playing":
        return (*DIRECTIONS, "interact", "wait")
    if observation.mode == "dialogue":
        return ("interact", "cancel", "wait")
    return ("wait",)


def execute(pyboy, action, *, render=False, hold_frames=12):
    before = observe(pyboy)
    use_item = action == "use_b" and before.mode == "playing"
    if not use_item and action not in candidates(before):
        raise ValueError(f"Ação indisponível em {before.mode}: {action}")
    key = {"interact": "a", "cancel": "b", "use_b": "b", "wait": None}.get(action, action)
    terrain_before = room_layout(pyboy) if use_item else None
    frames = 0

    def tick():
        nonlocal frames
        if not pyboy.tick(1, render=render):
            raise InterruptedError("Janela do emulador encerrada")
        frames += 1
        return observe(pyboy)

    if key:
        pyboy.button_press(key)
    try:
        for _ in range(hold_frames if action in DIRECTIONS or not key else 1):
            after = tick()
            if after.mode != before.mode or after.room != before.room:
                break
    finally:
        if key:
            pyboy.button_release(key)
    after = tick()
    if use_item:
        for _ in range(18):
            if after.mode != "playing" or after.room != before.room:
                break
            after = tick()
    while after.mode == "transition" and frames < 120:
        after = tick()
    if after.mode == "transition":
        event = "timeout"
    elif before.room and after.room and before.room != after.room:
        event = "room_changed"
    elif before.mode != "dialogue" and after.mode == "dialogue":
        event = "dialogue_opened"
    elif before.mode == "dialogue" and after.mode != "dialogue":
        event = "dialogue_closed"
    elif before.dialogue_has_next_page and not after.dialogue_ready and key in ("a", "b"):
        event = "dialogue_advanced"
    elif use_item and room_layout(pyboy) != terrain_before:
        event = "terrain_changed"
    elif action in DIRECTIONS and after.mode == "playing":
        event = "moved" if (before.x, before.y) != (after.x, after.y) else "blocked"
    else:
        event = "no_change"
    return after, event, frames


def room_layout(pyboy):
    return bytes(pyboy.memory[0xCF00:0xCFC0])


def show_status(pyboy, prefix="Ages"):
    """Update the title of the focused SDL window in this process."""
    from sdl2 import SDL_GetKeyboardFocus, SDL_SetWindowTitle

    window = SDL_GetKeyboardFocus()
    if not window:
        return
    obs = observe(pyboy)
    title = f"{prefix} | frame {pyboy.frame_count} | {obs.mode}"
    if obs.room is not None:
        title += f" | {obs.room} | XY {obs.x},{obs.y} | {obs.facing or '?'}"
    if pyboy.paused:
        title += " | paused"
    SDL_SetWindowTitle(window, title.encode("utf-8"))
