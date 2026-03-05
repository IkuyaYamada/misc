#!/usr/bin/env python3
import random
import math
import curses

FRAME_INTERVAL = 0.06   # ~16fps

SNOW_COUNT = 40
RAIN_COUNT = 60

_SNOW_CHARS = ['❄', '*', '·', '∘', '⋆', '+']
_RAIN_CHARS = ['│', '|', "'", '·', '`']

# particles.py が color pair 1–6 を使用するため 7–8 を使用
_SNOW_PAIR = 7
_RAIN_PAIR = 8

_color_attrs_snow: list = []
_color_attrs_rain: list = []


def init_colors() -> None:
    """curses.wrapper 内で一度だけ呼ぶ。"""
    global _color_attrs_snow, _color_attrs_rain
    if not curses.has_colors():
        _color_attrs_snow = [curses.A_DIM, curses.A_NORMAL]
        _color_attrs_rain = [curses.A_DIM, curses.A_NORMAL]
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    curses.init_pair(_SNOW_PAIR, curses.COLOR_BLUE, bg)
    curses.init_pair(_RAIN_PAIR, curses.COLOR_CYAN, bg)
    _color_attrs_snow = [
        curses.color_pair(_SNOW_PAIR) | curses.A_DIM,
        curses.color_pair(_SNOW_PAIR),
    ]
    _color_attrs_rain = [
        curses.color_pair(_RAIN_PAIR) | curses.A_DIM,
        curses.color_pair(_RAIN_PAIR),
        curses.color_pair(_RAIN_PAIR) | curses.A_BOLD,
    ]


class Snowflake:
    def __init__(self, h: int, w: int, rain: bool = False) -> None:
        self.rain = rain
        self._t = 0.0
        self._spawn(h, w, initial=True)

    def _spawn(self, h: int, w: int, initial: bool = False) -> None:
        self.x = random.uniform(0, w - 1)
        self.y = random.uniform(0, h - 1) if initial else 0.0
        if self.rain:
            self.vy = random.uniform(0.8, 1.6)
            self.vx = random.uniform(-0.04, 0.04)
            self.char = random.choice(_RAIN_CHARS)
            self.attr = (random.choice(_color_attrs_rain)
                         if _color_attrs_rain else curses.A_DIM)
        else:
            self.vy = random.uniform(0.07, 0.22)
            self.drift_amp = random.uniform(0.2, 0.8)
            self.drift_freq = random.uniform(0.3, 1.2)
            self.drift_phase = random.uniform(0, 2 * math.pi)
            self.char = random.choice(_SNOW_CHARS)
            self.attr = (random.choice(_color_attrs_snow)
                         if _color_attrs_snow else curses.A_DIM)

    def update(self, h: int, w: int) -> None:
        self._t += 1
        self.y += self.vy
        if self.rain:
            self.x += self.vx
        else:
            self.x += (math.sin(self.drift_phase + self._t * self.drift_freq * 0.08)
                       * 0.12 * self.drift_amp)

        if self.y >= h - 1:
            self._spawn(h, w)
            self._t = 0.0

        # 横はループ
        self.x %= w

    def draw(self, stdscr: "curses._CursesWindow") -> None:
        ix, iy = int(self.x), int(self.y)
        try:
            stdscr.addstr(iy, ix, self.char, self.attr)
        except curses.error:
            pass


def make_snow(h: int, w: int, count: int = SNOW_COUNT) -> list:
    return [Snowflake(h, w, rain=False) for _ in range(count)]


def make_rain(h: int, w: int, count: int = RAIN_COUNT) -> list:
    return [Snowflake(h, w, rain=True) for _ in range(count)]
