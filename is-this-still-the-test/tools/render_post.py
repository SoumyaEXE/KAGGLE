"""Fill post/<name>.tmpl.md with figures/final/numbers.json and write post/<name>.md.

    python tools/render_post.py [post/dev_post_final.tmpl.md]

Every {{key}} must exist in numbers.json; an unknown or leftover placeholder is an error, so a
rendered post can never go out with a stale or missing number.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fmt(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


def kaggle_images(text):
    """<!-- KAGGLE_IMG key | alt --> becomes ![alt](url) from images/kaggle_links.json. With no url, a local
    screenshot images/kaggle/<key>.png becomes an <UPLOAD> placeholder (uploaded with the charts by
    tools/dev_images.py); with neither, the line is dropped."""
    links = json.loads((ROOT / "images/kaggle_links.json").read_text(encoding="utf-8"))

    def swap(m):
        key, alt = m.group(1), m.group(2).strip()
        if key not in links:
            sys.exit(f"images/kaggle_links.json has no slot: {key}")
        url = links[key].get("url", "").strip()
        if not url and (ROOT / f"images/kaggle/{key}.png").exists():
            url = f"<UPLOAD images/kaggle/{key}.png>"
        return f"![{alt}]({url})\n" if url else ""
    return re.sub(r"<!-- KAGGLE_IMG (\w+) \| (.+?) -->\n?", swap, text)


def render(tmpl):
    nums = json.loads((ROOT / "figures/final/numbers.json").read_text(encoding="utf-8"))
    pilot = ROOT / "figures/pilot/numbers.json"  # round-2 pilot, once it has run
    if pilot.exists():
        nums.update(json.loads(pilot.read_text(encoding="utf-8")))
    text = tmpl.read_text(encoding="utf-8")
    missing = sorted({k for k in re.findall(r"\{\{(\w+)\}\}", text) if k not in nums})
    if missing:
        sys.exit(f"numbers.json has no value for: {', '.join(missing)}")
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: fmt(nums[m.group(1)]), text)
    out = kaggle_images(out)
    dst = tmpl.with_name(tmpl.name.replace(".tmpl.md", ".md"))
    dst.write_text(out, encoding="utf-8")
    print(f"rendered {dst.relative_to(ROOT)} from {nums['runs']} complete runs ({nums['decisions']} decisions)")


if __name__ == "__main__":
    render(ROOT / (sys.argv[1] if len(sys.argv) > 1 else "post/dev_post_final.tmpl.md"))
