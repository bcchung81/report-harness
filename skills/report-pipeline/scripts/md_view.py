#!/usr/bin/env python3
"""문서 보기 — 초안 밖의 md(아웃라인·분석·맥락·research·부속 문서)를 리뷰어에서 읽고 코멘트한다. stdlib-only.

초안(20_draft.md)은 hwpx 양식에 가깝게 그리는 '양식 보기'(render_review_html)가 맡는다. 나머지 md는 일반
마크다운(#·목록·표·코드·인용)이라 양식 보기로 그리면 헤딩·문단이 한 덩어리가 되고 목록이 hwpx 대시로
그려진다('26.9.25 실측: 05_analysis 462블록 중 361블록이 구분 없음). 이 모듈은 읽기 쉬운 문서 모양으로 그리고,
블록마다 코멘트 주소와 원본 줄 번호(data-line)를 단다 — 리뷰 서버·패널은 두 보기를 같은 방식으로 다룬다.

주소: 헤딩 `§1.2`, 그 아래 문단 `§1.2-¶3`·목록 `§1.2-•4`·표 `§1.2-표1`·코드 `§1.2-코드1`·인용 `§1.2-인용1`.
research 파일의 출처 머리(---…---)는 `출처`.

render_parts(text, title) → {"title", "css", "pages": [[{addr, line, html}…]], "counts"} — render_review_html과 같은 틀.
"""
import html
import re

HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
LIST = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")
TABLE = re.compile(r"^\s*\|")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{3,}")
FENCE = re.compile(r"^\s*(```|~~~)")
QUOTE = re.compile(r"^\s*>\s?(.*)$")
HR = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")
COMMENT = re.compile(r"^\s*<!--.*-->\s*$")


def inline(text):
    """이스케이프 후 굵게·기울임·코드·링크·하이라이트만 살린다."""
    s = html.escape(text, quote=False)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![*\w])\*(?!\s)([^*]+?)\*(?!\w)", r"<i>\1</i>", s)
    s = re.sub(r"==(.+?)==", r"<mark>\1</mark>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def split_row(line):
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def parse(text):
    """블록 목록 — kind: meta·heading·para·item·table·code·quote·hr. 문단은 이어진 줄을 한 블록으로(lines 수)."""
    lines = text.split("\n")
    blocks, i, n = [], 0, len(lines)
    if n and lines[0].strip() == "---":                       # research 출처 머리
        j = next((k for k in range(1, n) if lines[k].strip() == "---"), None)
        if j:
            pairs = [re.match(r"^(\w[\w-]*):\s*(.*)$", x) for x in lines[1:j]]
            blocks.append({"kind": "meta", "line": 1, "lines": j + 1, "pairs": [(m.group(1), m.group(2)) for m in pairs if m]})
            i = j + 1
    while i < n:
        raw = lines[i]
        s = raw.strip()
        if not s or COMMENT.match(s):
            i += 1
            continue
        if FENCE.match(raw):
            j = next((k for k in range(i + 1, n) if FENCE.match(lines[k])), n)
            blocks.append({"kind": "code", "line": i + 1, "lines": j - i + 1, "text": "\n".join(lines[i + 1:j])})
            i = j + 1
            continue
        m = HEADING.match(raw)
        if m:
            blocks.append({"kind": "heading", "line": i + 1, "lines": 1, "level": len(m.group(1)), "text": m.group(2)})
            i += 1
            continue
        if TABLE.match(raw):
            j = i
            while j < n and TABLE.match(lines[j]):
                j += 1
            rows = [split_row(x) for x in lines[i:j] if not TABLE_SEP.match(x.replace("|", "", 1))]
            blocks.append({"kind": "table", "line": i + 1, "lines": j - i, "rows": rows})
            i = j
            continue
        if HR.match(raw):
            blocks.append({"kind": "hr", "line": i + 1, "lines": 1})
            i += 1
            continue
        if QUOTE.match(raw):
            j, body = i, []
            while j < n and QUOTE.match(lines[j]):
                body.append(QUOTE.match(lines[j]).group(1))
                j += 1
            blocks.append({"kind": "quote", "line": i + 1, "lines": j - i, "text": "\n".join(body)})
            i = j
            continue
        m = LIST.match(raw)
        if m:
            depth = len(m.group(1).replace("\t", "  ")) // 2
            blocks.append({"kind": "item", "line": i + 1, "lines": 1, "depth": depth, "mark": m.group(2), "text": m.group(3)})
            i += 1
            continue
        j, body = i, []                                        # 문단 — 빈 줄·다른 블록 시작 전까지
        while j < n and lines[j].strip() and not (HEADING.match(lines[j]) or TABLE.match(lines[j]) or FENCE.match(lines[j])
                                                    or LIST.match(lines[j]) or QUOTE.match(lines[j]) or HR.match(lines[j])):
            body.append(lines[j].strip())
            j += 1
        blocks.append({"kind": "para", "line": i + 1, "lines": j - i, "text": " ".join(body)})
        i = j
    return blocks


def address(blocks):
    """헤딩 번호 경로(§1.2)와 그 아래 종류별 순번으로 주소를 단다 — 문서 안에서 유일하다."""
    nums, counts, out = [], {}, []
    marks = {"para": "¶", "item": "•", "table": "표", "code": "코드", "quote": "인용", "hr": "선"}
    for b in blocks:
        if b["kind"] == "meta":
            b["addr"] = "출처"
        elif b["kind"] == "heading":
            lv = b["level"]
            nums = (nums + [0] * lv)[:lv]
            nums[lv - 1] += 1
            b["addr"] = "§" + ".".join(str(x) for x in nums if x) if any(nums) else "§0"
            counts = {}
        else:
            sec = "§" + ".".join(str(x) for x in nums if x) if any(nums) else "§0"
            k = b["kind"]
            counts[k] = counts.get(k, 0) + 1
            b["addr"] = f"{sec}-{marks[k]}{counts[k]}"
        out.append(b)
    return out


def block_html(b):
    """리뷰 패널이 다루는 블록 틀 — class blk + 종류, id L{줄}, data-line·data-lines·data-addr, 주소 라벨."""
    kind = {"heading": "other", "para": "other", "item": "other", "table": "table"}.get(b["kind"], "ro")
    attrs = (f'class="blk {kind} v-{b["kind"]}" id="L{b["line"]}" data-line="{b["line"]}" '
             f'data-lines="{b.get("lines", 1)}" data-addr="{html.escape(b["addr"])}"')
    label = f'<span class="addr">{html.escape(b["addr"])}</span>'
    k = b["kind"]
    if k == "meta":
        rows = "".join(f"<tr><th>{html.escape(a)}</th><td>{inline(v)}</td></tr>" for a, v in b["pairs"])
        body = f'<table class="meta">{rows}</table>'
    elif k == "heading":
        body = f'<p class="h{b["level"]}">{inline(b["text"])}</p>'
    elif k == "para":
        body = f"<p>{inline(b['text'])}</p>"
    elif k == "item":
        mark = "•" if b["mark"] in "-*+" else html.escape(b["mark"])
        body = f'<p class="li" style="padding-left:{1.4 + b["depth"] * 1.4:.1f}em"><span class="lm">{mark}</span>{inline(b["text"])}</p>'
    elif k == "table":
        rows = b["rows"]
        head = "".join(f"<th>{inline(c)}</th>" for c in rows[0]) if rows else ""
        tr = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rows[1:])
        body = f'<div class="tw"><table><thead><tr>{head}</tr></thead><tbody>{tr}</tbody></table></div>'
    elif k == "code":
        body = f"<pre>{html.escape(b['text'])}</pre>"
    elif k == "quote":
        body = f"<blockquote>{inline(b['text']).replace(chr(10), '<br>')}</blockquote>"
    else:
        body = "<hr>"
    return f"<div {attrs}>{label}{body}</div>"


def css():
    return """
:root { --paper:#ffffff; --desk:#e9e8e6; --ink:#1e2124; --muted:#8a8a8a; --line:#d6dbe1; --head:#eef2f7; --mark:#fff1a8; }
html, body { margin:0; background:var(--desk); color:var(--ink); }
.page.doc { box-sizing:border-box; width:210mm; min-height:60vh; margin:16px auto; background:var(--paper); padding:14mm 16mm 18mm 20mm;
  box-shadow:0 1px 4px rgba(0,0,0,.25); position:relative; font:15px/1.65 "Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;
  word-break:keep-all; overflow-wrap:break-word; }
.page.doc .blk { position:relative; margin:0 0 6px; }
.page.doc .addr { position:absolute; left:-19mm; top:.25em; width:17mm; text-align:right; font:10px/1.3 "Apple SD Gothic Neo","Malgun Gothic",sans-serif; color:var(--muted); user-select:none; }
.page.doc p { margin:0; }
.page.doc p.h1 { font-size:22px; font-weight:700; margin:14px 0 4px; } .page.doc p.h2 { font-size:18.5px; font-weight:700; margin:16px 0 2px; border-bottom:1px solid var(--line); padding-bottom:3px; }
.page.doc p.h3 { font-size:16.5px; font-weight:700; margin:12px 0 0; } .page.doc p.h4, .page.doc p.h5, .page.doc p.h6 { font-size:15px; font-weight:700; margin:8px 0 0; }
.page.doc p.li { position:relative; } .page.doc .lm { position:absolute; margin-left:-1.2em; color:#555; }
.page.doc .tw { overflow-x:auto; } .page.doc table { border-collapse:collapse; font-size:13px; line-height:1.5; }
.page.doc th, .page.doc td { border:1px solid var(--line); padding:3px 6px; vertical-align:top; } .page.doc th { background:var(--head); font-weight:700; }
.page.doc table.meta { width:100%; font-size:12px; color:#444; } .page.doc table.meta th { width:18%; text-align:left; }
.page.doc pre { background:#f6f7f9; border:1px solid var(--line); border-radius:3px; padding:8px 10px; font:12px/1.5 Menlo,Consolas,monospace; white-space:pre-wrap; margin:0; }
.page.doc blockquote { margin:0; padding:4px 10px; border-left:3px solid #b8c4d2; color:#444; background:#fafbfc; }
.page.doc code { background:#f1f3f5; border-radius:3px; padding:0 3px; font-size:.92em; } .page.doc mark { background:var(--mark); }
.page.doc hr { border:0; border-top:1px solid var(--line); margin:10px 0; }
.page.doc .readonly-note { font-size:12px; color:#7a5b00; background:#fff7dc; border:1px solid #f0dfa0; border-radius:3px; padding:4px 8px; margin-bottom:10px; }
"""


def render_parts(text, title="문서", note=""):
    """문서 보기 조각 — 쪽 나눔이 없으므로 '쪽'은 하나다(패널의 쪽 기능은 문서 보기에서 꺼진다)."""
    blocks = address(parse(text))
    items = [{"addr": b["addr"], "line": b["line"], "html": block_html(b)} for b in blocks]
    if note:
        items.insert(0, {"addr": "", "line": 0, "html": f'<div class="readonly-note">{html.escape(note)}</div>'})
    counts = {}
    for b in blocks:
        counts[b["kind"]] = counts.get(b["kind"], 0) + 1
    return {"title": title, "css": css(), "pages": [items], "counts": {"blocks": len(blocks), **counts}}


def page_html(items):
    return '<section class="page doc">\n' + "\n".join(x["html"] for x in items) + "\n</section>"


def document(parts):
    body = "\n".join(page_html(p) for p in parts["pages"])
    return (f'<!doctype html>\n<html lang="ko"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta name="color-scheme" content="only light">'   # 강제 다크 반전 방지 — render_review_html과 같다
            f'<title>{html.escape(parts["title"])} — 리뷰</title><style>{parts["css"]}</style></head>\n<body>\n{body}\n</body></html>\n')
