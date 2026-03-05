#!/usr/bin/env python3
"""Paris cityscape with filled-body braille figure."""
import random
import math
import curses
from drawille import Canvas

_CITY_PAIR   = 10
_FIGURE_PAIR = 11
_BUBBLE_PAIR = 12

_attr_city   = curses.A_NORMAL
_attr_figure = curses.A_BOLD
_attr_bubble = curses.A_BOLD


def init_colors() -> None:
    global _attr_city, _attr_figure, _attr_bubble
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK
    curses.init_pair(_CITY_PAIR,   curses.COLOR_WHITE,  bg)
    curses.init_pair(_FIGURE_PAIR, curses.COLOR_YELLOW, bg)
    curses.init_pair(_BUBBLE_PAIR, curses.COLOR_CYAN,   bg)
    _attr_city   = curses.color_pair(_CITY_PAIR)
    _attr_figure = curses.color_pair(_FIGURE_PAIR) | curses.A_BOLD
    _attr_bubble = curses.color_pair(_BUBBLE_PAIR)


# ---- Eiffel Tower ----
_EIFFEL = [
    "    *    ",
    "    |    ",
    "   /|\\   ",
    "   |||   ",
    "  / | \\  ",
    " /  |  \\ ",
    "/   |   \\",
]
_EIFFEL_W = 9


def _eiffel_heights() -> list:
    total = len(_EIFFEL)
    heights = []
    for c in range(_EIFFEL_W):
        first = total
        for r, line in enumerate(_EIFFEL):
            if c < len(line) and line[c] != ' ':
                first = r
                break
        heights.append(max(0, total - first))
    return heights


# ---- Figure geometry constants (braille dot coords) ----
_CDOTS_W  = 24
_CDOTS_H  = 48

_CX       = 12   # figure center x
_HEAD_R   = 3    # head radius
_HEAD_CY  = 6    # head center y (top of head = y 3)
_SHLDR_Y  = 15   # shoulder y
_SHLDR_DX = 5    # shoulder x offset from center
_HIP_Y0   = 27   # hip y (no bob)
_THIGH_L  = 9
_CALF_L   = 10   # slightly long to keep foot near ground when angled
_UPPER_L  = 7
_FORE_L   = 6
# Nominal ground: _HIP_Y0 + _THIGH_L + _CALF_L = 46


# ---- Low-level primitives ----

def _dot(c: Canvas, x: int, y: int) -> None:
    if 0 <= x < _CDOTS_W and 0 <= y < _CDOTS_H:
        c.set(x, y)


def _disc(c: Canvas, cx: int, cy: int, r: int) -> None:
    """Filled circle."""
    for dy in range(-r, r + 1):
        w = int(math.sqrt(max(0, r * r - dy * dy)))
        for dx in range(-w, w + 1):
            _dot(c, cx + dx, cy + dy)


def _capsule(c: Canvas, x1: int, y1: int, x2: int, y2: int, r: int = 1) -> None:
    """Thick line: draw a filled circle at each point along the line."""
    dx, dy = x2 - x1, y2 - y1
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        t = i / steps
        cx = round(x1 + t * dx)
        cy = round(y1 + t * dy)
        if r == 0:
            _dot(c, cx, cy)
        else:
            for oy in range(-r, r + 1):
                w = int(math.sqrt(max(0, r * r - oy * oy)))
                for ox in range(-w, w + 1):
                    _dot(c, cx + ox, cy + oy)


# ---- Body part builders ----

def _draw_head(c: Canvas, cx: int, cy: int) -> None:
    _disc(c, cx, cy, _HEAD_R)


def _draw_torso(c: Canvas, cx: int, neck_top: int, sy: int, hy: int) -> None:
    _capsule(c, cx, neck_top, cx, sy, r=0)                       # neck
    _capsule(c, cx - _SHLDR_DX, sy, cx + _SHLDR_DX, sy, r=0)   # collar
    _capsule(c, cx - _SHLDR_DX, sy, cx - 3, hy, r=1)            # left torso side
    _capsule(c, cx + _SHLDR_DX, sy, cx + 3, hy, r=1)            # right torso side
    _capsule(c, cx - 3, hy, cx + 3, hy, r=0)                    # pelvis


def _draw_arm(c: Canvas, sx: int, sy: int, swing: float) -> None:
    """Two-joint arm. swing: + forward, - backward."""
    ex = sx + int(_UPPER_L * math.sin(swing))
    ey = sy + int(_UPPER_L * math.cos(swing))
    hx = ex + int(_FORE_L * math.sin(swing * 0.6))
    hy = ey + int(_FORE_L * math.cos(swing * 0.6))
    _capsule(c, sx, sy, ex, ey, r=1)
    _capsule(c, ex, ey, hx, hy, r=1)


def _draw_leg(c: Canvas, hx: int, hy: int, phase: float) -> None:
    """Two-joint leg. phase=0: straight down. +: forward, -: backward."""
    thigh_a = math.sin(phase) * 0.42
    kx = hx + int(_THIGH_L * math.sin(thigh_a))
    ky = hy + int(_THIGH_L * math.cos(thigh_a))
    bend   = max(0.0, math.sin(phase)) * 0.38
    calf_a = thigh_a - bend
    fx = kx + int(_CALF_L * math.sin(calf_a))
    fy = ky + int(_CALF_L * math.cos(calf_a))
    _capsule(c, hx, hy, kx, ky, r=2)       # thick thigh
    _capsule(c, kx, ky, fx, fy, r=1)       # thinner calf
    _capsule(c, fx - 1, fy, fx + 3, fy, r=0)  # foot (heel + toe)


# ---- Full pose renders ----

def _walk_rows(phase: float) -> list:
    c = Canvas()
    bob = int(abs(math.sin(phase)) * 2)
    hy  = _HIP_Y0  + bob
    sy  = _SHLDR_Y + bob // 2
    hcy = _HEAD_CY + bob // 3

    _draw_head(c, _CX, hcy)
    _draw_torso(c, _CX, hcy + _HEAD_R, sy, hy)

    swing = math.sin(phase) * 0.38
    _draw_arm(c, _CX - _SHLDR_DX, sy, -swing)
    _draw_arm(c, _CX + _SHLDR_DX, sy,  swing)

    _draw_leg(c, _CX - 2, hy, phase)
    _draw_leg(c, _CX + 2, hy, phase + math.pi)

    return c.rows()


def _think_rows(t: float) -> list:
    c = Canvas()
    _draw_head(c, _CX, _HEAD_CY)
    _draw_torso(c, _CX, _HEAD_CY + _HEAD_R, _SHLDR_Y, _HIP_Y0)

    # Left arm: elbow raised backward, hand at chin
    lsx, lsy = _CX - _SHLDR_DX, _SHLDR_Y      # shoulder (7, 15)
    lex, ley  = _CX - 7, _SHLDR_Y - 7          # elbow backward & up (5, 8)
    lhx, lhy  = _CX - 1, _HEAD_CY + _HEAD_R + 2  # hand at chin (11, 11)
    _capsule(c, lsx, lsy, lex, ley, r=1)
    _capsule(c, lex, ley, lhx, lhy, r=1)

    # Right arm: hanging, gentle breathing sway
    sway = math.sin(t * 1.4) * 0.06
    _draw_arm(c, _CX + _SHLDR_DX, _SHLDR_Y, sway)

    # Relaxed stance
    _draw_leg(c, _CX - 2, _HIP_Y0, -0.08)
    _draw_leg(c, _CX + 2, _HIP_Y0, math.pi + 0.08)

    # Thought dots rising above-right of head
    bx0 = _CX + _HEAD_R + 2
    by0 = _HEAD_CY - _HEAD_R - 1
    for i, (ddx, ddy) in enumerate([(0, 0), (1, -2), (2, -4)]):
        bx, by = bx0 + ddx, by0 + ddy
        if (int(t * 2.5) + i) % 5 < 4:
            _dot(c, bx, by)

    return c.rows()


# ---- State machine ----

class _State:
    WALK  = 0
    THINK = 1


class CityScene:
    SCROLL_SPEED = 0.2
    PHASE_SPEED  = 0.16

    def __init__(self, h: int, w: int) -> None:
        self._scroll = 0.0
        self._phase  = 0.0
        self._t      = 0.0
        self._state  = _State.WALK
        self._timer  = random.randint(120, 280)
        self._hmap: list      = []
        self._landmarks: list = []
        self._extend(w * 3)

    def _extend(self, target: int) -> None:
        while len(self._hmap) < target:
            r = random.random()
            if r < 0.06 and len(self._hmap) > 30:
                col0 = len(self._hmap)
                self._hmap.extend(_eiffel_heights())
                self._landmarks.append((col0, _EIFFEL))
            elif r < 0.15:
                self._hmap.extend([0] * random.randint(1, 3))
            else:
                self._hmap.extend([random.randint(2, 10)] * random.randint(3, 9))

    def update(self, h: int, w: int) -> None:
        self._t     += 1
        self._timer -= 1

        if self._state == _State.WALK:
            self._scroll += self.SCROLL_SPEED
            self._phase   = (self._phase + self.PHASE_SPEED) % (2 * math.pi)
            if self._timer <= 0:
                self._state = _State.THINK
                self._timer = random.randint(80, 160)
        else:
            if self._timer <= 0:
                self._state = _State.WALK
                self._timer = random.randint(120, 280)

        self._extend(int(self._scroll) + w + 60)

    def draw(self, stdscr) -> None:
        h, w = stdscr.getmaxyx()
        ground_y = h - 2
        si = int(self._scroll)

        # buildings
        for sx in range(w - 1):
            mc = si + sx
            if mc < 0 or mc >= len(self._hmap):
                continue
            bh = self._hmap[mc]
            for row in range(bh):
                y = ground_y - row
                if 0 <= y < h - 1:
                    try:
                        stdscr.addstr(y, sx, '\u2588', _attr_city)
                    except curses.error:
                        pass

        # landmark overlays
        for c0, lines in self._landmarks:
            sx0   = c0 - si
            top_y = ground_y - len(lines)
            for dy, line in enumerate(lines):
                y = top_y + dy
                if y < 0 or y >= h - 1:
                    continue
                for dx, ch in enumerate(line):
                    if ch == ' ':
                        continue
                    sx = sx0 + dx
                    if 0 <= sx < w - 1:
                        try:
                            stdscr.addstr(y, sx, ch, _attr_city)
                        except curses.error:
                            pass

        # ground line
        for sx in range(w - 1):
            try:
                stdscr.addstr(ground_y, sx, '\u2500', _attr_city)
            except curses.error:
                pass

        # figure
        if self._state == _State.WALK:
            rows = _walk_rows(self._phase)
        else:
            rows = _think_rows(self._t / 16.0)

        fig_sx  = 8
        fig_by  = ground_y - 1
        fig_top = fig_by - len(rows) + 1

        for i, row_str in enumerate(rows):
            y = fig_top + i
            if y < 0 or y >= h - 1:
                continue
            for dx, ch in enumerate(row_str):
                sx = fig_sx + dx
                if 0 <= sx < w - 1:
                    try:
                        stdscr.addstr(y, sx, ch, _attr_figure)
                    except curses.error:
                        pass

        # thought bubble (terminal chars above braille rows)
        if self._state == _State.THINK:
            tick    = int(self._t / 6)
            dot_str = ['.  ', '.. ', '...'][tick % 3]
            q_y  = fig_top - 1
            q_sx = fig_sx + 7
            if 0 <= q_y < h - 1:
                for dx, ch in enumerate(dot_str + ' ?'):
                    sx = q_sx + dx
                    if 0 <= sx < w - 1:
                        try:
                            attr = _attr_bubble if ch == '?' else _attr_figure
                            stdscr.addstr(q_y, sx, ch, attr)
                        except curses.error:
                            pass


def make_city(h: int, w: int) -> list:
    return [CityScene(h, w)]
