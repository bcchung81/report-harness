"""문서 보기(md_view) — 초안 밖 md를 읽기 쉬운 문서로 그리고 블록마다 주소·줄 번호를 단다('26.9.25)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "skills/report-pipeline/scripts"))
import md_view as mv

DOC = """---
source_url: https://example.go.kr/a
title: 예시 자료
confidence: 확정
---

# 제목

첫 문단은
두 줄에 걸친다.

## 1. 절

- 항목 하나
  - 들여쓴 항목
1. 번호 항목

| 가 | 나 |
|---|---|
| 1 | 2 |

```
코드 줄
```

> 인용 줄
"""


def test_blocks_addresses_and_lines():
    blocks = mv.address(mv.parse(DOC))
    kinds = [b["kind"] for b in blocks]
    assert kinds == ["meta", "heading", "para", "heading", "item", "item", "item", "table", "code", "quote"]
    addrs = [b["addr"] for b in blocks]
    assert len(addrs) == len(set(addrs)) and addrs[0] == "출처" and addrs[1] == "§1" and addrs[3] == "§1.1"
    para = blocks[2]
    assert para["line"] == 9 and para["lines"] == 2 and para["text"] == "첫 문단은 두 줄에 걸친다."
    assert blocks[5]["depth"] == 1


def test_render_parts_has_panel_hooks():
    p = mv.render_parts(DOC, "예시", note="보기 전용")
    html = mv.document(p)
    assert 'class="page doc"' in html and 'data-addr="§1.1-표1"' in html and 'data-lines="2"' in html
    assert "readonly-note" in html and "<table" in html and "example.go.kr" in html
    assert "<script" not in html


def test_inline_escapes_and_keeps_bold_links():
    out = mv.inline("**굵게** <b>x</b> [링크](https://a.b/c)")
    assert "<b>굵게</b>" in out and "&lt;b&gt;" in out and 'href="https://a.b/c"' in out
