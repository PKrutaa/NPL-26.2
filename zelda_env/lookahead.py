"""Check short controller actions in a headless copy of the current state."""

from collections import deque
from io import BytesIO

from .adapter import DIRECTIONS, candidates, execute, observe


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

    def path(self, pyboy, destination, *, limit=600, interaction=None):
        """Search legal controller inputs until a checkpoint predicate holds."""
        def capture(emulator):
            stream = BytesIO()
            emulator.save_state(stream)
            return stream.getvalue()

        initial = observe(pyboy)
        if initial.mode != "playing":
            raise RuntimeError(f"Navegação indisponível em {initial.mode}")

        def location(obs):
            return obs.x // 4, obs.y // 4, obs.facing if interaction else None

        pending = deque([(capture(pyboy), ())])

        if destination(initial):
            return ()
        visited = {location(initial)}
        expanded = 0
        while pending and expanded < limit:
            state, route = pending.popleft()
            self.shadow.load_state(BytesIO(state))
            before = observe(self.shadow)
            expanded += 1
            actions = (*DIRECTIONS, "interact") if interaction else DIRECTIONS
            for direction in actions:
                if direction not in candidates(before):
                    continue
                self.shadow.load_state(BytesIO(state))
                after, event, _ = execute(self.shadow, direction)
                candidate = (*route, direction)
                if destination(after) or (
                    interaction and direction == "interact" and interaction(self.shadow, after)
                ):
                    return candidate
                if after.mode != "playing" or after.room != initial.room:
                    continue
                if event != "moved" and not (interaction and before.facing != after.facing):
                    continue
                key = location(after)
                if key not in visited:
                    visited.add(key)
                    pending.append((capture(self.shadow), candidate))
        raise RuntimeError(f"A busca não encontrou rota após {expanded} estados")
