"""Prepare the DEV image uploads for a post, then swap the uploaded URLs back in.

DEV's public API cannot upload images, so the images are uploaded once through the DEV editor
("Upload image" button), which returns https://dev-to-uploads.s3.amazonaws.com/... URLs.

    python tools/dev_images.py prepare [post/dev_post_final.md]
        Copies every image the post references (cover first, then in reading order) into
        post/dev_upload_<post>/NN-name.png and writes urls.txt there, one line per image.
    python tools/dev_images.py fill [post/dev_post_final.md]
        Reads the URLs you pasted into urls.txt and writes <post>.dev.md with every
        <UPLOAD path> placeholder replaced. The source post keeps its placeholders.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_RX = re.compile(r"<UPLOAD ([^>]+)>")


def dirs(post):
    """Each post gets its own upload folder: post/dev_upload_<post name>/ with urls.txt."""
    out = ROOT / "post" / f"dev_upload_{post.stem}"
    return out, out / "urls.txt"


def placeholders(post):
    seen = []
    for path in UPLOAD_RX.findall(post.read_text(encoding="utf-8")):
        if path not in seen:
            seen.append(path)
    return seen


def upload_name(i, path):
    return f"{i:02d}-{Path(path).stem.replace('_', '-')}{Path(path).suffix}"


def prepare(post):
    OUT_DIR, URLS = dirs(post)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# One line per image: '<file> = <DEV URL>'. Upload each file in the DEV editor",
             "# (Upload image button), copy the URL from the markdown it gives you, paste it after '='."]
    for i, path in enumerate(placeholders(post)):
        src = ROOT / path
        if not src.exists():
            sys.exit(f"missing image: {path}")
        name = upload_name(i, path)
        shutil.copy2(src, OUT_DIR / name)
        lines.append(f"{name} = ")
    if URLS.exists():  # keep URLs already pasted
        old = dict(l.split(" = ", 1) for l in URLS.read_text(encoding="utf-8").splitlines()
                   if " = " in l and not l.startswith("#"))
        lines = [f"{l.split(' = ')[0]} = {old.get(l.split(' = ')[0], '').strip()}" if " = " in l else l for l in lines]
    URLS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines) - 2} images copied to {OUT_DIR.relative_to(ROOT)}; paste their DEV URLs into {URLS.relative_to(ROOT)}")


def fill(post):
    OUT_DIR, URLS = dirs(post)
    urls = {}
    for l in URLS.read_text(encoding="utf-8").splitlines():
        if " = " in l and not l.startswith("#"):
            name, url = (x.strip() for x in l.split(" = ", 1))
            urls[name] = url
    text = post.read_text(encoding="utf-8")
    missing = []
    for i, path in enumerate(placeholders(post)):
        url = urls.get(upload_name(i, path), "")
        if not url.startswith("https://"):
            missing.append(upload_name(i, path))
            continue
        text = text.replace(f"<UPLOAD {path}>", url)
    out = post.with_suffix(".dev.md")
    out.write_text(text, encoding="utf-8")
    left = len(UPLOAD_RX.findall(text))
    print(f"wrote {out.relative_to(ROOT)}; {left} placeholder(s) left" + (f": {', '.join(missing)}" if missing else ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "prepare"
    post = ROOT / (sys.argv[2] if len(sys.argv) > 2 else "post/dev_post_final.md")
    {"prepare": prepare, "fill": fill}[cmd](post)
