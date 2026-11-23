"""Find the order of block pushes that opens a way in a room.

Trying pushes one at a time does not solve these rooms: a block pushed the wrong way stays
there until Link leaves, and the room then starts over. The search runs on the tile grid,
with the rules read from the pinned disassembly, so it costs no emulation. The survey then
replays the answer in its copy of the emulator before offering it.
"""

from collections import deque

UP, RIGHT, DOWN, LEFT = "up", "right", "down", "left"
STEP = {UP: (0, -1), RIGHT: (1, 0), DOWN: (0, 1), LEFT: (-1, 0)}
ANY = (UP, RIGHT, DOWN, LEFT)

# data/ages/tile_properties/interactableTiles.s and pushableTiles.s, dungeons and indoors:
# tile -> (directions it can be pushed in, tile it becomes, needs the Power Bracelet).
BLOCKS = {
    0x18: ((UP,), 0x1D, False), 0x19: ((RIGHT,), 0x1D, False), 0x1A: ((DOWN,), 0x1D, False),
    0x1B: ((LEFT,), 0x1D, False), 0x1C: (ANY, 0x1D, False),
    0x2A: (ANY, 0x2A, False), 0x2C: (ANY, 0x2C, False), 0x2D: (ANY, 0x2D, False), 0x2E: (ANY, 0x2E, False),
    0x25: (ANY, 0x25, False), 0x07: (ANY, 0x06, False),
    0x10: (ANY, 0x10, True), 0x11: (ANY, 0x10, True), 0x12: (ANY, 0x10, True), 0x13: (ANY, 0x10, True),
}
FLOOR_UNDER = 0xA0  # what a pushed block leaves behind in these rooms
MAX_STATES = 4000


def reachable(walls, blocks, start, width, height):
    """Cells Link can walk to from `start` without pushing anything."""
    seen, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in STEP.values():
            cell = (x + dx, y + dy)
            if (0 <= cell[0] < width and 0 <= cell[1] < height and cell not in seen
                    and cell not in walls and cell not in blocks):
                seen.add(cell)
                queue.append(cell)
    return seen


def solve(layout, collisions, start, width, height, *, bracelet=False, targets=None, limit=3):
    """Shortest push sequences that let Link reach a place he could not reach before.

    `layout` and `collisions` map (x, y) to the tile and to its collision byte. `targets`
    is the set of cells worth reaching; by default, the walkable cells on the edge of the
    room. Returns up to `limit` solutions, one per newly reached target, as lists of
    ((x, y) of the block, direction). The start state counts every block as pushable
    again, so the caller must pass a room that has not been disturbed.
    """
    movable = {cell: BLOCKS[tile] for cell, tile in layout.items()
               if tile in BLOCKS and (bracelet or not BLOCKS[tile][2])}
    walls = {cell for cell, value in collisions.items() if value and cell not in movable}
    if not movable:
        return []
    if targets is None:
        targets = {cell for cell in layout if cell not in walls and cell not in movable
                   and (cell[0] in (0, width - 1) or cell[1] in (0, height - 1))}
    first = frozenset((cell, layout[cell]) for cell in movable)
    fixed_start = frozenset()
    base = reachable(walls, {cell for cell, _ in first} | fixed_start, start, width, height)
    already = targets & base
    found, claimed = [], set()
    # A state is the blocks that can still move, the blocks that no longer can, and where
    # Link is, named by the smallest cell he can reach.
    queue = deque([(first, fixed_start, start, [])])
    seen = {(first, fixed_start, min(base))}
    while queue and len(seen) < MAX_STATES and len(found) < limit:
        loose, fixed, link, pushes = queue.popleft()
        occupied = {cell for cell, _ in loose} | set(fixed)
        area = reachable(walls, occupied, link, width, height)
        gained = (targets & area) - already - claimed
        if gained and pushes:
            claimed |= gained
            found.append(pushes)
            continue
        for cell, tile in loose:
            for direction in BLOCKS[tile][0]:
                dx, dy = STEP[direction]
                stand = (cell[0] - dx, cell[1] - dy)
                goes = (cell[0] + dx, cell[1] + dy)
                if stand not in area or goes in walls or goes in occupied:
                    continue
                if not (0 <= goes[0] < width and 0 <= goes[1] < height):
                    continue
                becomes = BLOCKS[tile][1]
                rest = frozenset(item for item in loose if item[0] != cell)
                if becomes in BLOCKS and (bracelet or not BLOCKS[becomes][2]):
                    next_loose, next_fixed = rest | {(goes, becomes)}, fixed
                else:
                    next_loose, next_fixed = rest, fixed | {goes}
                # After the push Link stands where the block was.
                after_area = reachable(walls, {c for c, _ in next_loose} | set(next_fixed), cell, width, height)
                key = (next_loose, next_fixed, min(after_area))
                if key not in seen:
                    seen.add(key)
                    queue.append((next_loose, next_fixed, cell, [*pushes, (cell, direction)]))
    return found


def walk(walls, blocks, start, goal, width, height):
    """Cells to step through from `start` to `goal`, both included, or None."""
    previous, queue = {start: None}, deque([start])
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = []
            while cell is not None:
                path.append(cell)
                cell = previous[cell]
            return path[::-1]
        for dx, dy in STEP.values():
            near = (cell[0] + dx, cell[1] + dy)
            if (0 <= near[0] < width and 0 <= near[1] < height and near not in previous
                    and near not in walls and near not in blocks):
                previous[near] = cell
                queue.append(near)
    return None
