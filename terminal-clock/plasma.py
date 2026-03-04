#!/usr/bin/env python3
import math
import curses

FRAME_INTERVAL = 0.08   # ~12fps（CPU負荷を抑えるため少し遅め）

# color pairs 12–16 を使用（particles:1–6, snow:7–8, orbit:9–11）
_THRESHOLD = 0.25       # これ未満は空白のまま

# (上限値, char, color_pair)  ── 順に薄い→濃い
_LEVELS = [
    (0.40, '·', 12),   # ブルー
    (0.55, '+', 13),   # シアン
    (0.70, '*', 14),   # グリーン
    (0.85, '◆', 15),  # イエロー
]
_TOP_CHAR = '█'
_TOP_PAIR = 16          # ホワイト (BOLD)

_color_map: dict = {}


def init_colors() -> None:
    global _color_map
    if not curses.has_colors():
        return
    curses.start_color()
    try:
        curses.use_default_colors()
        bg = -1
    except Exception:
        bg = curses.COLOR_BLACK

    for pair, color in [
        (12, curses.COLOR_BLUE),
        (13, curses.COLOR_CYAN),
        (14, curses.COLOR_GREEN),
        (15, curses.COLOR_YELLOW),
        (16, curses.COLOR_WHITE),
    ]:
        curses.init_pair(pair, color, bg)
        _color_map[pair] = curses.color_pair(pair)


def _plasma_value(x: int, y: int, t: float) -> float:
    """sin を重ね合わせた 0.0–1.0 の値を返す。"""
    v = (math.sin(x * 0.15 + t)
         + math.sin(y * 0.28 + t * 0.7)
         + math.sin((x + y) * 0.10 + t * 1.3))
    return (v + 3.0) / 6.0   # [-3, 3] → [0, 1]


class Plasma:
    def __init__(self) -> None:
        self._t = 0.0

    def update(self, h: int, w: int) -> None:
        self._t += 0.07

    def draw(self, stdscr: "curses._CursesWindow") -> None:
        h, w = stdscr.getmaxyx()
        for y in range(h - 1):      # 最終行はフッター用に空ける
            for x in range(w - 1):
                v = _plasma_value(x, y, self._t)
                if v < _THRESHOLD:
                    continue

                # レベル判定
                char, pair, bold = _TOP_CHAR, _TOP_PAIR, True
                for upper, c, p in _LEVELS:
                    if v < upper:
                        char, pair, bold = c, p, False
                        break

                attr = _color_map.get(pair, curses.A_DIM) if _color_map else curses.A_DIM
                if bold:
                    attr |= curses.A_BOLD
                try:
                    stdscr.addstr(y, x, char, attr)
                except curses.error:
                    pass


def make_plasma() -> list:
    return [Plasma()]
