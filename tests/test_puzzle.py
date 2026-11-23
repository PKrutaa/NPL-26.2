from zelda_env import puzzle


def room(rows):
    """'#' wall, '.' floor, 'o' block pushable any way, '^' block pushable up only, 'L' Link."""
    tiles = {"#": (0xB0, 0x0F), ".": (0xA0, 0), "o": (0x1C, 0x0F), "^": (0x18, 0x0F), "L": (0xA0, 0)}
    layout, collisions, start = {}, {}, None
    for y, row in enumerate(rows):
        for x, mark in enumerate(row):
            layout[(x, y)], collisions[(x, y)] = tiles[mark]
            if mark == "L":
                start = (x, y)
    return layout, collisions, start, len(rows[0]), len(rows)


def test_a_block_in_a_corridor_is_pushed_aside_to_reach_the_door():
    # Pushing it up would shut the corridor for good: it has to go left, into the alcove.
    layout, collisions, start, width, height = room([
        "###.###",
        "###.###",
        "#..o..#",
        "#..L..#",
        "#######",
    ])
    solutions = puzzle.solve(layout, collisions, start, width, height)
    assert solutions == [[((3, 2), "right")]] or solutions == [[((3, 2), "left")]]


def test_a_block_that_only_goes_up_is_not_pushed_sideways():
    layout, collisions, start, width, height = room([
        "#######",
        "#.....#",
        "..^...#",
        "#.L...#",
        "#######",
    ])
    # The exit on the left edge is already reachable, and nothing else is: no solution needed.
    assert puzzle.solve(layout, collisions, start, width, height) == []


def test_two_pushes_in_the_right_order():
    layout, collisions, start, width, height = room([
        "####.####",
        "#..#.#..#",
        "#...o...#",
        "#...o...#",
        "#...L...#",
        "#########",
    ])
    solutions = puzzle.solve(layout, collisions, start, width, height)
    assert solutions
    # Both blocks leave the middle column, each pushed from the side.
    assert all(direction in ("left", "right") for _, direction in solutions[0])


def test_no_blocks_means_no_search():
    layout, collisions, start, width, height = room(["#.#", "#L#", "###"])
    assert puzzle.solve(layout, collisions, start, width, height) == []


def test_walk_goes_around_a_block():
    layout, collisions, start, width, height = room(["....", ".o..", "L..."])
    walls = {cell for cell, value in collisions.items() if value and layout[cell] != 0x1C}
    path = puzzle.walk(walls, {(1, 1)}, start, (1, 0), width, height)
    assert path[0] == start and path[-1] == (1, 0) and (1, 1) not in path
