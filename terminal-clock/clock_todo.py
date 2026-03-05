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
import subprocess
import unicodedata
from datetime import datetime, timedelta, date as date_type
from particles import init_colors as _particle_init_colors, make_particles
from snow import init_colors as _snow_init_colors, make_snow, make_rain
from orbit import init_colors as _orbit_init_colors, make_orbits
from plasma import init_colors as _plasma_init_colors, make_plasma
from city import init_colors as _city_init_colors, make_city

_FRAME_INTERVAL = 0.06   # 全エフェクト共通フレーム間隔

# ===== 調整項目 =====
MAX_BLOCK_TASKS = 200  # 1ブロック内の最大表示タスク数（スクロールで対応）
BLOCK_WIDTH     = 62   # TODOブロックの固定横幅（折り返し基準）
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

TASK_RE  = re.compile(r'^(\s*[-*]\s*)(\[[ xX]\])(\s*.*)$')
URL_RE   = re.compile(r'https?://\S+')
DATE_RE = re.compile(r'^# (\d{4}-\d{2}-\d{2})(?:\s+(\d{1,2}:\d{2}))?\s*(.*)')

def render_big(text):
    rows = [""] * 5
    for ch in text:
        pattern = BIG_DIGITS.get(ch, ["     "] * 5)
        for i in range(5):
            rows[i] += pattern[i] + "  "
    return rows

def read_blocks(path):
    """日付ブロック単位でタスクを読み込む。新しい順に返す。
    戻り値: [(date_str, topic_str, [(line_idx, raw_line), ...]), ...]
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return []

    blocks = []
    current_date = None
    current_time = ""
    current_title = ""
    current_tasks = []

    for i, line in enumerate(lines):
        date_m = DATE_RE.match(line)
        if date_m:
            if current_date is not None:
                blocks.append((current_date, current_time, current_title, current_tasks[:]))
            current_date  = date_m.group(1)
            current_time  = (date_m.group(2) or "").strip()
            current_title = (date_m.group(3) or "").strip()
            current_tasks = []
        elif line.strip():
            current_tasks.append((i, line.rstrip("\n")))

    if current_date is not None:
        blocks.append((current_date, current_time, current_title, current_tasks[:]))

    if FILTER_DAYS > 0:
        cutoff = (date_type.today() - timedelta(days=FILTER_DAYS)).strftime("%Y-%m-%d")
        blocks = [(d, tm, tt, t) for d, tm, tt, t in blocks if not d or d >= cutoff]

    blocks.sort(key=lambda b: f"{b[0]} {b[1]}", reverse=True)
    return blocks

def open_url(raw):
    """行テキストから最初のURLを取り出して xdg-open で開く"""
    m = URL_RE.search(raw)
    if not m:
        return
    url = m.group(0).rstrip(")")  # 末尾の ) を除去（Markdown リンク対策）
    subprocess.Popen(["xdg-open", url],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

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

_CLOCK_ROWS = 5  # render_big は常に5行（clock_only モード用）

def _layout(h):
    """画面高さから固定レイアウト定数を計算して返す。
    (top, clock_y, header_y, todo_y0, todo_visible)
    top      : 日付+時刻行
    clock_y  : 大時計開始行
    header_y : ブロック日付ヘッダー行
    todo_y0  : タスクコンテンツ開始行
    """
    top      = max(3, min(8, h // 6))   # 上寄り（h=24→4, h=40→6, h=50→8）
    clock_y  = top + 2
    header_y = clock_y + _CLOCK_ROWS + 2
    todo_y0  = header_y + 3             # ヘッダー + トピック + 空行
    visible  = max(1, h - 1 - top - todo_y0)  # 上余白(top行) = 下余白(top行)
    return top, clock_y, header_y, todo_y0, visible

def clamp_scroll(scroll_offset, task_row, flat, visible_rows):
    """flat リストと task_row を使い scroll_offset を調整して返す。
    flat は (item_idx, ...) のリスト。"""
    if not flat:
        return 0
    # task_row に対応する flat 上の最初・最後の行インデックスを求める
    first = last = None
    for fi, (item_idx, _, _) in enumerate(flat):
        if item_idx == task_row:
            if first is None:
                first = fi
            last = fi
    if first is None:
        return scroll_offset
    # 上に隠れている
    if first < scroll_offset:
        return first
    # 下に隠れている
    if last >= scroll_offset + visible_rows:
        return max(0, last - visible_rows + 1)
    return scroll_offset

def _cw(ch):
    """1文字の端末表示幅（全角=2, 半角=1）"""
    eaw = unicodedata.east_asian_width(ch)
    return 2 if eaw in ('W', 'F') else 1

def display_len(s):
    """文字列の端末表示幅"""
    return sum(_cw(ch) for ch in s)

def display_ljust(s, width):
    """表示幅ベースの left-justify"""
    pad = width - display_len(s)
    return s + " " * max(0, pad)

def wrap_line(text, width):
    """表示幅ベースで折り返し、行リストを返す"""
    if not text:
        return [""]
    lines = []
    cur, cur_w = "", 0
    for ch in text:
        w = _cw(ch)
        if cur_w + w > width:
            lines.append(cur)
            cur, cur_w = ch, w
        else:
            cur += ch
            cur_w += w
    lines.append(cur)
    return lines

def item_lines(raw, width):
    """(折り返し行リスト, base_attr, is_task) を返す"""
    m = TASK_RE.match(raw)
    if m:
        done = m.group(2).lower() == "[x]"
        display = f"{m.group(2)} {m.group(3).strip()}"
        attr = curses.A_DIM if done else curses.A_NORMAL
        return wrap_line(display, width), attr, True
    stripped = raw.strip()
    if stripped.startswith("#"):
        return wrap_line(stripped, width), curses.A_BOLD, False
    return wrap_line(stripped, width), curses.A_NORMAL, False


def draw_screen(stdscr, path, blocks, block_idx, task_row, scroll_offset=0,
                clock_only=False, items=None):
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    if items:
        for item in items:
            item.draw(stdscr)

    now = datetime.now()

    time_str = now.strftime("%H:%M:%S")
    big = render_big(time_str)

    top, clock_y, header_y, todo_y0, todo_visible = _layout(h)
    cw = min(BLOCK_WIDTH, w - 4)
    content_x = max(2, (w - cw) // 2)

    if clock_only:
        date_str = now.strftime("%Y-%m-%d (%a)")
        safe_addstr(stdscr, top, (w - len(date_str)) // 2, date_str)
        for i, line in enumerate(big):
            safe_addstr(stdscr, clock_y + i, (w - len(line)) // 2, line, curses.A_BOLD)
        safe_addstr(stdscr, h - 1, (w - 6) // 2, "q:quit", curses.A_DIM)
        stdscr.refresh()
        return

    # 日付 + 時刻（1行、大時計と同じ時刻を横に添える）
    dt_str = now.strftime("%Y-%m-%d (%a)  %H:%M:%S")
    safe_addstr(stdscr, top, (w - len(dt_str)) // 2, dt_str, curses.A_BOLD)

    # 大時計
    for i, line in enumerate(big):
        safe_addstr(stdscr, clock_y + i, (w - len(line)) // 2, line, curses.A_BOLD)

    if blocks:
        blk_date, blk_time, title, tasks = blocks[block_idx]
        n_tasks = min(len(tasks), MAX_BLOCK_TASKS)

        # ヘッダー行: 日付 [時刻] + ブロック位置 + タスク位置
        date_time = f"{blk_date} {blk_time}".strip() if blk_time else (blk_date or "(no date)")
        nav = f"[{block_idx + 1}/{len(blocks)}]"
        pos = f"({task_row + 1}/{n_tasks})" if n_tasks > 0 else ""
        header = f"{date_time}  {nav}  {pos}".rstrip()
        safe_addstr(stdscr, header_y, content_x, header[:cw], curses.A_UNDERLINE)

        # タイトル行（固定表示、スクロールしない）
        if title:
            safe_addstr(stdscr, header_y + 1, content_x, title[:cw], curses.A_BOLD)

        # フラットな表示行リストを構築
        flat = []  # (item_idx, wline, base_attr)
        for i, (_, raw) in enumerate(tasks[:MAX_BLOCK_TASKS]):
            wrapped, base_attr, _ = item_lines(raw, cw)
            for wline in wrapped:
                flat.append((i, wline, base_attr))

        # scroll_offset を補正（cw が確定した後に行う）
        scroll_offset = clamp_scroll(scroll_offset, task_row, flat, todo_visible)

        # スクロールウィンドウ描画
        ind_x = content_x + cw + 1
        n_drawn = 0
        for rel, (item_idx, wline, base_attr) in enumerate(
                flat[scroll_offset: scroll_offset + todo_visible]):
            y = todo_y0 + rel
            if y >= h - 1:
                break
            selected = (item_idx == task_row)
            attr = (base_attr | curses.A_REVERSE) if selected else base_attr
            safe_addstr(stdscr, y, content_x, display_ljust(wline, cw), attr)
            n_drawn += 1

        # スクロールインジケータ
        if scroll_offset > 0:
            safe_addstr(stdscr, todo_y0, ind_x, "↑", curses.A_DIM)
        if scroll_offset + todo_visible < len(flat):
            safe_addstr(stdscr, todo_y0 + n_drawn - 1, ind_x, "↓", curses.A_DIM)

        footer = "h/l:block  j/k:row  Enter:toggle  o:open URL  q:quit"
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

    block_idx     = 0
    task_row      = 0
    scroll_offset = 0

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

    draw_screen(stdscr, path, blocks, block_idx, task_row, scroll_offset,
                clock_only, items or None)

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
                    scroll_offset = 0
                    need_redraw = True

        if need_redraw:
            draw_screen(stdscr, path, blocks, block_idx, task_row, scroll_offset,
                        clock_only, items or None)

        ch = stdscr.getch()
        if ch == -1:
            continue

        if ch in (ord("q"), ord("Q")):
            break

        if clock_only:
            continue

        h_cur, w_cur = stdscr.getmaxyx()
        _, _, _, _, visible = _layout(h_cur)
        cw = min(BLOCK_WIDTH, w_cur - 4)

        if ch == ord("h"):
            # 古いブロックへ（日付をさかのぼる）
            block_idx = min(block_idx + 1, max(0, len(blocks) - 1))
            task_row = 0
            scroll_offset = 0
        elif ch == ord("l"):
            # 新しいブロックへ（日付を進む）
            block_idx = max(block_idx - 1, 0)
            task_row = 0
            scroll_offset = 0
        elif ch == ord("j") or ch == curses.KEY_DOWN:
            if blocks:
                n = min(len(blocks[block_idx][3]), MAX_BLOCK_TASKS)
                task_row = min(task_row + 1, max(0, n - 1))
                # scroll_offset は draw_screen 内で clamp_scroll により補正される
        elif ch == ord("k") or ch == curses.KEY_UP:
            if blocks:
                task_row = max(task_row - 1, 0)
        elif ch in (10, 13):
            if blocks:
                _, _, _, tasks = blocks[block_idx]
                if task_row < len(tasks):
                    line_idx, raw = tasks[task_row]
                    if TASK_RE.match(raw):  # タスク行のみトグル
                        toggle_task(path, line_idx)
                        blocks = read_blocks(path)
                        block_idx = clamp(block_idx, 0, max(0, len(blocks) - 1))
        elif ch == ord("o"):
            if blocks:
                _, _, _, tasks = blocks[block_idx]
                if task_row < len(tasks):
                    _, raw = tasks[task_row]
                    open_url(raw)

        draw_screen(stdscr, path, blocks, block_idx, task_row, scroll_offset,
                    clock_only, items or None)

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
