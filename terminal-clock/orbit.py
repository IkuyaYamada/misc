#!/usr/bin/env python3
import math
import curses

FRAME_INTERVAL = 0.05   # ~20fps

# (rx_frac, ry_frac, n_particles, speed_rad/frame, chars, color_slot)
# rx/ry は画面サイズに対する比率。ターミナルは横幅が文字2個分の幅なので
# 円っぽく見せるには rx_frac ≈ ry_frac * 2 にする。
_RING_DEFS = [
    (0.20, 0.25,  8,  0.050, ['★', '◆', '○', '◇'],  0),  # 内側  / シアン / 時計回り
    (0.33, 0.20, 10, -0.030, ['✦', '*', '+', '×'],   1),  # 中間  / 黄色  / 反時計回り
    (0.25, 0.38, 12,  0.018, ['·', '∘', '⋆', '•'],  2),  # 外側  / マゼンタ / 遅い
]

_color_attrs: list = [[], [], []]


def init_colors() -> None:
    global _color_attrs
    if not curses.has_colors():
        _color_attrs = [[curses.A_BOLD], [curses.A_NORMAL], [curses.A_DIM]]
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    palette = [
        (9,  curses.COLOR_CYAN),
        (10, curses.COLOR_YELLOW),
        (11, curses.COLOR_MAGENTA),
    ]
    for slot, (pair, color) in enumerate(palette):
        curses.init_pair(pair, color, bg)
        _color_attrs[slot] = [
            curses.color_pair(pair) | curses.A_DIM,
            curses.color_pair(pair),
            curses.color_pair(pair) | curses.A_BOLD,
        ]


class OrbitalParticle:
    def __init__(self, rx_frac: float, ry_frac: float, angle: float,
                 speed: float, char: str, attr: int, cy_bias: int) -> None:
        self.rx_frac = rx_frac
        self.ry_frac = ry_frac
        self.angle = angle
        self.speed = speed
        self.char = char
        self.attr = attr
        self.cy_bias = cy_bias

    def update(self, h: int, w: int) -> None:
        self.angle = (self.angle + self.speed) % (2 * math.pi)

    def draw(self, stdscr: "curses._CursesWindow") -> None:
        h, w = stdscr.getmaxyx()
        cx = w // 2
        cy = h // 2 + self.cy_bias
        rx = max(1, int(self.rx_frac * w))
        ry = max(1, int(self.ry_frac * h))
        x = cx + int(rx * math.cos(self.angle))
        y = cy + int(ry * math.sin(self.angle))
        if 0 <= y < h - 1 and 0 <= x < w - 1:
            try:
                stdscr.addstr(y, x, self.char, self.attr)
            except curses.error:
                pass


def make_orbits(h: int, w: int, cy_bias: int = -2) -> list:
    particles = []
    for rx_frac, ry_frac, n, speed, chars, slot in _RING_DEFS:
        attrs = _color_attrs[slot] if _color_attrs[slot] else [curses.A_NORMAL]
        for i in range(n):
            angle = (2 * math.pi / n) * i
            char = chars[i % len(chars)]
            attr = attrs[i % len(attrs)]
            particles.append(
                OrbitalParticle(rx_frac, ry_frac, angle, speed, char, attr, cy_bias)
            )
    return particles
