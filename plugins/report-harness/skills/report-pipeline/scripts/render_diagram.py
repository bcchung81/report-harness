#!/usr/bin/env python3
"""도식 이미지 — `figures/{슬러그}.json` 명세를 HTML로 조립하고 300dpi PNG로 뜬다. stdlib-only.

배경('26.9.24 사용자 요청): 보고서 본문에 흐름·구조·일정 도식을 "뭉개지지 않게, 적정한 배열과
크기로" 넣고 같은 도식을 HTML 시각화에도 쓰고 싶다는 요구. 표 도식 Pool은 GFM이 셀 병합을
못 해 원형을 재현하지 못했고(실사용 0건), 화살표·연결선이 필요한 흐름·체계도는 표로 그릴 수
없다. 조사('26.9.24) 결론 — 공공 보고서 개념도는 그래프 자동 배치가 아니라 칸 맞춤 배치라
HTML/CSS 격자가 맞고, 원본 하나로 HTML과 hwpx 그림을 함께 얻을 수 있다.

  · **LLM은 명세(JSON 슬롯)만 쓴다** — 배치·색·크기는 이 스크립트가 결정론으로 정한다(매번 같은
    결과여야 하므로 scripts/ 소관).
  · 캡처는 설치된 Chrome·Edge·Chromium 헤드리스를 subprocess로 부른다(pip·npm 불필요). 캔버스를
    CSS px 기준 `폭mm ÷ 25.4 × 96`으로 짜고 배율 300/96로 찍으면 CSS pt가 문서 pt와 같아지고
    결과는 정확히 300dpi다. PNG에 해상도(pHYs)를 기록하므로 `postprocess_hwpx.py`
    `apply_figure_fit`(R088)이 명세 폭 그대로 hwpx에 넣는다.
  · 페이지에는 외부 URL이 없고, 헤드리스 크롬은 실행마다 임시 프로필을 쓴다.
  · 서체는 맑은 고딕(표 서체)을 쓴다. 폰트 파일을 PC 폰트 폴더·설정 `font_dirs`에서 찾아 쓰고,
    없으면 대체 서체로 그린 뒤 `font_fallback`으로 알린다 — 기관 폰트는 저장소에 넣을 수 없다.

명세 형식(`type`별 슬롯)은 references/diagram-pool.md §이미지 도식. `type: image`는 research
그림을 가리키는 참조로, 변환 때 원본 그대로(픽셀 유지) 같은 폴더에 복사한다.
"""
import sys
import os
import re
import json
import html
import shutil
import struct
import zlib
import argparse
import pathlib
import tempfile
import subprocess

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from harness_config import load_config                           # noqa: E402
from postprocess_hwpx import (                                   # noqa: E402  (크기 계산 단독 출처)
    image_pixels, figure_display, FIT_PAGE_SLACK, HU_PER_MM, FIGURE_MAX_H_MM, LABEL_FILL)

BODY_WIDTH_HU = 48190                  # KCA 본문 폭 170mm (format-profile.kca.md)
DEFAULT_WIDTH_MM = round((BODY_WIDTH_HU - FIT_PAGE_SLACK) / HU_PER_MM, 1)   # 169.0 — R042 여유
CSS_DPI, OUT_DPI = 96, 300
FONT_FAMILY = "맑은 고딕"
FONT_ALIASES = {"맑은 고딕", "Malgun Gothic"}
FALLBACK_STACK = '"Apple SD Gothic Neo","Noto Sans KR","Noto Sans CJK KR","NanumGothic",sans-serif'
TYPES = ("flow", "compare", "structure", "timeline", "pdca", "strategy", "stack", "chart", "image")
PDCA_LETTERS = "PDCA"
PDCA_SHADES = ("#1B1760", "#27438f", "#2f63b0", "#006BA6")   # 남색 → 청색 단계 — 흰 글씨를 얹으므로 끝도 4.5:1 이상(R090)

NAVY, BLUE, LINE = "#1B1760", "#0080C0", "#7F8FA6"
# 제목 띠는 연한 바탕 + 남색 굵은 글자('26.9.24 사용자 선택 — 진한 채움은 흑백 인쇄에서 무겁다).
# 표 머리행과 같은 하늘색을 써 본문 표와 한 벌로 읽히게 한다.
HEAD, HEAD_STRONG, HEAD_OLD, OLD_TEXT = "#DCE6F1", "#BDD7EE", "#F2F2F2", "#404040"
STEP_NUMS = "①②③④⑤⑥"
# 도식 배색 역할(R090) — 값의 단일 출처는 format-profile.kca.md '도식 배색', test_value_drift가 대조한다.
# 원칙(KRDS): 글자 명도대비 4.5:1·그래픽 3:1, 강조는 도식당 1곳, 색만으로 정보를 전하지 않는다(두 번째 채널 병기).
# 이전 머리를 #E7E6E6 → #F2F2F2로 옮긴 이유: 개선 머리(#DCE6F1)와 휘도 차가 0.011뿐이라 흑백 인쇄에서 같아 보였다.
BLUE_FILL = "#006BA6"       # 글자를 얹는 청색 채움(흰 글씨 5.75:1) — #0080C0 위 흰 글씨는 4.33:1로 미달, #0080C0은 선·화살표 전용
ACCENT, ACCENT_LINE, ACCENT_SOFT = "#B34700", "#D55E00", "#FBE5D6"   # 강조(채움·흰 글씨 5.5:1 / 테두리 / 옅은 바탕) — 청색의 보색
STATUS = {                  # 일정 막대 상태 — 같은 청색 계열의 명도 3단계(흑백에서도 갈린다) + 글자 라벨
    "done": ("#1B1760", "#FFFFFF", "완료"), "doing": (BLUE_FILL, "#FFFFFF", "진행"), "plan": ("#BDD7EE", "#1B1760", "예정")}
CHART_SERIES = (BLUE_FILL, NAVY, LINE, HEAD_STRONG)   # 차트 계열 순서 — 명도가 번갈아 흑백에서도 갈린다


def _accent_count(obj):
    """`"tone": "accent"`가 몇 곳인가 — 강조는 도식당 1곳(KRDS 강조색 5% 이하 원칙, R090)."""
    if isinstance(obj, dict):
        return (obj.get("tone") == "accent") + sum(_accent_count(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_accent_count(v) for v in obj)
    return 0


def check_palette_use(spec):
    """배색 역할 검사 — 강조 2곳 이상·모르는 tone·status는 거부한다."""
    if _accent_count(spec) > 1:
        raise ValueError("강조(tone: accent)는 도식당 1곳만 — 여러 곳을 강조하면 아무것도 강조되지 않는다")
    for row in spec.get("rows") or []:
        if row.get("status") and row["status"] not in STATUS:
            raise ValueError(f"timeline.rows.status는 {', '.join(STATUS)} 중 하나: {row['status']}")


# ---------------------------------------------------------------------------
# 서체 — 폰트 파일 name 테이블에서 패밀리명을 읽는다
# ---------------------------------------------------------------------------

def font_names(blob):
    """TTF·OTF·TTC의 패밀리·전체 이름 집합(name ID 1·4, UTF-16BE 레코드만)."""
    offsets = [0]
    if blob[:4] == b"ttcf":
        n = struct.unpack(">I", blob[8:12])[0]
        offsets = list(struct.unpack(f">{n}I", blob[12:12 + 4 * n]))
    names = set()
    for base in offsets:
        num = struct.unpack(">H", blob[base + 4:base + 6])[0]
        for i in range(num):
            rec = base + 12 + 16 * i
            tag, _chk, off, _len = struct.unpack(">4sIII", blob[rec:rec + 16])
            if tag != b"name":
                continue
            _fmt, count, strs = struct.unpack(">HHH", blob[off:off + 6])
            for j in range(count):
                pid, _eid, _lid, nid, ln, so = struct.unpack(">HHHHHH", blob[off + 6 + 12 * j:off + 18 + 12 * j])
                if nid in (1, 4) and pid in (0, 3):
                    raw = blob[off + strs + so:off + strs + so + ln]
                    names.add(raw.decode("utf-16-be", "ignore").strip())
    return names


def font_dirs(extra=()):
    home = pathlib.Path.home()
    dirs = list(extra) + [
        home / "Library/Fonts", pathlib.Path("/Library/Fonts"), pathlib.Path("/System/Library/Fonts"),
        pathlib.Path("/System/Library/Fonts/Supplemental"),
        pathlib.Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
        pathlib.Path(os.environ.get("LOCALAPPDATA", str(home))) / "Microsoft/Windows/Fonts",
        home / ".fonts", home / ".local/share/fonts", pathlib.Path("/usr/share/fonts"),
    ]
    return [d for d in dirs if d.is_dir()]


def find_font(aliases=FONT_ALIASES, extra=()):
    """맑은 고딕 폰트 파일 경로(없으면 None). 파일명이 아니라 name 테이블로 판정한다."""
    for d in font_dirs(extra):
        for p in sorted(d.rglob("*")):
            if p.suffix.lower() not in (".ttf", ".otf", ".ttc"):
                continue
            try:
                if font_names(p.read_bytes()) & aliases:
                    return p
            except (OSError, struct.error, IndexError):
                continue
    return None


# ---------------------------------------------------------------------------
# 명세 → HTML 조각
# ---------------------------------------------------------------------------

def _t(s):
    return html.escape(str(s), quote=False)


def _box(node, head_cls="h"):
    """제목 띠 + 본문(목록) 상자. node = {"head": 문자열, "body": [문자열…] 또는 문자열}.
    `"emphasis": true`면 결과 칸과 같은 강조(가운데·굵게·크게, 목록 점 없음)로 그린다('26.9.24 지적)."""
    acc = node.get("tone") == "accent"              # 강조 카드 — 주황 머리 + 굵은 테두리(색 + 두 번째 채널, R090)
    if node.get("emphasis"):
        return _key_box(node, ("h res" if head_cls == "h" else head_cls) + (" acc" if acc else ""), acc)
    body = node.get("body") or []
    if isinstance(body, str):
        body = [body]
    items = "".join(f"<li>{_t(x)}</li>" for x in body)
    inner = f'<ul>{items}</ul>' if items else ""
    box_cls = "box" + (" acc" if acc else "") + (" old" if "old" in head_cls.split() else "")
    return f'<div class="{box_cls}"><div class="{head_cls}{" acc" if acc else ""}">{_t(node.get("head", ""))}</div>' + \
           (f'<div class="b">{inner}</div>' if inner else "") + "</div>"


def _items(node):
    body = node.get("body") or []
    return [body] if isinstance(body, str) else list(body)


def _same_count(nodes, where):
    """같은 줄에 놓이는 카드는 항목 수를 같게 — 2개면 전부 2개('26.9.24 게이트② 지적: 카드마다 2~5개로
    들쭉날쭉하면 도식이 아니라 나열로 읽힌다)."""
    counts = [len(_items(n)) for n in nodes]
    if len(set(counts)) > 1:
        raise ValueError(f"{where} 카드의 항목 수가 다르다 {counts} — 같은 줄 카드는 항목 수를 맞춘다")


def _key_box(node, head_cls="h res", acc=None):
    """결과 칸 — 전하려는 핵심을 개조식 줄로, 가운데·굵게·크게(목록 점 없이)."""
    acc = node.get("tone") == "accent" if acc is None else acc
    if acc and " acc" not in head_cls:
        head_cls += " acc"
    lines = "".join(f'<div class="key">{_t(x)}</div>' for x in _items(node))
    return (f'<div class="box{" acc" if acc else ""}"><div class="{head_cls}">{_t(node.get("head", ""))}</div>'
            f'<div class="b keys">{lines}</div></div>')


def _flow(spec):
    steps = spec.get("steps") or []
    if not 2 <= len(steps) <= 6:
        raise ValueError("flow.steps는 2~6개")
    _same_count(steps, "flow.steps")
    parts = []
    numbered = spec.get("numbered", True)             # 단계 번호 ①②③ (사용자 선택 '26.9.24)
    for i, s in enumerate(steps):
        if i:
            parts.append('<div class="arrow"></div>')
        node = dict(s, head=f'{STEP_NUMS[i]} {s.get("head", "")}') if numbered else s
        parts.append(f'<div class="cell">{_box(node)}</div>')
    out = f'<div class="flow"><div class="row">{"".join(parts)}</div>'
    if spec.get("result"):
        out += f'<div class="down"></div><div class="result">{_key_box(spec["result"])}</div>'
    return out + "</div>"


def _compare(spec):
    left, right = spec.get("left"), spec.get("right")
    if not (left and right):
        raise ValueError("compare는 left·right가 필요")
    _same_count([left, right], "compare.left·right")
    label = _t(spec.get("arrow", ""))
    return (f'<div class="compare"><div class="cell">{_box(left, "h old")}</div>'
            f'<div class="bigarrow"><span>{label}</span></div>'
            f'<div class="cell">{_box(right, "h res")}</div></div>')   # 개선 = 진한 머리(종전과 흑백 휘도 차 0.23, R090)


def _link(upper, lower):
    """두 층 사이 연결선 — 칸 폭이 같으므로 중심 좌표(%)를 계산해 절대 위치로 긋는다."""
    cu = [(2 * i + 1) / (2 * upper) * 100 for i in range(upper)]
    cl = [(2 * j + 1) / (2 * lower) * 100 for j in range(lower)]
    lo, hi = min(cu + cl), max(cu + cl)
    lines = [f'<i class="up" style="left:{c:.3f}%"></i>' for c in cu]
    lines += [f'<i class="dn" style="left:{c:.3f}%"></i>' for c in cl]
    if hi > lo:
        lines.append(f'<i class="bus" style="left:{lo:.3f}%;right:{100 - hi:.3f}%"></i>')
    return f'<div class="link">{"".join(lines)}</div>'


def _structure(spec):
    levels = spec.get("levels") or []
    if not 2 <= len(levels) <= 4 or any(not lv or len(lv) > 6 for lv in levels):
        raise ValueError("structure.levels는 2~4층, 층마다 1~6개")
    for k, lv in enumerate(levels):
        _same_count(lv, f"structure.levels[{k}]")
    out = []
    for k, lv in enumerate(levels):
        if k:
            out.append(_link(len(levels[k - 1]), len(lv)))
        head_cls = "h top" if k == 0 else "h"
        out.append('<div class="level">' + "".join(f'<div class="cell">{_box(n, head_cls)}</div>' for n in lv) + "</div>")
    return f'<div class="structure">{"".join(out)}</div>'


def _timeline(spec):
    periods, rows = spec.get("periods") or [], spec.get("rows") or []
    if not periods or not rows:
        raise ValueError("timeline은 periods·rows가 필요")
    n = len(periods)
    cols = f"grid-template-columns:{spec.get('task_ratio', 34)}% repeat({n},1fr)"
    cells = ['<div class="th">추진 과제</div>'] + [f'<div class="th">{_t(p)}</div>' for p in periods]
    for r, row in enumerate(rows, start=2):
        a, b = row.get("span", [0, 0])
        if not (0 <= a <= b < n):
            raise ValueError(f"timeline.rows[{r - 2}].span 범위 오류")
        cells.append(f'<div class="task" style="grid-row:{r}">{_t(row.get("task", ""))}</div>')
        cells += [f'<div class="slot" style="grid-row:{r};grid-column:{c + 2}"></div>' for c in range(n)]
        st = STATUS.get(row.get("status"))           # 상태는 명도 + 라벨로 — 라벨이 없으면 상태 이름을 쓴다(R090)
        paint = f"background:{st[0]};color:{st[1]};" if st else ""
        label = row.get("note") or (st[2] if st else "")
        cells.append(f'<div class="bar" style="grid-row:{r};grid-column:{a + 2}/{b + 3};{paint}">{_t(label)}</div>')
    return f'<div class="timeline" style="{cols}">{"".join(cells)}</div>'


def _pdca(spec):
    """P→D→C→A 이행체계 — 셰브론 4칸과 칸별 내용, 선택으로 A→P 환류 띠(경영관리 프레임워크 이행체계 틀)."""
    phases = spec.get("phases") or []
    if len(phases) != 4:
        raise ValueError("pdca.phases는 4개(P·D·C·A)")
    _same_count(phases, "pdca.phases")
    cells = []
    for i, ph in enumerate(phases):
        items = "".join(f"<li>{_t(x)}</li>" for x in _items(ph))
        cells.append(f'<div class="ph"><div class="chev" style="background:{PDCA_SHADES[i]}"><b>{PDCA_LETTERS[i]}</b>'
                     f'{_t(ph.get("head", ""))}</div><div class="pb"><ul>{items}</ul></div></div>')
    loop = f'<div class="loop">↻ {_t(spec["feedback"])}</div>' if spec.get("feedback") else ""
    return f'<div class="pdca"><div class="phs">{"".join(cells)}</div>{loop}</div>'


STRATEGY_LABELS = {"vision": "비전", "goals": "경영목표", "pillars": "전략목표", "tasks": "전략과제", "base": "핵심가치"}


def _strategy(spec):
    """전략체계도 — 왼쪽 라벨 칸 + 비전 띠 → 경영목표 → 전략목표 N열 → 전략과제 N열(→ 핵심가치 띠)."""
    pillars = spec.get("pillars") or []
    if not spec.get("vision") or not 2 <= len(pillars) <= 5:
        raise ValueError("strategy는 vision과 pillars 2~5개가 필요")
    _same_count([{"body": p.get("items")} for p in pillars], "strategy.pillars")
    lab = dict(STRATEGY_LABELS, **(spec.get("labels") or {}))
    n = len(pillars)
    row = lambda key, inner: f'<div class="srow"><div class="slab">{_t(lab[key])}</div><div class="sval">{inner}</div></div>'
    out = [row("vision", f'<div class="band vis">{_t(spec["vision"])}</div>')]
    if spec.get("goals"):
        goals = spec["goals"] if isinstance(spec["goals"], list) else [spec["goals"]]
        out.append(row("goals", '<div class="band goal">' + "".join(f"<span>{_t(g)}</span>" for g in goals) + "</div>"))
    grid = f'style="grid-template-columns:repeat({n},1fr)"'
    out.append(row("pillars", f'<div class="sgrid" {grid}>' + "".join(f'<div class="phead">{_t(p.get("head", ""))}</div>' for p in pillars) + "</div>"))
    out.append(row("tasks", f'<div class="sgrid" {grid}>' + "".join(
        '<div class="ptasks">' + "".join(f'<div class="task">{_t(x)}</div>' for x in _items({"body": p.get("items")})) + "</div>"
        for p in pillars) + "</div>"))
    if spec.get("base"):
        out.append(row("base", f'<div class="band base">{_t(spec["base"])}</div>'))
    return f'<div class="strategy">{"".join(out)}</div>'


def _stack(spec):
    """라벨 블록 ▽ 연결 — 블록마다 왼쪽 회색 라벨 칸 + 내용(목록 또는 N열), 블록 사이 ▽(프레임워크 체계표 틀)."""
    blocks = spec.get("blocks") or []
    if not 2 <= len(blocks) <= 6:
        raise ValueError("stack.blocks는 2~6개")
    out = []
    for k, b in enumerate(blocks):
        if k:
            out.append('<div class="sdown"><i></i></div>')
        if b.get("cols"):
            cols = b["cols"]
            if len(cols) > 4:
                raise ValueError("stack 블록의 cols는 4개 이하")
            _same_count(cols, f"stack.blocks[{k}].cols")
            inner = f'<div class="sgrid" style="grid-template-columns:repeat({len(cols)},1fr)">' + "".join(
                _box(c) for c in cols) + "</div>"
        elif b.get("emphasis"):
            inner = '<div class="skey">' + "".join(f'<div class="key">{_t(x)}</div>' for x in _items(b)) + "</div>"
        else:
            inner = '<div class="sbody"><ul>' + "".join(f"<li>{_t(x)}</li>" for x in _items(b)) + "</ul></div>"
        out.append(f'<div class="srow"><div class="slab">{_t(b.get("label", ""))}</div><div class="sval">{inner}</div></div>')
    return f'<div class="stack">{"".join(out)}</div>'


def _num(v):
    return f"{v:,.1f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"


def _chart(spec):
    """인용 차트(R092) — 외부 자료의 시계열·비교 수치를 막대(bar)·꺾은선(line)으로. 인라인 SVG.

    인용 자료라 `source`(research 원본 경로)가 필수다 — 출처 ※ 줄과 팩트체크의 근거. 값은 막대·점마다 숫자로
    적는다(색만으로 읽히지 않게, R090). `highlight`(범주 번호) 한 곳만 강조색."""
    if not spec.get("source"):
        raise ValueError("chart는 인용 자료라 source(research 원본 경로)가 필요하다 — 출처 ※ 줄의 근거")
    cats, series = spec.get("categories") or [], spec.get("series") or []
    if not 2 <= len(cats) <= 12 or not 1 <= len(series) <= 4:
        raise ValueError("chart는 categories 2~12개, series 1~4개")
    for sr in series:
        vals = sr.get("values") or []
        if len(vals) != len(cats) or not all(isinstance(v, (int, float)) for v in vals):
            raise ValueError(f"chart.series '{sr.get('name', '')}'의 values는 범주 수({len(cats)})만큼의 숫자")
    kind, hi, unit = spec.get("kind", "bar"), spec.get("highlight"), spec.get("unit", "")
    W, H, L, R, T, B = 640, 270, 46, 16, 30 if len(series) > 1 else 14, 40
    top = max(v for sr in series for v in sr["values"]) or 1
    top *= 1.18
    pw, ph_ = W - L - R, H - T - B
    gw = pw / len(cats)
    y = lambda v: T + ph_ - v / top * ph_
    el = [f'<line x1="{L}" y1="{T + ph_}" x2="{W - R}" y2="{T + ph_}" stroke="{LINE}" stroke-width="1"/>']
    for k in range(1, 5):                                           # 눈금선 4개 — 옅은 회색
        yy = T + ph_ - ph_ * k / 5
        el.append(f'<line x1="{L}" y1="{yy:.1f}" x2="{W - R}" y2="{yy:.1f}" stroke="#E6E8EA" stroke-width="0.8"/>')
    if unit:
        el.append(f'<text x="{L - 6}" y="{T - 4}" text-anchor="end" font-size="10" fill="#555">({_t(unit)})</text>')
    if isinstance(hi, int) and 0 <= hi < len(cats):                  # 강조 범주 바탕
        el.append(f'<rect x="{L + gw * hi:.1f}" y="{T}" width="{gw:.1f}" height="{ph_}" fill="{ACCENT_SOFT}"/>')
    for i, c in enumerate(cats):
        cx = L + gw * (i + 0.5)
        el.append(f'<text x="{cx:.1f}" y="{T + ph_ + 16}" text-anchor="middle" font-size="11" fill="#111"'
                  f'{" font-weight=\"700\"" if i == hi else ""}>{_t(c)}</text>')
    marks = ("circle", "rect", "diamond", "tri")
    for si, sr in enumerate(series):
        color = CHART_SERIES[si % len(CHART_SERIES)]
        if kind == "line":
            pts = [(L + gw * (i + 0.5), y(v)) for i, v in enumerate(sr["values"])]
            el.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{color}" stroke-width="2"/>')
            for i, (a, b) in enumerate(pts):
                col = ACCENT if (i == hi and len(series) == 1) else color   # 여러 계열이면 강조는 바탕 띠·굵은 글씨로만
                m = marks[si % len(marks)]                           # 계열마다 표식 모양이 달라 흑백에서도 갈린다
                el.append(f'<circle cx="{a:.1f}" cy="{b:.1f}" r="3.6" fill="{col}"/>' if m == "circle" else
                          f'<rect x="{a - 3.4:.1f}" y="{b - 3.4:.1f}" width="6.8" height="6.8" fill="{col}"/>' if m == "rect" else
                          f'<polygon points="{a:.1f},{b - 4.5:.1f} {a + 4.5:.1f},{b:.1f} {a:.1f},{b + 4.5:.1f} {a - 4.5:.1f},{b:.1f}" fill="{col}"/>' if m == "diamond" else
                          f'<polygon points="{a:.1f},{b - 4.5:.1f} {a + 4.5:.1f},{b + 3.5:.1f} {a - 4.5:.1f},{b + 3.5:.1f}" fill="{col}"/>')
                el.append(f'<text x="{a:.1f}" y="{b - 8:.1f}" text-anchor="middle" font-size="10.5" fill="#111">{_num(sr["values"][i])}</text>')
        else:
            bw = gw * 0.72 / len(series)
            for i, v in enumerate(sr["values"]):
                x0 = L + gw * i + gw * 0.14 + bw * si
                col = ACCENT if (i == hi and len(series) == 1) else color   # 계열 색을 지워 구분을 잃지 않게
                el.append(f'<rect x="{x0:.1f}" y="{y(v):.1f}" width="{bw:.1f}" height="{T + ph_ - y(v):.1f}" fill="{col}"/>')
                el.append(f'<text x="{x0 + bw / 2:.1f}" y="{y(v) - 4:.1f}" text-anchor="middle" font-size="10.5" fill="#111"'
                          f'{" font-weight=\"700\"" if i == hi else ""}>{_num(v)}</text>')
    if len(series) > 1:                                             # 범례 — 계열이 둘 이상일 때만
        x = L
        for si, sr in enumerate(series):
            el.append(f'<rect x="{x}" y="4" width="10" height="10" fill="{CHART_SERIES[si % len(CHART_SERIES)]}"/>')
            el.append(f'<text x="{x + 14}" y="13" font-size="11" fill="#111">{_t(sr.get("name", ""))}</text>')
            x += 24 + 11 * len(str(sr.get("name", "")))
    return (f'<div class="chart"><svg viewBox="0 0 {W} {H}" width="100%" role="img" '
            f'aria-label="{_t(spec.get("caption", ""))}">{"".join(el)}</svg></div>')


BUILDERS = {"flow": _flow, "compare": _compare, "structure": _structure, "timeline": _timeline,
            "pdca": _pdca, "strategy": _strategy, "stack": _stack, "chart": _chart}


def css(font_face=""):
    fam = f'"{FONT_FAMILY}","Malgun Gothic",{FALLBACK_STACK}'
    return f"""{font_face}
.dg {{ font-family:{fam}; font-size:11pt; line-height:1.35; color:#111; background:#fff; word-break:keep-all; overflow-wrap:break-word; }}
.dg * {{ box-sizing:border-box; }}
.dg ul {{ margin:0; padding-left:1.1em; }} .dg li {{ margin:0; }}
.dg .box {{ border:1px solid {LINE}; border-radius:3pt; overflow:hidden; background:#fff; height:100%; display:flex; flex-direction:column; }}
.dg .h {{ background:{HEAD}; color:{NAVY}; font-weight:700; text-align:center; padding:3pt 4pt; font-size:11.5pt; border-bottom:1px solid {LINE}; }}
.dg .h.old {{ background:{HEAD_OLD}; color:{OLD_TEXT}; }} .dg .h.res, .dg .h.top {{ background:{HEAD_STRONG}; }}
.dg .box.old {{ border-style:dashed; }}
.dg .box.acc {{ border:2px solid {ACCENT_LINE}; }} .dg .h.acc {{ background:{ACCENT}; color:#fff; border-bottom-color:{ACCENT_LINE}; }}
.dg .b {{ padding:4pt 5pt; background:#fff; flex:1; }}
.dg .b.keys {{ display:flex; flex-direction:column; justify-content:center; gap:2pt; padding:5pt 8pt; }}
.dg .key {{ text-align:center; font-weight:700; font-size:12.5pt; color:{NAVY}; }}
.dg .row, .dg .compare, .dg .level {{ display:flex; align-items:stretch; }}
.dg .cell {{ flex:1 1 0; min-width:0; }}
.dg .level .cell {{ padding:0 4pt; }}
.dg .arrow {{ flex:0 0 12pt; align-self:center; height:0; border-left:9pt solid {NAVY}; border-top:7pt solid transparent; border-bottom:7pt solid transparent; margin:0 3pt; }}
.dg .down {{ width:0; margin:4pt auto; border-top:9pt solid {BLUE}; border-left:12pt solid transparent; border-right:12pt solid transparent; }}
.dg .bigarrow {{ flex:0 0 58pt; display:flex; align-items:center; justify-content:center; }}
.dg .bigarrow span {{ display:flex; align-items:center; justify-content:center; width:100%; min-height:34pt; padding:0 14pt 0 6pt; background:{BLUE_FILL}; color:#fff; font-weight:700; font-size:10pt; text-align:center;
  clip-path:polygon(0 18%, 72% 18%, 72% 0, 100% 50%, 72% 100%, 72% 82%, 0 82%); }}
.dg .link {{ position:relative; height:14pt; }}
.dg .link i {{ position:absolute; display:block; background:{NAVY}; }}
.dg .link .up {{ top:0; height:50%; width:1.2pt; margin-left:-0.6pt; }}
.dg .link .dn {{ top:50%; height:50%; width:1.2pt; margin-left:-0.6pt; }}
.dg .link .bus {{ top:50%; height:1.2pt; margin-top:-0.6pt; }}
.dg .pdca .phs {{ display:grid; grid-template-columns:repeat(4,1fr); gap:0 3pt; }}
.dg .pdca .ph {{ display:flex; flex-direction:column; min-width:0; }}
.dg .pdca .chev {{ color:#fff; font-weight:700; text-align:center; padding:5pt 14pt 5pt 16pt; font-size:11.5pt;
  clip-path:polygon(0 0, calc(100% - 10pt) 0, 100% 50%, calc(100% - 10pt) 100%, 0 100%, 10pt 50%); }}
.dg .pdca .ph:first-child .chev {{ clip-path:polygon(0 0, calc(100% - 10pt) 0, 100% 50%, calc(100% - 10pt) 100%, 0 100%); padding-left:8pt; }}
.dg .pdca .chev b {{ display:inline-block; width:15pt; height:15pt; line-height:15pt; border-radius:50%; background:#fff; color:{NAVY}; margin-right:4pt; font-size:10pt; }}
.dg .pdca .pb {{ flex:1; margin-top:3pt; border:1px solid {LINE}; border-radius:3pt; padding:4pt 5pt; background:#fff; }}
.dg .pdca .loop {{ margin-top:5pt; text-align:center; background:{HEAD}; color:{NAVY}; font-weight:700; border-radius:3pt; padding:3pt; border:1px dashed {BLUE}; }}
.dg .srow {{ display:grid; grid-template-columns:64pt 1fr; gap:0 4pt; margin-bottom:3pt; }}
.dg .slab {{ background:{LABEL_FILL}; font-weight:700; text-align:center; display:flex; align-items:center; justify-content:center; padding:3pt; border-radius:3pt; }}
.dg .sval {{ min-width:0; }}
.dg .band {{ border-radius:3pt; padding:5pt 8pt; text-align:center; font-weight:700; }}
.dg .band.vis {{ background:linear-gradient(135deg,{NAVY},{BLUE_FILL}); color:#fff; font-size:12.5pt; }}
.dg .band.goal {{ background:{HEAD_STRONG}; color:{NAVY}; display:flex; justify-content:space-around; gap:6pt; flex-wrap:wrap; }}
.dg .band.base {{ background:{HEAD_OLD}; color:{OLD_TEXT}; }}
.dg .sgrid {{ display:grid; gap:0 4pt; }}
.dg .phead {{ background:{NAVY}; color:#fff; font-weight:700; text-align:center; padding:4pt; border-radius:3pt; }}
.dg .ptasks {{ display:flex; flex-direction:column; gap:3pt; }}
.dg .task {{ border:1px solid {LINE}; border-radius:3pt; padding:3pt 5pt; background:#fff; text-align:center; }}
.dg .stack .sbody {{ border:1px solid {LINE}; border-radius:3pt; padding:4pt 6pt; background:#fff; height:100%; box-sizing:border-box; }}
.dg .stack .skey {{ border:1px solid {LINE}; border-radius:3pt; padding:5pt 8pt; background:{HEAD}; }}
.dg .stack .sgrid .box {{ height:100%; }}
.dg .sdown {{ display:grid; grid-template-columns:64pt 1fr; gap:0 4pt; margin:1pt 0 4pt; }}
.dg .sdown i {{ grid-column:2; justify-self:center; width:0; border-top:8pt solid {BLUE}; border-left:14pt solid transparent; border-right:14pt solid transparent; }}
.dg .timeline {{ display:grid; border-top:1.5pt solid #222; border-bottom:1.5pt solid #222; font-size:10.5pt; }}
.dg .timeline .th {{ background:#dce6f1; font-weight:700; text-align:center; padding:3pt; border-bottom:1pt solid #444; border-left:0.5pt solid #999; }}
.dg .timeline .th:first-child {{ border-left:0; }}
.dg .timeline .task {{ grid-column:1; padding:3pt 5pt; border-bottom:0.5pt solid #bbb; }}
.dg .timeline .slot {{ border-left:0.5pt solid #ccc; border-bottom:0.5pt solid #bbb; }}
.dg .timeline .bar {{ align-self:center; margin:3pt 2pt; min-height:12pt; background:{BLUE_FILL}; color:#fff; font-size:9pt; text-align:center; border-radius:2pt; padding:1pt 3pt; z-index:1; }}
"""


def fragment(spec):
    kind = spec.get("type")
    if kind not in BUILDERS:
        raise ValueError(f"type은 {', '.join(BUILDERS)} 중 하나: {kind}")
    check_palette_use(spec)
    return f'<div class="dg">{BUILDERS[kind](spec)}</div>'


def width_px(spec):
    mm = float(spec.get("width_mm", DEFAULT_WIDTH_MM))
    if not 30 <= mm <= DEFAULT_WIDTH_MM:
        raise ValueError(f"width_mm는 30~{DEFAULT_WIDTH_MM}")
    return round(mm / 25.4 * CSS_DPI)


def page(spec, font_file=None, probe=False):
    face = (f'@font-face {{ font-family:"{FONT_FAMILY}"; src:url("{pathlib.Path(font_file).resolve().as_uri()}"); }}'
            if font_file else "")
    script = ("<script>document.fonts.ready.then(()=>{document.body.setAttribute('data-h',"
              "Math.ceil(document.getElementById('fig').getBoundingClientRect().height))})</script>") if probe else ""
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><style>html,body{{margin:0;background:#fff}}'
            f'{css(face)}</style></head><body><div id="fig" style="width:{width_px(spec)}px">{fragment(spec)}</div>'
            f'{script}</body></html>')


# ---------------------------------------------------------------------------
# 캡처 — Chrome·Edge·Chromium 헤드리스
# ---------------------------------------------------------------------------

def find_browser():
    env = os.environ.get("CHROME_PATH")
    cands = [env] if env else []
    cands += [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    cands += [shutil.which(n) for n in ("google-chrome", "chromium", "chromium-browser", "microsoft-edge")]
    for c in cands:
        if c and pathlib.Path(c).is_file():
            return c
    raise FileNotFoundError("Chrome·Edge·Chromium을 찾지 못했다 — CHROME_PATH로 지정")


def _chrome(browser, *args):
    # 헤드리스는 실행마다 임시 프로필을 쓴다. `--user-data-dir`를 따로 주면 macOS에서 응답 없이
    # 멈췄다('26.9.24 실측 — 4개 조합 전부 20초 초과, 미지정은 0.7초).
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
           "--disable-extensions", "--allow-file-access-from-files", *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60)


def set_png_dpi(blob, dpi):
    """PNG에 pHYs(해상도)를 기록한다 — 기존 pHYs는 지우고 IHDR 바로 뒤에 넣는다."""
    out, i = [blob[:8]], 8
    ppm = int(round(dpi / 0.0254))
    body = struct.pack(">IIB", ppm, ppm, 1)
    phys = struct.pack(">I", 9) + b"pHYs" + body + struct.pack(">I", zlib.crc32(b"pHYs" + body))
    while i + 8 <= len(blob):
        n, tag = struct.unpack(">I4s", blob[i:i + 8])
        chunk = blob[i:i + 12 + n]
        if tag != b"pHYs":
            out.append(chunk)
        if tag == b"IHDR":
            out.append(phys)
        i += 12 + n
    return b"".join(out)


def capture(spec, png_path, html_path=None, font_file=None, browser=None):
    """명세 → PNG(300dpi, pHYs 기록). 높이는 1차 실행에서 DOM으로 재고 2차에서 정확히 찍는다."""
    browser = browser or find_browser()
    w = width_px(spec)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        probe = tmp / "probe.html"
        probe.write_text(page(spec, font_file, probe=True), encoding="utf-8")
        r = _chrome(browser, "--virtual-time-budget=3000", "--dump-dom", probe.as_uri())
        m = re.search(r'data-h="(\d+)"', r.stdout)
        if not m:
            raise RuntimeError(f"도식 높이 측정 실패: {r.stderr.strip()[:200]}")
        h = int(m.group(1))
        shot_html = tmp / "shot.html"
        shot_html.write_text(page(spec, font_file), encoding="utf-8")
        shot = tmp / "shot.png"
        _chrome(browser, f"--force-device-scale-factor={OUT_DPI / CSS_DPI}",
                f"--window-size={w},{h}", f"--screenshot={shot}", shot_html.as_uri())
        if not shot.is_file():
            raise RuntimeError("스크린샷 실패")
        blob = set_png_dpi(shot.read_bytes(), OUT_DPI)
    png_path = pathlib.Path(png_path)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(blob)
    if html_path:
        pathlib.Path(html_path).write_text(page(spec), encoding="utf-8")
    return blob


# ---------------------------------------------------------------------------
# 작업폴더 일괄 — figures/*.json → 판본 폴더의 평면 그림 폴더(kordoc image_dir)
# ---------------------------------------------------------------------------

def _report(slug, kind, path, blob, caption, **extra):
    w, h, dpi = image_pixels(blob)
    d = figure_display(w, h, dpi, DEFAULT_WIDTH_MM, FIGURE_MAX_H_MM)
    return {"slug": slug, "type": kind, "file": path.name, "caption": caption, "px": [w, h],
            "mm": [d["w_mm"], d["h_mm"]], "effective_dpi": d["effective_dpi"], "sharp": d["sharp"], **extra}


def build_all(work_dir, out_dir, font_file=None, browser=None):
    """작업폴더의 모든 명세를 out_dir 한 곳에 모은다 — kordoc `image_dir`는 하위 폴더를 따라가지 않고
    ('26.9.24 실측 — `sub/a.png` 참조 0건 임베드) 한글 파일명도 넣지 않아(같은 날 4건 전부 alt로
    남음) `fig{순번}` 영문 이름으로 쓰고, 슬러그 대응은 `figure_args`로 넘긴다."""
    work_dir, out_dir = pathlib.Path(work_dir), pathlib.Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    figs = []
    for n, spec_path in enumerate(sorted((work_dir / "figures").glob("*.json")), start=1):
        slug, base = spec_path.stem, f"fig{n:02d}"   # kordoc은 영문·숫자 파일명만 임베드한다(한글명은 alt로 남음)
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        kind, caption = spec.get("type"), spec.get("caption", slug)
        if kind == "image":
            src = work_dir / spec["src"]
            dst = out_dir / f"{base}{src.suffix.lower()}"
            shutil.copyfile(src, dst)                 # 픽셀 유지 — 크기는 후처리가 정한다(R088)
            figs.append(_report(slug, kind, dst, dst.read_bytes(), caption, src=spec["src"]))
        else:
            dst = out_dir / f"{base}.png"
            blob = capture(spec, dst, out_dir / f"{base}.html", font_file, browser)
            extra = {"font_fallback": font_file is None}
            if spec.get("source"):                    # 외부 도식을 우리 양식으로 다시 그린 것 — 출처 표기 확인 재료
                extra.update(source=spec["source"], source_ok=(work_dir / spec["source"]).is_file())
            figs.append(_report(slug, kind, dst, blob, caption, **extra))
    return figs


def main(argv=None):
    ap = argparse.ArgumentParser(description="도식 명세(JSON) → 300dpi PNG + HTML")
    ap.add_argument("spec", nargs="?", help="명세 JSON 하나 (또는 --work-dir로 일괄)")
    ap.add_argument("-o", "--out", help="PNG 경로(단건)")
    ap.add_argument("--html", help="HTML 사본 경로(단건, 선택)")
    ap.add_argument("--work-dir", help="작업폴더 — figures/*.json 전부를 --out-dir에 모은다")
    ap.add_argument("--out-dir", help="일괄 산출 폴더(판본 폴더의 figures/)")
    args = ap.parse_args(argv)

    font = find_font(extra=load_config()["font_dirs"])
    if args.work_dir:
        if not args.out_dir:
            ap.error("--work-dir에는 --out-dir가 필요하다")
        figs = build_all(args.work_dir, args.out_dir, font)
        print(json.dumps({"image_dir": str(pathlib.Path(args.out_dir).resolve()),
                          "font": str(font) if font else None, "font_fallback": font is None,
                          "figure_args": [f"{f['slug']}={f['file']}|{f['caption']}" for f in figs],
                          "figures": figs}, ensure_ascii=False))
        return 1 if any(not f["sharp"] for f in figs) else 0
    if not (args.spec and args.out):
        ap.error("spec과 -o가 필요하다(또는 --work-dir·--out-dir)")
    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8"))
    blob = capture(spec, args.out, args.html, font)
    r = _report(pathlib.Path(args.spec).stem, spec.get("type"), pathlib.Path(args.out), blob,
                spec.get("caption", ""), font_fallback=font is None)
    print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)
