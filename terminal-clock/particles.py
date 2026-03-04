#!/usr/bin/env python3
import random
import math
import curses

FRAME_INTERVAL = 0.08   # ~12 fps
PARTICLE_COUNT = 30

_MAX_SPEED = 0.25
_CHARS = ['*', '·', '+', '○', '◆', '★', '✦', '⋆', '∘', '•']
_color_attrs: list = []


def init_colors() -> None:
    """curses.wrapper 内で一度だけ呼ぶ。パーティクル用カラーペアを初期化する。"""
    global _color_attrs
    if not curses.has_colors():
        _color_attrs = [curses.A_DIM, curses.A_NORMAL]
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    palette = [
        curses.COLOR_CYAN,
        curses.COLOR_YELLOW,
        curses.COLOR_GREEN,
        curses.COLOR_MAGENTA,
        curses.COLOR_BLUE,
        curses.COLOR_WHITE,
    ]
    _color_attrs = []
    for i, color in enumerate(palette, start=1):
        curses.init_pair(i, color, bg)
        _color_attrs.append(curses.color_pair(i) | curses.A_DIM)
        _color_attrs.append(curses.color_pair(i))


def _rand_attr() -> int:
    if _color_attrs:
        return random.choice(_color_attrs)
    return curses.A_DIM


class Particle:
    def __init__(self, h: int, w: int) -> None:
        self.x = random.uniform(0, w - 1)
        self.y = random.uniform(0, h - 2)
        speed = random.uniform(0.05, _MAX_SPEED)
        angle = random.uniform(0, 2 * math.pi)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed * 0.5
        self.char = random.choice(_CHARS)
        self.attr = _rand_attr()

    def update(self, h: int, w: int) -> None:
        # Brownian drift
        self.vx += random.gauss(0, 0.008)
        self.vy += random.gauss(0, 0.004)
        # Clamp speed
        speed = math.hypot(self.vx, self.vy)
        if speed > _MAX_SPEED:
            self.vx = self.vx / speed * _MAX_SPEED
            self.vy = self.vy / speed * _MAX_SPEED

        self.x += self.vx
        self.y += self.vy

        if self.x < 0:
            self.x = 0.0
            self.vx = abs(self.vx)
        elif self.x >= w - 1:
            self.x = float(w - 2)
            self.vx = -abs(self.vx)
        if self.y < 0:
            self.y = 0.0
            self.vy = abs(self.vy)
        elif self.y >= h - 1:
            self.y = float(h - 2)
            self.vy = -abs(self.vy)

        # Occasional twinkle
        if random.random() < 0.02:
            self.char = random.choice(_CHARS)
            self.attr = _rand_attr()

    def draw(self, stdscr: "curses._CursesWindow") -> None:
        ix, iy = int(self.x), int(self.y)
        try:
            stdscr.addstr(iy, ix, self.char, self.attr)
        except curses.error:
            pass


def make_particles(h: int, w: int, count: int = PARTICLE_COUNT) -> list:
    return [Particle(h, w) for _ in range(count)]
