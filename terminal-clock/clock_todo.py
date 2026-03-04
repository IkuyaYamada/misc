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

_FRAME_INTERVAL = 0.06   # 全エフェクト共通フレーム間隔

# ===== 調整項目 =====
MAX_UNDONE = 10
MAX_DONE = 3
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

def read_tasks(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return [], []

    # 日付ヘッダーを先に全行分解決しておく
    date_map = {}
    current_date = ""
    for i, line in enumerate(lines):
        date_m = DATE_RE.match(line)
        if date_m:
            current_date = date_m.group(1)
        date_map[i] = current_date

    cutoff = (date_type.today() - timedelta(days=FILTER_DAYS)) if FILTER_DAYS > 0 else None

    def within_range(date_str):
        if cutoff is None or not date_str:
            return True
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date() >= cutoff
        except ValueError:
            return True

    # 末尾から走査して最新 MAX_* 件を収集し、最後に逆順にする
    undone, done = [], []
    for i in range(len(lines) - 1, -1, -1):
        line = lines[i]
        m = TASK_RE.match(line)
        if not m:
            continue
        if not within_range(date_map[i]):
            continue
        checkbox = m.group(2).lower()
        entry = (i, line.rstrip("\n"), date_map[i])
        if checkbox == "[ ]" and len(undone) < MAX_UNDONE:
            undone.append(entry)
        elif checkbox in ("[x]", "[X]") and len(done) < MAX_DONE:
            done.append(entry)
        if len(undone) >= MAX_UNDONE and len(done) >= MAX_DONE:
            break

    undone.reverse()
    done.reverse()
    return undone, done

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

def draw_screen(stdscr, path, undone, done, col, row, clock_only=False, items=None):
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
        # 日付1 + 空行1 + 時計5
        block_height = 1 + 1 + len(big)
    else:
        # ===== レイアウト高さ定義 =====
        # 日付1 + 空行1 + 時計5 + 空行2
        # + 見出し1 + 空行1 + MAX_UNDONE
        # + 空行1 + 見出し1 + 空行1 + MAX_DONE
        block_height = (1 + 1 + len(big) + 2
                        + 1 + 1 + MAX_UNDONE
                        + 1 + 1 + 1 + MAX_DONE)

    top = compute_block_top(h, block_height)

    # 日付
    safe_addstr(stdscr, top, (w - len(date_str)) // 2, date_str)

    # 時計
    clock_y = top + 2
    for i, line in enumerate(big):
        safe_addstr(stdscr, clock_y + i, (w - len(line)) // 2, line, curses.A_BOLD)

    if not clock_only:
        def fmt(t):
            return f"{t[2]}  {t[1]}" if t[2] else t[1]

        all_lines = [fmt(t) for t in undone + done]
        content_width = max((len(s) for s in all_lines), default=len("[ ] Undone"))
        content_width = max(content_width, len("[ ] Undone"))
        content_width = min(content_width, w - 4)
        content_x = max(2, (w - content_width) // 2)
        text_width = content_width

        # Undone セクション
        undone_title_y = clock_y + len(big) + 2
        safe_addstr(stdscr, undone_title_y, content_x, "[ ] Undone", curses.A_UNDERLINE)

        undone_y0 = undone_title_y + 2
        for i in range(MAX_UNDONE):
            y = undone_y0 + i
            if y >= h - 1:
                break
            if i < len(undone):
                attr = curses.A_REVERSE if col == 0 and row == i else curses.A_NORMAL
                safe_addstr(stdscr, y, content_x, fmt(undone[i])[:text_width], attr)

        # Done セクション
        done_title_y = undone_y0 + MAX_UNDONE + 1
        safe_addstr(stdscr, done_title_y, content_x, "[x] Done", curses.A_UNDERLINE | curses.A_DIM)

        done_y0 = done_title_y + 2
        for i in range(MAX_DONE):
            y = done_y0 + i
            if y >= h - 1:
                break
            if i < len(done):
                attr = curses.A_REVERSE if col == 1 and row == i else curses.A_DIM
                safe_addstr(stdscr, y, content_x, fmt(done[i])[:text_width], attr)

        footer = "jk/up-down:move  hl/left-right:section  Enter:toggle  q:quit"
    else:
        footer = "q:quit"
    safe_addstr(stdscr, h - 1, (w - len(footer)) // 2, footer, curses.A_DIM)

    stdscr.refresh()

def main_loop(stdscr, path, clock_only=False, particle_count=0,
              snow_count=0, rain_count=0, use_orbit=False, use_plasma=False):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(50)

    col = 0
    row = 0

    undone, done = ([], []) if clock_only else read_tasks(path)

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

    last_sec = None
    next_poll = 0.0
    next_frame = 0.0
    last_mtime = os.path.getmtime(path) if (not clock_only and os.path.exists(path)) else None

    draw_screen(stdscr, path, undone, done, col, row, clock_only, items or None)

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
                    undone, done = read_tasks(path)
                    row = 0
                    need_redraw = True

        if need_redraw:
            draw_screen(stdscr, path, undone, done, col, row, clock_only, items or None)

        ch = stdscr.getch()
        if ch == -1:
            continue

        if ch in (ord("q"), ord("Q")):
            break

        if clock_only:
            continue

        if ch in (curses.KEY_UP, ord("k")):
            row = max(0, row - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            current = undone if col == 0 else done
            row = min(max(0, len(current) - 1), row + 1) if current else 0
        elif ch in (curses.KEY_LEFT, ord("h")):
            col = 0
            row = clamp(row, 0, len(undone) - 1)
        elif ch in (curses.KEY_RIGHT, ord("l")):
            col = 1
            row = clamp(row, 0, len(done) - 1)
        elif ch in (10, 13):
            target = undone if col == 0 else done
            if row < len(target):
                toggle_task(path, target[row][0])
                undone, done = read_tasks(path)
                row = 0

        draw_screen(stdscr, path, undone, done, col, row, clock_only, items or None)

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
    )

if __name__ == "__main__":
    main()
