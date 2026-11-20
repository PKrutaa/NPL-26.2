"""Check short controller actions in a headless copy of the current state."""

from heapq import heappop, heappush
from itertools import count
from io import BytesIO

from .adapter import DIRECTIONS, candidates, execute, observe, room_layout


class Lookahead:
    def __init__(self, rom):
        from pyboy import PyBoy

        self.shadow = PyBoy(str(rom), window="null", ram_file=BytesIO(bytes(8192)), sound_volume=0)
        self.shadow.set_emulation_speed(0)

    def directions(self, pyboy, observation, choices):
        if observation.mode != "playing":
            return {}
        state = BytesIO()
        pyboy.save_state(state)
        results = {}
        for action in DIRECTIONS:
            if action in choices:
                state.seek(0)
                self.shadow.load_state(state)
                after, event, _ = execute(self.shadow, action)
                results[action] = {
                    "event": event,
                    "room": after.room,
                    "position": [after.x, after.y],
                }
        return results

    def close(self):
        self.shadow.stop(save=False)

    def path(self, pyboy, destination, *, limit=600, interaction=None, toward=None, across_rooms=False, terrain_tools=False):
        """Search legal controller inputs until a checkpoint predicate holds."""
        def capture(emulator):
            stream = BytesIO()
            emulator.save_state(stream)
            return stream.getvalue()

        initial = observe(pyboy)
        if initial.mode != "playing":
            raise RuntimeError(f"Navegação indisponível em {initial.mode}")

        def location(obs, emulator):
            scale = 8 if across_rooms else 4
            facing = obs.facing if interaction or terrain_tools else None
            terrain = room_layout(emulator) if terrain_tools else None
            return obs.room, obs.x // scale, obs.y // scale, facing, terrain

        sequence = count()
        pending = []

        def enqueue(obs, state, route):
            priority = len(route) + (toward(obs) if toward else 0)
            heappush(pending, (priority, next(sequence), state, route))

        enqueue(initial, capture(pyboy), ())

        if destination(initial):
            return ()
        visited = {location(initial, pyboy)}
        expanded = 0
        while pending and expanded < limit:
            _, _, state, route = heappop(pending)
            self.shadow.load_state(BytesIO(state))
            before = observe(self.shadow)
            expanded += 1
            actions = candidates(before)
            actions = tuple(action for action in actions if action in DIRECTIONS or (
                action == "interact" and interaction
            ))
            if terrain_tools:
                actions += terrain_actions(self.shadow, before)
            for direction in actions:
                self.shadow.load_state(BytesIO(state))
                after, event, _ = execute(self.shadow, direction)
                candidate = (*route, direction)
                if destination(after) or (
                    interaction and direction == "interact" and interaction(self.shadow, after)
                ):
                    return candidate
                if after.mode != "playing" or (not across_rooms and after.room != initial.room):
                    continue
                if event not in ("moved", "room_changed", "terrain_changed") and not (
                    (interaction or terrain_tools) and before.facing != after.facing
                ):
                    continue
                key = location(after, self.shadow)
                if key not in visited:
                    visited.add(key)
                    enqueue(after, capture(self.shadow), candidate)
        raise RuntimeError(f"A busca não encontrou rota após {expanded} estados")


    def overland(self, pyboy, room, *, limit=2500, terrain_tools=False):
        group, index = room.split(":")
        index = int(index, 16)

        def distance(obs):
            current_group, current = obs.room.split(":")
            if current_group != group:
                return 100
            current = int(current, 16)
            dx = (current % 16 - index % 16) * 160 + obs.x - 80
            dy = (current // 16 - index // 16) * 128 + obs.y - 64
            return (abs(dx) + abs(dy)) / 12

        return self.path(pyboy, lambda obs: obs.room == room, limit=limit, toward=distance,
                         across_rooms=True, terrain_tools=terrain_tools)


def terrain_actions(pyboy, obs):
    """Only branch on item use when a matching obstacle is within reach."""
    if obs.mode != "playing" or not obs.facing or obs.collision_quadrants is None:
        return ()
    delta = {"up": (0, -1), "right": (1, 0), "down": (0, 1), "left": (-1, 0)}
    dx, dy = delta[obs.facing]
    layout = room_layout(pyboy)
    targets = set()
    for distance in (4, 8, 12, 16):
        x = (obs.x + dx * distance) // 16
        y = (obs.y + dy * distance) // 16
        if 0 <= x < 10 and 0 <= y < 8:
            targets.add(layout[y * 16 + x])
    equipment = {5: 0xC5, 21: 0xCD}
    return tuple(
        action for action, address in (("use_a", 0xC689), ("use_b", 0xC688))
        if equipment.get(pyboy.memory[address]) in targets
    )
