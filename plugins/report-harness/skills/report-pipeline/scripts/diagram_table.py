#!/usr/bin/env python3
"""도식 명세(figures/{슬러그}.json)를 한글 표로 조립한다 — 흐름·비교·체계·일정 4유형 (R089).

그림(PNG) 대신 표로 넣으면 한글에서 글자를 바로 고칠 수 있고 흐려지지 않으며, 같은 내용이 그림보다
낮게 들어간다('26.9.25 시험: 흐름 62.7→49.1mm, 체계 77.8→56.7mm).

  · 카드 = 테두리 셀(머리 음영 + 본문), 카드 사이 = 테두리 없는 셀, 연결선 = 선만 있는 빈 셀
  · 화살표 머리 = 셀 안 삼각형 도형 — 기관 도식 Pool 원본과 같은 방식(hp:polygon을 글자처럼 넣는다).
    셀 테두리·대각선만으로는 속이 빈 선 화살표밖에 못 그린다(Pool 원본 17개 전부 도형, 셀 대각선 0건)
  · 격자는 좌표로 짠다 — 항목마다 (x0, x1, y0, y1)을 주면 경계 좌표를 모아 열·행을 만들고, 덮이지 않은
    칸은 빈 셀, 연결선은 맞닿은 셀 변에 긋는다. 비교형 화살표 몸통처럼 카드 머리 경계와 어긋난 세로 위치를
    행·열 번호로는 나타낼 수 없어서다.

격자 계산은 여기 한 곳이고, hwpx(변환)와 HTML(게이트② 리뷰)은 같은 격자의 두 출력이다. 줄 수 추정은
후처리(postprocess_hwpx)의 측정 모델을 그대로 쓴다.

변환 순서: generate(이미지 주입) → **diagram_table.py** → postprocess_hwpx.py --all(캡션 내장·쪽 추정) → 검증.
표로 바꾼 도식 표에는 첫 셀 이름 표지(postprocess FIGURE_TABLE_NAME)를 달아 후처리가 일반 표 규칙을 걸지 않게 한다.

    diagram_table.py <file.hwpx> --work-dir <작업폴더> --figures-json <판본폴더>/41_figures.json

exit 0: 처리 완료(JSON 보고) | exit 2: 인자·파일·구조 오류
"""
import argparse
import copy
import json
import os
import pathlib
import re
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import postprocess_hwpx as ph          # noqa: E402  (측정 모델·XML 입출력·도식 표 표지 단독 출처)
import render_diagram as rd            # noqa: E402  (도식 색·단계 번호 단독 출처)

qn = ph.qn
TABLE_TYPES = ("flow", "compare", "structure", "timeline")
TABLE_FACE = "맑은 고딕"                # 표 서체 — 셀·캡션과 같다(R023)
LINE = ("SOLID", "0.12 mm", rd.LINE)
GRID = ("SOLID", "0.12 mm", "#BFBFBF")
BUS = ("SOLID", "0.4 mm", rd.NAVY)      # 체계형 연결선
DASH = ("DASH", "0.12 mm", rd.LINE)     # 비교형 이전 칸 — 색 + 점선(흑백 인쇄 두 번째 채널, R090)
ACC = ("SOLID", "0.4 mm", rd.ACCENT_LINE)   # 강조 카드 테두리 — 색 + 굵기
CELL_MARGIN = (283, 283, 141, 141)      # 좌·우·위·아래(HU)
LINE_SPACING = 130                      # 셀 문단 줄 간격(%) — 표 셀과 같다
ARROW_HEAD_ASPECT = 0.55                # 비교도 화살표 머리 폭 ÷ 높이 — 머리는 라벨 높이에서 정한다(f15)
CARD_MARK = "•"                         # 카드 본문 항목 부호
CARD_HANG = 1500                        # 카드 본문 내어쓰기(HU) — 부호 1글자 + 반 칸(10pt 기준). 둘째 줄이 첫 줄 글자와
                                        # 같은 자리에서 시작한다(R093, format-profile §8-1)
STYLES = {                              # 이름: (크기 pt, 굵게, 색)
    "head": (11, True, rd.NAVY), "old_head": (11, True, rd.OLD_TEXT), "body": (10, False, "#111111"),
    "key": (11, True, rd.NAVY), "th": (10.5, True, rd.NAVY), "task": (10, False, "#111111"),
    "bar": (9.5, True, "#FFFFFF"), "band": (10.5, True, "#FFFFFF"),
    "bar_dark": (9.5, True, rd.NAVY), "acc_head": (11, True, "#FFFFFF"),
}


def wants_table(spec):
    """이 명세를 표로 조립하는가 — 4유형이 기본이고, `"render": "image"`면 그림으로 남긴다."""
    return spec.get("type") in TABLE_TYPES and spec.get("render") != "image"


# ---------------------------------------------------------------- 좌표 격자
class Canvas:
    def __init__(self, width):
        self.width, self.items, self.lines = width, [], []

    def add(self, x0, x1, y0, y1, fill=None, sides="", line=LINE, paras=(), valign="CENTER", margin=CELL_MARGIN):
        self.items.append({"x": (x0, x1), "y": (y0, y1), "fill": fill, "own": {k: line for k in sides},
                           "paras": list(paras), "valign": valign, "m": margin})

    def vline(self, x, y0, y1, line=BUS):
        self.lines.append(("v", x, y0, y1, line))

    def hline(self, y, x0, x1, line=BUS):
        self.lines.append(("h", y, x0, x1, line))

    def box(self, x0, x1, y0, y1, y2, head, body, head_fill=rd.HEAD, head_style="head", emphasis=False,
            accent=False, line=LINE):
        """카드 — 머리 [y0, y1] + 본문 [y1, y2]. emphasis면 결과 칸처럼 본문을 가운데·굵게·점 없이.
        accent(명세 `"tone": "accent"`)면 주황 머리 + 굵은 주황 테두리 — 도식당 1곳(R090)."""
        if accent:
            head_fill, head_style, line = rd.ACCENT, "acc_head", ACC
        self.add(x0, x1, y0, y1, fill=head_fill, sides="LRTB", line=line, paras=[("C", head_style, head)])
        if emphasis:
            self.add(x0, x1, y1, y2, sides="LRTB", line=line, paras=[("C", "key", b) for b in body])
        else:
            self.add(x0, x1, y1, y2, sides="LRTB", line=line, valign="TOP", paras=card_items(body))

    def grid(self):
        xs = {0, self.width}
        ys = {0}
        for it in self.items:
            xs.update(it["x"]); ys.update(it["y"])
        for kind, a, b, c, _ in self.lines:
            (xs if kind == "v" else ys).add(a)
            (ys if kind == "v" else xs).update((b, c))
        xs, ys = sorted(xs), sorted(ys)
        xi, yi = {v: i for i, v in enumerate(xs)}, {v: i for i, v in enumerate(ys)}
        cells, covered = [], set()
        for it in self.items:
            c0, c1, r0, r1 = xi[it["x"][0]], xi[it["x"][1]], yi[it["y"][0]], yi[it["y"][1]]
            cells.append({"r": r0, "c": c0, "rs": r1 - r0, "cs": c1 - c0, "fill": it["fill"],
                          "s": {k: it["own"].get(k) for k in "LRTB"}, "paras": it["paras"],
                          "valign": it["valign"], "m": it["m"]})
            covered.update((r, c) for r in range(r0, r1) for c in range(c0, c1))
        for r in range(len(ys) - 1):
            for c in range(len(xs) - 1):
                if (r, c) not in covered:
                    cells.append({"r": r, "c": c, "rs": 1, "cs": 1, "fill": None, "s": dict.fromkeys("LRTB"),
                                  "paras": [], "valign": "CENTER", "m": (0, 0, 0, 0)})

        def edges(x):
            return xs[x["c"]], xs[x["c"] + x["cs"]], ys[x["r"]], ys[x["r"] + x["rs"]]

        def within(a0, a1, b0, b1):          # [a0, a1] ⊂ [b0, b1]
            return b0 <= a0 and a1 <= b1

        # 연결선 — 선분이 지나는 셀 변 양쪽에 긋는다
        for kind, a, b, c, line in self.lines:
            for x in cells:
                x0, x1, y0, y1 = edges(x)
                if kind == "v" and within(y0, y1, b, c):
                    if x1 == a:
                        x["s"]["R"] = line
                    if x0 == a:
                        x["s"]["L"] = line
                if kind == "h" and within(x0, x1, b, c):
                    if y1 == a:
                        x["s"]["B"] = line
                    if y0 == a:
                        x["s"]["T"] = line
        # 카드 테두리 — 맞닿은 이웃 셀의 같은 변에도 적는다(이웃 변이 카드 변 안에 들 때만, 선이 카드 밖으로
        # 번지지 않게). 한글은 맞닿은 두 셀의 선을 각자 그리므로 한쪽만 적으면 굵기·색이 섞일 수 있다
        for a in cells:
            ax0, ax1, ay0, ay1 = edges(a)
            for b in cells:
                if a is b:
                    continue
                bx0, bx1, by0, by1 = edges(b)
                if a["s"]["R"] and bx0 == ax1 and within(by0, by1, ay0, ay1) and not b["s"]["L"]:
                    b["s"]["L"] = a["s"]["R"]
                if a["s"]["L"] and bx1 == ax0 and within(by0, by1, ay0, ay1) and not b["s"]["R"]:
                    b["s"]["R"] = a["s"]["L"]
                if a["s"]["B"] and by0 == ay1 and within(bx0, bx1, ax0, ax1) and not b["s"]["T"]:
                    b["s"]["T"] = a["s"]["B"]
                if a["s"]["T"] and by1 == ay0 and within(bx0, bx1, ax0, ax1) and not b["s"]["B"]:
                    b["s"]["B"] = a["s"]["T"]
        cells.sort(key=lambda x: (x["r"], x["c"]))
        return {"widths": [b - a for a, b in zip(xs, xs[1:])], "heights": [b - a for a, b in zip(ys, ys[1:])],
                "cells": cells}


# ---------------------------------------------------------------- 높이 추정
def card_items(body):
    """카드 본문 항목 문단 — `H`(내어쓰기): 부호는 내어쓰기 칸에 두고 글자는 모든 줄에서 CARD_HANG 뒤에 선다."""
    return [("H", "body", b) for b in body]


def paras_height(paras, width, margin=CELL_MARGIN):
    """셀 문단들이 차지하는 높이(HU) — 후처리와 같은 줄 수 추정(어절 단위)."""
    h = 0
    for p in paras:
        if p[0] == "tri":
            h += p[3]
            continue
        size = STYLES[p[1]][0]
        hang = CARD_HANG if p[0] == "H" else 0      # 내어쓰기 항목은 모든 줄이 부호 칸만큼 좁다
        avail = (width - margin[0] - margin[1] - hang) / 100 * ph.FIT_SLACK
        n = ph.lines_at(ph._weighted_len(p[2]), avail, size, 100, 0, ph.word_lens(p[2]))
        h += n * size * LINE_SPACING
    return int(h + margin[2] + margin[3] + 60)


def tri(direction, w, h, color, align="C"):
    """셀 안 삼각형 도형 — direction right(▶)·down(▼), 폭·높이 HU, align C(가운데)·L(왼쪽 붙임)."""
    return ("tri", direction, w, h, color, align)


# ---------------------------------------------------------------- 4유형 빌더
def _flow(spec, W):
    steps = spec["steps"]
    n, aw = len(steps), 1300
    cw = (W - aw * (n - 1)) // n
    xs = [(i * (cw + aw), i * (cw + aw) + cw) for i in range(n)]
    xs[-1] = (xs[-1][0], W)
    numbered = spec.get("numbered", True)
    heads = [f"{rd.STEP_NUMS[i]} {s.get('head', '')}" if numbered else s.get("head", "") for i, s in enumerate(steps)]
    hh = max(paras_height([("C", "head", h)], x1 - x0) for h, (x0, x1) in zip(heads, xs))
    bh = max(paras_height(card_items(rd._items(s)), x1 - x0) for s, (x0, x1) in zip(steps, xs))
    cv = Canvas(W)
    for (x0, x1), head, s in zip(xs, heads, steps):
        cv.box(x0, x1, 0, hh, hh + bh, head, rd._items(s), accent=s.get("tone") == "accent")
    for i in range(1, n):
        x1 = xs[i - 1][1]
        cv.add(x1, x1 + aw, 0, hh + bh, paras=[tri("right", 700, 1000, rd.NAVY)], margin=(0, 0, 0, 0))
    y = hh + bh
    if spec.get("result"):
        res = spec["result"]
        cv.add(0, W, y, y + 1000, paras=[tri("down", 1700, 700, rd.BLUE)], margin=(0, 0, 0, 0))
        y += 1000
        rh = paras_height([("C", "head", res.get("head", ""))], W)
        rb = paras_height([("C", "key", b) for b in rd._items(res)], W)
        cv.box(0, W, y, y + rh, y + rh + rb, res.get("head", ""), rd._items(res), head_fill=rd.HEAD_STRONG, emphasis=True,
               accent=res.get("tone") == "accent")
    return cv


def arrow_label(text):
    """비교도 화살표 라벨 — 어절마다 한 줄로 세워 몸통을 좁힌다(3어절 이상은 두 줄로 나눈다)."""
    words = text.split()
    if len(words) > 2:
        half = (len(words) + 1) // 2
        words = [" ".join(words[:half]), " ".join(words[half:])]
    return [("C", "band", w) for w in words] or [("C", "band", "")]


def _compare(spec, W):
    """종전(회색 머리) | 블록 화살표 | 이번 기준. 화살표 = 파란 몸통 셀(라벨) + 머리 셀 안 삼각형 도형.
    화살표는 라벨에 맞춘다 — 라벨을 어절마다 세워 몸통 폭을 줄이고, 몸통 높이 = 라벨 높이, 머리 = 몸통 ÷ 0.64
    (몸통:머리 비율은 이미지 도식과 같다). 줄인 폭만큼 좌우 카드가 넓어져 줄바꿈이 준다. 종전에는 머리를 도식
    높이의 84%로 키워 화살표가 카드만큼 컸다('26.9.25 게이트② f15)."""
    left, right = spec["left"], spec["right"]
    label = arrow_label(spec.get("arrow", ""))
    pad = (200, 200, 100, 100)
    size = STYLES["band"][0]
    sw = int(max(ph._weighted_len(p[2]) for p in label) * size * 100 / ph.FIT_SLACK) + pad[0] + pad[1] + 100
    shaft = paras_height(label, sw, pad)
    head_h = int(shaft / 0.64)
    hw = max(int(head_h * ARROW_HEAD_ASPECT), 700)
    cw = (W - sw - hw) // 2
    lx, bx, hx, rx = (0, cw), (cw, cw + sw), (cw + sw, cw + sw + hw), (cw + sw + hw, W)
    hh = max(paras_height([("C", "head", n.get("head", ""))], cw) for n in (left, right))
    bh = max(paras_height(card_items(rd._items(n)), cw) for n in (left, right))
    # 카드가 화살표보다 낮으면 화살표를 자르지 않고 카드 본문을 늘린다 — 자르면 머리 비율(ARROW_HEAD_ASPECT)과 칸 폭이
    # 어긋나고 라벨 칸이 라벨보다 낮아져 한글이 행을 키우며 격자가 틀어진다('26.9.25 코드 리뷰)
    bh = max(bh, head_h + 200 - hh)
    T = hh + bh
    mid = T // 2
    cv = Canvas(W)
    cv.box(*lx, 0, hh, T, left.get("head", ""), rd._items(left), head_fill=rd.HEAD_OLD, head_style="old_head", line=DASH)
    cv.box(*rx, 0, hh, T, right.get("head", ""), rd._items(right), head_fill=rd.HEAD_STRONG,   # 개선 = 진한 머리(R090)
           accent=right.get("tone") == "accent")
    cv.add(*bx, mid - shaft // 2, mid - shaft // 2 + shaft, fill=rd.BLUE_FILL, paras=label, margin=pad)
    cv.add(*hx, 0, T, paras=[tri("right", hw, head_h, rd.BLUE_FILL, align="L")], margin=(0, 0, 0, 0))
    return cv


def _structure(spec, W):
    """층별 카드 + 연결선. 층마다 노드 수의 최소공배수 k로 단위를 나누고, 카드 사이 간격은 테두리 없는 칸."""
    from math import lcm
    levels = spec["levels"]
    k = 1
    for lv in levels:
        k = lcm(k, len(lv))
    gap, unit = 300, W / k
    cv, y, prev = Canvas(W), 0, None
    for li, lv in enumerate(levels):
        span = k // len(lv)
        boxes = [(round(i * span * unit) + gap, round((i + 1) * span * unit) - gap) for i in range(len(lv))]
        centers = [(a + b) // 2 for a, b in boxes]
        if prev is not None:
            half = 420
            for c in prev:
                cv.vline(c, y, y + half)
            if len(set(prev + centers)) > 1:
                cv.hline(y + half, min(prev + centers), max(prev + centers))
            for c in centers:
                cv.vline(c, y + half, y + 2 * half)
            y += 2 * half
        top = li == 0
        hh = max(paras_height([("C", "head", n.get("head", ""))], b - a) for n, (a, b) in zip(lv, boxes))
        bh = max(paras_height([("C", "key", t) for t in rd._items(n)] if n.get("emphasis")
                              else card_items(rd._items(n)), b - a) for n, (a, b) in zip(lv, boxes))
        for n, (a, b) in zip(lv, boxes):
            cv.box(a, b, y, y + hh, y + hh + bh, n.get("head", ""), rd._items(n),
                   head_fill=rd.HEAD_STRONG if (top or n.get("emphasis")) else rd.HEAD, emphasis=bool(n.get("emphasis")),
                   accent=n.get("tone") == "accent")
        y += hh + bh
        prev = centers
    return cv


def _timeline(spec, W):
    periods, rows = spec["periods"], spec["rows"]
    tw = int(W * spec.get("task_ratio", 34) / 100)
    pw = (W - tw) // len(periods)
    xs = [tw + j * pw for j in range(len(periods))] + [W]
    cv = Canvas(W)
    th = max(paras_height([("C", "th", p)], pw) for p in ["추진 과제"] + list(periods))
    cv.add(0, tw, 0, th, fill=rd.HEAD, sides="LRTB", line=GRID, paras=[("C", "th", "추진 과제")])
    for j, p in enumerate(periods):
        cv.add(xs[j], xs[j + 1], 0, th, fill=rd.HEAD, sides="LRTB", line=GRID, paras=[("C", "th", p)])
    y = th
    for row in rows:
        a, b = row.get("span", [0, 0])
        if not (0 <= a <= b < len(periods)):
            raise ValueError("timeline.rows.span 범위 오류")
        h = max(paras_height([("L", "task", row.get("task", ""))], tw), 700)
        cv.add(0, tw, y, y + h, sides="LRTB", line=GRID, paras=[("L", "task", row.get("task", ""))])
        for j in range(len(periods)):
            if j == a:
                st = rd.STATUS.get(row.get("status"), (rd.BLUE_FILL, "#FFFFFF", ""))   # 상태 = 명도 단계 + 라벨(R090)
                label = row.get("note") or st[2]
                style = "bar_dark" if st[1] != "#FFFFFF" else "bar"
                cv.add(xs[a], xs[b + 1], y, y + h, fill=st[0], sides="LRTB", line=GRID,
                       paras=[("C", style, label)] if label else [], margin=(141, 141, 60, 60))
            elif not a <= j <= b:
                cv.add(xs[j], xs[j + 1], y, y + h, sides="LRTB", line=GRID)
        y += h
    return cv


BUILDERS = {"flow": _flow, "compare": _compare, "structure": _structure, "timeline": _timeline}


def layout(spec, width):
    """명세 → 격자 {widths, heights, cells}. width는 표 폭(HU)."""
    if not wants_table(spec):
        raise ValueError(f"표로 조립하지 않는 유형: {spec.get('type')}")
    rd.check_palette_use(spec)
    return BUILDERS[spec["type"]](spec, width).grid()


# ---------------------------------------------------------------- HTML (게이트② 리뷰)
def _css_side(v):
    if not v:
        return "none"
    return f"{v[1].replace(' ', '')} solid {v[2]}"


def html(spec, width=None):
    """리뷰 화면용 <table> — hwpx와 같은 격자·열 폭·행 높이·선·채움, 삼각형은 인라인 SVG."""
    width = width or round(rd.DEFAULT_WIDTH_MM * 7200 / 25.4)       # 본문 표 폭 상한(169mm)과 같게
    g = layout(spec, width)
    total = sum(g["widths"])
    cols = "".join(f'<col style="width:{w / total * 100:.3f}%">' for w in g["widths"])
    rows = {}
    for x in g["cells"]:
        rows.setdefault(x["r"], []).append(x)
    out = []
    for r, h in enumerate(g["heights"]):
        tds = []
        for x in rows.get(r, []):
            s = x["s"]
            m = x["m"]
            style = (f"border-left:{_css_side(s['L'])};border-right:{_css_side(s['R'])};"
                     f"border-top:{_css_side(s['T'])};border-bottom:{_css_side(s['B'])};"
                     f"vertical-align:{x['valign'].lower()};padding:{m[2] / 100:g}pt {m[1] / 100:g}pt {m[3] / 100:g}pt {m[0] / 100:g}pt;"
                     + (f"background:{x['fill']};" if x["fill"] else ""))
            span = (f' rowspan="{x["rs"]}"' if x["rs"] > 1 else "") + (f' colspan="{x["cs"]}"' if x["cs"] > 1 else "")
            tds.append(f'<td{span} style="{style}">{"".join(_html_para(p) for p in x["paras"])}</td>')
        out.append(f'<tr style="height:{h / 100:.2f}pt">{"".join(tds)}</tr>')
    return f'<table class="dgt"><colgroup>{cols}</colgroup>{"".join(out)}</table>'


def _html_para(p):
    if p[0] == "tri":
        _, d, w, h, color, align = p
        pts = f"0,0 {w},{h / 2:g} 0,{h}" if d == "right" else f"0,0 {w},0 {w / 2:g},{h}"
        al = "left" if align == "L" else "center"
        return (f'<div style="text-align:{al};line-height:0"><svg width="{w / 100:g}pt" height="{h / 100:g}pt" '
                f'viewBox="0 0 {w} {h}" style="display:inline-block"><polygon points="{pts}" fill="{color}"/></svg></div>')
    al, st, text = p
    size, bold, color = STYLES[st]
    style = (f'text-align:{"center" if al == "C" else "left"};font-size:{size}pt;'
             f'font-weight:{700 if bold else 400};color:{color};line-height:{LINE_SPACING}%')
    if al == "H":       # 부호를 내어쓰기 폭의 고정 칸에 — 글자폭대로 그리면 1줄과 2줄의 앞이 어긋난다(본문 marker_html과 같다)
        hang = CARD_HANG / 100
        return (f'<div style="{style};padding-left:{hang:g}pt;text-indent:-{hang:g}pt">'
                f'<span style="display:inline-block;width:{hang:g}pt;text-indent:0">{CARD_MARK}</span>{_esc(text)}</div>')
    return f'<div style="{style}">{_esc(text)}</div>'


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def css():
    # border:0 — 리뷰의 일반 표 규칙(위·아래 2px 선)이 도식 표 바깥에 번지면 빈 칸(간격·화살표 열) 위아래까지
    # 선이 이어진다('26.9.25 게이트② f10). 선은 셀마다 준 값만 긋는다 — hwpx 표 테두리(빈 borderFill)와 같다.
    return (".dgt { width:100%; table-layout:fixed; border-collapse:collapse; border:0; margin:0 auto; "
            "font-family:\"맑은 고딕\",\"Malgun Gothic\",\"Apple SD Gothic Neo\",sans-serif; word-break:keep-all; }\n"
            ".dgt td { box-sizing:border-box; overflow:hidden; }\n")


# ---------------------------------------------------------------- hwpx 자원·XML
class _Res:
    """header.xml에 도식 표용 테두리·글자·문단 모양을 더한다(같은 모양은 한 번만)."""

    def __init__(self, header):
        self.h = header
        self.bf, self.cp, self.pp = {}, {}, {}
        self.tab = None
        self.font = ph._ensure_font_face(header, TABLE_FACE)
        self.obj = 1990000000

    def object_id(self):
        self.obj += 1
        return self.obj

    def _next(self, container, tag):
        return str(max((int(e.get("id")) for e in container.findall(tag)), default=0) + 1)

    def border(self, sides, fill):
        key = (tuple(sides[k] for k in "LRTB"), fill)
        if key in self.bf:
            return self.bf[key]
        bfs = self.h.find(f".//{qn('hh', 'borderFills')}")
        i = self._next(bfs, qn("hh", "borderFill"))

        def side(tag, v):
            t, w, c = v or ("NONE", "0.1 mm", "#000000")
            return f'<hh:{tag} type="{t}" width="{w}" color="{c}"/>'
        fb = (f'<hc:fillBrush><hc:winBrush faceColor="{fill}" hatchColor="#000000" alpha="0"/></hc:fillBrush>'
              if fill else "")
        bfs.append(ET.fromstring(
            f'<hh:borderFill xmlns:hh="{ph.NS["hh"]}" xmlns:hc="{ph.NS["hc"]}" id="{i}" threeD="0" shadow="0" '
            f'centerLine="NONE" breakCellSeparateLine="0"><hh:slash type="NONE" Crooked="0" isCounter="0"/>'
            f'<hh:backSlash type="NONE" Crooked="0" isCounter="0"/>{side("leftBorder", sides["L"])}'
            f'{side("rightBorder", sides["R"])}{side("topBorder", sides["T"])}{side("bottomBorder", sides["B"])}'
            f'<hh:diagonal type="SOLID" width="0.1 mm" color="#000000"/>{fb}</hh:borderFill>'))
        bfs.set("itemCnt", str(len(bfs.findall(qn("hh", "borderFill")))))
        self.bf[key] = i
        return i

    def char(self, style):
        if style in self.cp:
            return self.cp[style]
        size, bold, color = STYLES[style]
        props = self.h.find(f".//{qn('hh', 'charProperties')}")
        base = props.find(qn("hh", "charPr"))
        new = copy.deepcopy(base)
        new.set("id", self._next(props, qn("hh", "charPr")))
        new.set("height", str(int(size * 100)))
        new.set("textColor", color)
        for tag in ("bold", "italic", "underline", "strikeout", "outline", "shadow", "emboss", "engrave",
                    "supscript", "subscript"):
            for el in new.findall(qn("hh", tag)):
                new.remove(el)
        fr = new.find(qn("hh", "fontRef"))
        if fr is not None and self.font is not None:
            for lang in ("hangul", "latin", "hanja", "japanese", "other", "symbol", "user"):
                fr.set(lang, self.font)
        if bold:
            ET.SubElement(new, qn("hh", "bold"))
        props.append(new)
        props.set("itemCnt", str(len(props.findall(qn("hh", "charPr")))))
        self.cp[style] = new.get("id")
        return self.cp[style]

    def auto_tab(self):
        """내어쓰기 자동 탭 탭 모양(autoTabLeft=1) — 부호 뒤 탭이 내어쓰기 위치로 간다. 본문 계층 문단과 같은 방식."""
        if self.tab:
            return self.tab
        props = self.h.find(f".//{qn('hh', 'tabProperties')}")
        if props is None:
            ref = self.h.find(f".//{qn('hh', 'refList')}")
            kids = list(ref)
            anchor = ref.find(qn("hh", "charProperties"))
            props = ET.Element(qn("hh", "tabProperties"))
            ref.insert(kids.index(anchor) + 1 if anchor is not None else len(kids), props)
        for tp in props.findall(qn("hh", "tabPr")):
            if tp.get("autoTabLeft") == "1" and tp.get("autoTabRight", "0") == "0" and not len(tp):
                self.tab = tp.get("id")
                return self.tab
        tp = ET.SubElement(props, qn("hh", "tabPr"), {"id": self._next(props, qn("hh", "tabPr")),
                                                      "autoTabLeft": "1", "autoTabRight": "0"})
        props.set("itemCnt", str(len(props.findall(qn("hh", "tabPr")))))
        self.tab = tp.get("id")
        return self.tab

    def para(self, align, spacing, hang=0):
        key = (align, spacing, hang)
        if key in self.pp:
            return self.pp[key]
        props = self.h.find(f".//{qn('hh', 'paraProperties')}")
        new = copy.deepcopy(props.find(qn("hh", "paraPr")))
        new.set("id", self._next(props, qn("hh", "paraPr")))
        for al in new.iter(qn("hh", "align")):
            al.set("horizontal", align)
            al.set("vertical", "BASELINE")
        for mg in new.iter(qn("hh", "margin")):
            for tag in ("intent", "left", "right", "prev", "next"):
                el = mg.find(qn("hc", tag))
                if el is not None:
                    el.set("value", str(-hang) if tag == "intent" else "0")   # 내어쓰기 = left 0·intent -hang(R061과 같은 인코딩)
        if hang:
            new.set("tabPrIDRef", self.auto_tab())
        for ls in new.iter(qn("hh", "lineSpacing")):
            ls.set("type", "PERCENT")
            ls.set("value", str(spacing))
        for hd in new.iter(qn("hh", "heading")):
            hd.set("type", "NONE")
        border = new.find(qn("hh", "border"))
        if border is not None:
            border.set("borderFillIDRef", "1")
            border.set("connect", "0")
        props.append(new)
        props.set("itemCnt", str(len(props.findall(qn("hh", "paraPr")))))
        self.pp[key] = new.get("id")
        return self.pp[key]


def _polygon(d, w, h, color, oid):
    pts = [(0, 0), (w, h // 2), (0, h)] if d == "right" else [(0, 0), (w, 0), (w // 2, h)]
    ident = 'e1="1" e2="0" e3="0" e4="0" e5="1" e6="0"'
    return (f'<hp:polygon xmlns:hp="{ph.NS["hp"]}" xmlns:hc="{ph.NS["hc"]}" id="{oid}" zOrder="0" '
            f'numberingType="PICTURE" textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" '
            f'href="" groupLevel="0" instid="{oid}"><hp:offset x="0" y="0"/><hp:orgSz width="{w}" height="{h}"/>'
            f'<hp:curSz width="{w}" height="{h}"/><hp:flip horizontal="0" vertical="0"/>'
            f'<hp:rotationInfo angle="0" centerX="{w // 2}" centerY="{h // 2}" rotateimage="1"/>'
            f'<hp:renderingInfo><hc:transMatrix {ident}/><hc:scaMatrix {ident}/><hc:rotMatrix {ident}/></hp:renderingInfo>'
            f'<hp:lineShape color="{color}" width="28" style="SOLID" endCap="FLAT" headStyle="NORMAL" tailStyle="NORMAL" '
            f'headfill="1" tailfill="1" headSz="MEDIUM_MEDIUM" tailSz="MEDIUM_MEDIUM" outlineStyle="NORMAL" alpha="0"/>'
            f'<hc:fillBrush><hc:winBrush faceColor="{color}" hatchColor="#000000" alpha="0"/></hc:fillBrush>'
            f'<hp:shadow type="NONE" color="#000000" offsetX="0" offsetY="0" alpha="0"/>'
            + "".join(f'<hc:pt x="{x}" y="{y}"/>' for x, y in pts)
            + f'<hp:sz width="{w}" widthRelTo="ABSOLUTE" height="{h}" heightRelTo="ABSOLUTE" protect="0"/>'
            f'<hp:pos treatAsChar="1" affectLSpacing="0" flowWithText="0" allowOverlap="0" holdAnchorAndSO="0" '
            f'vertRelTo="PARA" horzRelTo="PARA" vertAlign="TOP" horzAlign="LEFT" vertOffset="0" horzOffset="0"/>'
            f'<hp:outMargin left="0" right="0" top="0" bottom="0"/></hp:polygon>')


def table_element(g, res, tid):
    """격자 → <hp:tbl>. 첫 셀 이름에 도식 표 표지를 단다(후처리 제외 판별)."""
    hp = ph.NS["hp"]
    rows = {}
    for x in g["cells"]:
        rows.setdefault(x["r"], []).append(x)
    first = True
    trs = []
    for r in range(len(g["heights"])):
        tcs = []
        for x in rows.get(r, []):
            w = sum(g["widths"][x["c"]:x["c"] + x["cs"]])
            h = sum(g["heights"][x["r"]:x["r"] + x["rs"]])
            ps = []
            for n, p in enumerate(x["paras"]):
                if p[0] == "tri":
                    _, d, tw, th, color, align = p
                    pid = res.para("LEFT" if align == "L" else "CENTER", 100)     # 도형 문단은 줄 간격 100% — 세로 가운데 유지
                    obj = _polygon(d, tw, th, color, res.object_id())
                    ps.append(f'<hp:p paraPrIDRef="{pid}" styleIDRef="0"><hp:run charPrIDRef="{res.char("body")}">'
                              f'{obj}</hp:run></hp:p>')
                elif p[0] == "H":           # 부호 + 탭(내어쓰기 위치로) + 글자 — 부호 글자폭과 무관하게 줄 앞이 맞는다
                    _, st, text = p
                    pid = res.para("LEFT", LINE_SPACING, CARD_HANG)
                    ps.append(f'<hp:p paraPrIDRef="{pid}" styleIDRef="0"><hp:run charPrIDRef="{res.char(st)}">'
                              f'<hp:t>{CARD_MARK}<hp:tab width="{CARD_HANG // 2}" leader="0" type="1"/>{_esc(text)}'
                              f'</hp:t></hp:run></hp:p>')
                else:
                    al, st, text = p
                    pid = res.para("CENTER" if al == "C" else "LEFT", LINE_SPACING)
                    ps.append(f'<hp:p paraPrIDRef="{pid}" styleIDRef="0"><hp:run charPrIDRef="{res.char(st)}">'
                              f'<hp:t>{_esc(text)}</hp:t></hp:run></hp:p>')
            if not ps:
                ps.append(f'<hp:p paraPrIDRef="{res.para("CENTER", LINE_SPACING)}" styleIDRef="0">'
                          f'<hp:run charPrIDRef="{res.char("body")}"/></hp:p>')
            m = x["m"]
            name = ph.FIGURE_TABLE_NAME if first else ""
            first = False
            tcs.append(f'<hp:tc name="{name}" header="0" hasMargin="1" protect="0" editable="1" dirty="0" '
                       f'borderFillIDRef="{res.border(x["s"], x["fill"])}"><hp:subList id="" textDirection="HORIZONTAL" '
                       f'lineWrap="BREAK" vertAlign="{x["valign"]}" linkListIDRef="0" linkListNextIDRef="0" textWidth="0" '
                       f'textHeight="0" hasTextRef="0" hasNumRef="0">{"".join(ps)}</hp:subList>'
                       f'<hp:cellAddr colAddr="{x["c"]}" rowAddr="{x["r"]}"/><hp:cellSpan colSpan="{x["cs"]}" rowSpan="{x["rs"]}"/>'
                       f'<hp:cellSz width="{w}" height="{h}"/><hp:cellMargin left="{m[0]}" right="{m[1]}" top="{m[2]}" bottom="{m[3]}"/></hp:tc>')
        trs.append("<hp:tr>" + "".join(tcs) + "</hp:tr>")
    empty = res.border(dict.fromkeys("LRTB"), None)
    xml = (f'<hp:tbl xmlns:hp="{hp}" xmlns:hc="{ph.NS["hc"]}" id="{tid}" zOrder="0" numberingType="TABLE" '
           f'textWrap="TOP_AND_BOTTOM" textFlow="BOTH_SIDES" lock="0" dropcapstyle="None" pageBreak="NONE" '
           f'repeatHeader="0" rowCnt="{len(g["heights"])}" colCnt="{len(g["widths"])}" cellSpacing="0" '
           f'borderFillIDRef="{empty}" noShading="0"><hp:sz width="{sum(g["widths"])}" widthRelTo="ABSOLUTE" '
           f'height="{sum(g["heights"])}" heightRelTo="ABSOLUTE" protect="0"/><hp:pos treatAsChar="0" '
           f'affectLSpacing="0" flowWithText="1" allowOverlap="0" holdAnchorAndSO="0" vertRelTo="PARA" '
           f'horzRelTo="COLUMN" vertAlign="TOP" horzAlign="RIGHT" vertOffset="0" horzOffset="0"/>'
           f'<hp:outMargin left="0" right="0" top="0" bottom="600"/>'
           f'<hp:inMargin left="0" right="0" top="0" bottom="0"/>{"".join(trs)}</hp:tbl>')
    return ET.fromstring(xml)


def _body_width(sec_root):
    """도식 표 폭 — 본문의 다른 표와 같은 폭(가장 흔한 폭)에 맞추고, 없으면 표 폭 상한(본문 폭 - FIT_PAGE_SLACK, R042).

    본문 폭은 지금 쪽 여백이 아니라 **양식 여백(PAGE_MARGINS)**으로 잰다 — 이 단계는 후처리 앞이라 kordoc 여백
    (18mm)이 남아 있고, 후처리가 20mm로 바꾼다('26.9.25 시험: 지금 여백으로 재면 49041 — 다른 표보다 4.3mm 넓음)."""
    pp = sec_root.find(f".//{qn('hp', 'pagePr')}")
    page_w = int(pp.get("width", "59528")) if pp is not None else 59528
    limit = page_w - int(ph.PAGE_MARGINS["left"]) - int(ph.PAGE_MARGINS["right"]) - ph.FIT_PAGE_SLACK
    widths = [int(t.find(qn("hp", "sz")).get("width", "0")) for t in sec_root.iter(qn("hp", "tbl"))
              if t.find(qn("hp", "sz")) is not None and not ph._is_banner_table(t) and not ph.is_figure_table(t)]
    widths = [w for w in widths if 0 < w <= limit]          # 제목 박스처럼 상한을 넘는 표는 후처리가 줄인다 — 기준에서 뺀다
    return max(set(widths), key=widths.count) if widths else limit


# ---------------------------------------------------------------- 치환
def convert(path, work_dir, figures_json):
    """hwpx의 그림 도식을 표로 바꾼다. 그림 파일·목록 항목도 함께 뺀다."""
    figs = json.loads(pathlib.Path(figures_json).read_text(encoding="utf-8")).get("figures", [])
    with zipfile.ZipFile(path) as z:
        infos = z.infolist()
        data = {i.filename: z.read(i.filename) for i in infos}
    header = ET.fromstring(data["Contents/header.xml"])
    secs = {n: ET.fromstring(data[n]) for n in sorted(data) if ph.SECTION_RE.match(n)}
    res = _Res(header)
    report = {"replaced": [], "kept_image": [], "missing": []}
    tid = 1990000
    for f in figs:
        spec_path = pathlib.Path(work_dir) / "figures" / f"{f.get('slug', '')}.json"
        try:
            spec = json.loads(spec_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            report["kept_image"].append({"slug": f.get("slug"), "why": "명세 없음"})
            continue
        if not wants_table(spec):
            report["kept_image"].append({"slug": f.get("slug"), "why": spec.get("type")})
            continue
        stem = pathlib.Path(f.get("file", "")).stem
        hit = None
        for sec in secs.values():
            for run in sec.iter(qn("hp", "run")):
                for pic in run.findall(qn("hp", "pic")):
                    img = pic.find(f".//{qn('hc', 'img')}")
                    if img is not None and img.get("binaryItemIDRef") == stem:
                        hit = (sec, run, pic)
                        break
                if hit:
                    break
            if hit:
                break
        if not hit:
            report["missing"].append(f.get("slug"))
            continue
        sec, run, pic = hit
        g = layout(spec, _body_width(sec))
        tbl = table_element(g, res, tid)
        tid += 1
        idx = list(run).index(pic)
        run.remove(pic)
        run.insert(idx, tbl)
        _drop_bin(data, stem)
        report["replaced"].append({"slug": f.get("slug"), "type": spec["type"], "rows": len(g["heights"]),
                                   "cols": len(g["widths"]), "height_mm": round(sum(g["heights"]) / 7200 * 25.4, 1)})
    if report["replaced"]:
        data["Contents/header.xml"] = ph.serialize_xml(header)
        for n, root in secs.items():
            data[n] = ph.serialize_xml(root)
        _write(path, infos, data)
    return report


def _drop_bin(data, stem):
    """표로 바꾼 그림의 BinData와 content.hpf 목록 항목을 뺀다(참조가 없는 이미지를 남기지 않는다)."""
    for name in [n for n in data if n.startswith("BinData/") and pathlib.Path(n).stem == stem]:
        del data[name]
    hpf = "Contents/content.hpf"
    if hpf in data:
        text = data[hpf].decode("utf-8")
        data[hpf] = re.sub(r'<opf:item id="' + re.escape(stem) + r'"[^>]*/>', "", text).encode("utf-8")


def _write(path, infos, data):
    tmp_fd, tmp = tempfile.mkstemp(dir=str(pathlib.Path(path).resolve().parent), suffix=".hwpx.tmp")
    os.close(tmp_fd)
    try:
        with zipfile.ZipFile(tmp, "w") as out:
            for info in infos:
                if info.filename in data:
                    zi = copy.copy(info)
                    out.writestr(zi, data[info.filename])
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def main(argv=None):
    ap = argparse.ArgumentParser(description="도식 그림을 한글 표로 바꾼다(R089) — 이미지 주입 뒤, 후처리 앞")
    ap.add_argument("hwpx", help="변환된 hwpx(이미지 주입까지 끝난 것)")
    ap.add_argument("--work-dir", required=True, help="작업폴더(figures/{슬러그}.json 명세)")
    ap.add_argument("--figures-json", required=True, help="render_diagram.py 출력(41_figures.json)")
    a = ap.parse_args(argv)
    try:
        rep = convert(a.hwpx, a.work_dir, a.figures_json)
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, ET.ParseError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 2
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
