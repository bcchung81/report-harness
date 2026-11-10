"""양식 프로파일 후처리 (spec §6-0): kordoc 분석 JSON → format-profile md. stdlib-only."""
import sys, json, argparse

def render_profile(spec, source):
    lines = [f"# 양식 프로파일 (자동 추출)", "", f"> 출처: {source}", "",
             "| 요소 | 폰트 | 크기 | 비고 |", "|---|---|---|---|"]
    for name, v in spec.get("elements", {}).items():
        lines.append(f"| {name} | {v.get('font','—')} | {v.get('pt','—')}pt | {v.get('note','')} |")
    page = spec.get("page", {})
    if page:
        lines += ["", "## 편집용지"] + [f"- {k}: {v}" for k, v in page.items()]
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("spec_json"); ap.add_argument("-o", required=True); ap.add_argument("--source", default="")
    a = ap.parse_args()
    spec = json.loads(open(a.spec_json, encoding="utf-8").read())
    open(a.o, "w", encoding="utf-8").write(render_profile(spec, a.source or a.spec_json))
    print(f"OK {a.o}")
