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

def draw_screen(stdscr, path, undone, done, col, row):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d (%a)")
    time_str = now.strftime("%H:%M:%S")
    big = render_big(time_str)

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
    safe_addstr(stdscr, h - 1, (w - len(footer)) // 2, footer, curses.A_DIM)

    stdscr.refresh()

def main_loop(stdscr, path):
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    stdscr.timeout(50)

    col = 0
    row = 0

    undone, done = read_tasks(path)

    last_sec = None
    next_poll = 0
    last_mtime = os.path.getmtime(path) if os.path.exists(path) else None

    draw_screen(stdscr, path, undone, done, col, row)

    while True:
        now = datetime.now()
        if now.second != last_sec:
            last_sec = now.second
            draw_screen(stdscr, path, undone, done, col, row)

        if time.time() > next_poll:
            next_poll = time.time() + FILE_POLL_SEC
            if os.path.exists(path):
                m = os.path.getmtime(path)
                if m != last_mtime:
                    last_mtime = m
                    undone, done = read_tasks(path)
                    row = 0
                    draw_screen(stdscr, path, undone, done, col, row)

        ch = stdscr.getch()
        if ch == -1:
            continue

        if ch in (ord("q"), ord("Q")):
            break

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

        draw_screen(stdscr, path, undone, done, col, row)

def main():
    global FILTER_DAYS
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="./todo.txt")
    parser.add_argument("--days", "-d", type=int, default=FILTER_DAYS,
                        metavar="N", help="直近N日以内のタスクのみ表示 (0=無制限)")
    args = parser.parse_args()
    FILTER_DAYS = args.days
    curses.wrapper(main_loop, args.path)

if __name__ == "__main__":
    main()
