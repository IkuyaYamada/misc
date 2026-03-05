#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
==================== 調整パラメータ ====================

MAX_UNDONE
    → 未完了タスクの表示件数
      例: 10 → 15 にすれば15件表示

MAX_DONE
    → 完了タスクの表示件数

FILTER_DAYS
    → 何日以内のタスクのみ表示するか
      0  = 無制限（全期間）
      30 = 直近1か月
      90 = 直近3か月
      180 = 直近半年

CENTER_BIAS_LINES
    → 縦方向の位置調整
      0  = 真ん中
     -2  = やや上（現在値）
     -5  = さらに上寄せ
      +3  = 下寄せ

FILE_POLL_SEC
    → TODOファイルの更新チェック間隔（秒）

block_height 計算式
    → レイアウト全体の高さ定義
      構成を変更した場合はここを調整

=========================================================
"""

import argparse
import curses
import time
import sys
import os
import re
from datetime import datetime, timedelta, date as date_type
from particles import init_colors as _particle_init_colors, make_particles
from snow import init_colors as _snow_init_colors, make_snow, make_rain
from orbit import init_colors as _orbit_init_colors, make_orbits
from plasma import init_colors as _plasma_init_colors, make_plasma
from city import init_colors as _city_init_colors, make_city

_FRAME_INTERVAL = 0.06   # 全エフェクト共通フレーム間隔

# ===== 調整項目 =====
MAX_BLOCK_TASKS = 15   # 1ブロック内の最大表示タスク数
FILTER_DAYS = 0
CENTER_BIAS_LINES = -2
FILE_POLL_SEC = 2.0
# ====================

BIG_DIGITS = {
    "0": [" ███ ", "█   █", "█   █", "█   █", " ███ "],
    "1": ["  █  ", " ██  ", "  █  ", "  █  ", " ███ "],
    "2": [" ███ ", "█   █", "   ██", " ██  ", "█████"],
    "3": ["████ ", "    █", " ███ ", "    █", "████ "],
    "4": ["█  ██", "█  ██", "█████", "   ██", "   ██"],
    "5": ["█████", "█    ", "████ ", "    █", "████ "],
    "6": [" ███ ", "█    ", "████ ", "█   █", " ███ "],
    "7": ["█████", "    █", "   █ ", "  █  ", "  █  "],
    "8": [" ███ ", "█   █", " ███ ", "█   █", " ███ "],
    "9": [" ███ ", "█   █", " ████", "    █", " ███ "],
    ":": ["     ", "  █  ", "     ", "  █  ", "     "],
}

TASK_RE = re.compile(r'^(\s*[-*]\s*)(\[[ xX]\])(\s*.*)$')
DATE_RE = re.compile(r'^# (\d{4}-\d{2}-\d{2})')

def render_big(text):
    rows = [""] * 5
    for ch in text:
        pattern = BIG_DIGITS.get(ch, ["     "] * 5)
        for i in range(5):
            rows[i] += pattern[i] + "  "
    return rows

def read_blocks(path):
    """日付ブロック単位でタスクを読み込む。新しい順に返す。
    戻り値: [(date_str, [(line_idx, raw_line), ...]), ...]
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    blocks = []
    current_date = None
    current_tasks = []

    for i, line in enumerate(lines):
        date_m = DATE_RE.match(line)
        if date_m:
            if current_date is not None:
                blocks.append((current_date, current_tasks[:]))
            current_date = date_m.group(1)
            current_tasks = []
        elif line.strip():  # 空行以外はすべて拾う
            current_tasks.append((i, line.rstrip("\n")))

    if current_date is not None:
        blocks.append((current_date, current_tasks[:]))

    if FILTER_DAYS > 0:
        cutoff = (date_type.today() - timedelta(days=FILTER_DAYS)).strftime("%Y-%m-%d")
        blocks = [(d, t) for d, t in blocks if not d or d >= cutoff]

    blocks.sort(key=lambda b: b[0], reverse=True)
    return blocks

def toggle_task(path, line_index):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    m = TASK_RE.match(lines[line_index])
    if not m:
        return

    prefix, checkbox, rest = m.groups()
    new_checkbox = "[x]" if checkbox.lower() == "[ ]" else "[ ]"
    lines[line_index] = f"{prefix}{new_checkbox}{rest}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(lines)

def clamp(n, lo, hi):
    if hi < lo:
        return lo
    return max(lo, min(hi, n))

def safe_addstr(stdscr, y, x, s, attr=0):
    h, w = stdscr.getmaxyx()
    if y < 0 or y >= h:
        return
    if x < 0:
        s = s[-x:]
        x = 0
    if x >= w:
        return
    s = s[: max(0, w - x)]
    if not s:
        return
    try:
        stdscr.addstr(y, x, s, attr)
    except curses.error:
        pass

def compute_block_top(h, block_height):
    usable_h = max(1, h - 1)
    top = (usable_h - block_height) // 2 + CENTER_BIAS_LINES
    return max(0, top)

def _task_display(raw):
    m = TASK_RE.match(raw)
    if m:
        return f"{m.group(2)} {m.group(3).strip()}"
    return raw.lstrip()


def draw_screen(stdscr, path, blocks, block_idx, task_row, clock_only=False, items=None):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    if items:
        for item in items:
            item.draw(stdscr)

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d (%a)")
    time_str = now.strftime("%H:%M:%S")
    big = render_big(time_str)

    if clock_only:
        block_height = 1 + 1 + len(big)
    else:
        n_tasks = min(len(blocks[block_idx][1]), MAX_BLOCK_TASKS) if blocks else 0
        # 日付1 + 空行1 + 時計5 + 空行2 + ヘッダー1 + 空行1 + タスク数
        block_height = 1 + 1 + len(big) + 2 + 1 + 1 + n_tasks

    top = compute_block_top(h, block_height)

    # 日付
    safe_addstr(stdscr, top, (w - len(date_str)) // 2, date_str)

    # 時計
    clock_y = top + 2
    for i, line in enumerate(big):
        safe_addstr(stdscr, clock_y + i, (w - len(line)) // 2, line, curses.A_BOLD)

    if not clock_only and blocks:
        blk_date, tasks = blocks[block_idx]

        content_width = max((len(raw.strip()) for _, raw in tasks), default=10)
        content_width = max(content_width, len(blk_date) + 12)
        content_width = min(content_width, w - 4)
        content_x = max(2, (w - content_width) // 2)

        # ブロックヘッダー（日付 + ナビ番号）
        header_y = clock_y + len(big) + 2
        nav = f"[{block_idx + 1}/{len(blocks)}]"
        header = f"{blk_date or '(no date)'}  {nav}"
        safe_addstr(stdscr, header_y, content_x, header, curses.A_UNDERLINE)

        # 行一覧（タスク・テキスト混在）
        task_y0 = header_y + 2
        for i, (_, raw) in enumerate(tasks[:MAX_BLOCK_TASKS]):
            y = task_y0 + i
            if y >= h - 1:
                break
            m = TASK_RE.match(raw)
            if m:
                done = m.group(2).lower() == "[x]"
                display = f"{m.group(2)} {m.group(3).strip()}"
                base_attr = curses.A_DIM if done else curses.A_NORMAL
            else:
                display = raw.strip()
                base_attr = curses.A_DIM
            attr = (base_attr | curses.A_REVERSE) if i == task_row else base_attr
            safe_addstr(stdscr, y, content_x, display[:content_width], attr)

        footer = "j/k:block  up/down:task  Enter:toggle  q:quit"
    else:
        footer = "q:quit"
    safe_addstr(stdscr, h - 1, (w - len(footer)) // 2, footer, curses.A_DIM)

    stdscr.refresh()

def main_loop(stdscr, path, clock_only=False, particle_count=0,
              snow_count=0, rain_count=0, use_orbit=False, use_plasma=False,
              use_city=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(50)

    block_idx = 0
    task_row  = 0

    blocks = [] if clock_only else read_blocks(path)

    h, w = stdscr.getmaxyx()
    items: list = []
    if particle_count > 0:
        _particle_init_colors()
        items += make_particles(h, w, particle_count)
    if snow_count > 0:
        _snow_init_colors()
        items += make_snow(h, w, snow_count)
    if rain_count > 0:
        _snow_init_colors()
        items += make_rain(h, w, rain_count)
    if use_orbit:
        _orbit_init_colors()
        items += make_orbits(h, w, cy_bias=CENTER_BIAS_LINES)
    if use_plasma:
        _plasma_init_colors()
        items += make_plasma()
    if use_city:
        _city_init_colors()
        items += make_city(h, w)

    last_sec = None
    next_poll = 0.0
    next_frame = 0.0
    last_mtime = os.path.getmtime(path) if (not clock_only and os.path.exists(path)) else None

    draw_screen(stdscr, path, blocks, block_idx, task_row, clock_only, items or None)

    while True:
        now = datetime.now()
        t = time.time()
        need_redraw = False

        # 毎秒：時計更新
        if now.second != last_sec:
            last_sec = now.second
            need_redraw = True

        # フレーム毎：エフェクト更新
        if items and t >= next_frame:
            next_frame = t + _FRAME_INTERVAL
            h, w = stdscr.getmaxyx()
            for item in items:
                item.update(h, w)
            need_redraw = True

        # TODOファイルポーリング
        if not clock_only and t > next_poll:
            next_poll = t + FILE_POLL_SEC
            if os.path.exists(path):
                m = os.path.getmtime(path)
                if m != last_mtime:
                    last_mtime = m
                    blocks = read_blocks(path)
                    block_idx = clamp(block_idx, 0, max(0, len(blocks) - 1))
                    task_row = 0
                    need_redraw = True

        if need_redraw:
            draw_screen(stdscr, path, blocks, block_idx, task_row, clock_only, items or None)

        ch = stdscr.getch()
        if ch == -1:
            continue

        if ch in (ord("q"), ord("Q")):
            break

        if clock_only:
            continue

        if ch == ord("j"):
            # 新しいブロックへ（リスト先頭方向）
            block_idx = max(block_idx - 1, 0)
            task_row = 0
        elif ch == ord("k"):
            # 古いブロックへ（リスト末尾方向）
            block_idx = min(block_idx + 1, max(0, len(blocks) - 1))
            task_row = 0
        elif ch == curses.KEY_DOWN:
            if blocks:
                task_row = min(task_row + 1, max(0, len(blocks[block_idx][1]) - 1))
        elif ch == curses.KEY_UP:
            task_row = max(task_row - 1, 0)
        elif ch in (10, 13):
            if blocks:
                _, tasks = blocks[block_idx]
                if task_row < len(tasks):
                    line_idx, raw = tasks[task_row]
                    if TASK_RE.match(raw):  # タスク行のみトグル
                        toggle_task(path, line_idx)
                        blocks = read_blocks(path)
                        block_idx = clamp(block_idx, 0, max(0, len(blocks) - 1))

        draw_screen(stdscr, path, blocks, block_idx, task_row, clock_only, items or None)

def main():
    global FILTER_DAYS
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="./todo.txt")
    parser.add_argument("--days", "-d", type=int, default=FILTER_DAYS,
                        metavar="N", help="直近N日以内のタスクのみ表示 (0=無制限)")
    parser.add_argument("--clock-only", "-c", action="store_true",
                        help="時計のみ表示（TODO非表示）")
    parser.add_argument("--particles", "-p", nargs="?", const=30, type=int,
                        metavar="N", help="パーティクル表示 (デフォルト30個)")
    parser.add_argument("--snow", "-s", nargs="?", const=40, type=int,
                        metavar="N", help="雪エフェクト (デフォルト40個)")
    parser.add_argument("--rain", "-r", nargs="?", const=60, type=int,
                        metavar="N", help="雨エフェクト (デフォルト60個)")
    parser.add_argument("--orbit", "-o", action="store_true",
                        help="軌道エフェクト（時計周囲を記号が周回）")
    parser.add_argument("--plasma", action="store_true",
                        help="プラズマ波エフェクト（背景に波紋）")
    parser.add_argument("--walk", "-w", action="store_true",
                        help="パリ街並みと歩く棒人間")
    args = parser.parse_args()
    FILTER_DAYS = args.days
    curses.wrapper(
        main_loop,
        args.path,
        args.clock_only,
        args.particles or 0,
        args.snow or 0,
        args.rain or 0,
        args.orbit,
        args.plasma,
        args.walk,
    )

if __name__ == "__main__":
    main()
