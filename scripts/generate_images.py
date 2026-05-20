#!/usr/bin/env python3
"""
Generate per-scene still images with Gemini 2.5 Flash Image ("Nano Banana").

Works on the Gemini API FREE tier (image generation, unlike Veo video).

Character consistency: pass a reference image with --reference, or let the
script create one from the series character block with --series. That single
reference is then fed into every scene request so the character's face, hair,
and outfit stay identical across scenes.

Reads:  <ep_dir>/03_prompts/scene_NN.txt
Writes: <ep_dir>/04_images/scene_NN.png
        <ep_dir>/character_ref.png   (only when generated from --series)

Auth:
    export GEMINI_API_KEY=...

Usage:
    # generate a character reference from the series file, then every scene:
    python scripts/generate_images.py output/cafe-diary/01 --series docs/series/example.yaml

    # or anchor on your own reference image:
    python scripts/generate_images.py output/cafe-diary/01 --reference my_char.png
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests not installed. Run: pip install requests")


API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.environ.get("IMAGE_MODEL", "gemini-2.5-flash-image")


def text_part(text: str) -> dict:
    return {"text": text}


def image_part(img_bytes: bytes, mime: str = "image/png") -> dict:
    return {"inline_data": {"mime_type": mime, "data": base64.b64encode(img_bytes).decode()}}


def generate(parts: list[dict], api_key: str) -> bytes:
    url = f"{API_BASE}/models/{MODEL}:generateContent?key={api_key}"
    r = requests.post(url, json={"contents": [{"parts": parts}]}, timeout=180)
    if not r.ok:
        raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    data = r.json()
    for cand in data.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])
    raise RuntimeError(f"no image in response: {str(data)[:300]}")


def load_series_character(series_path: Path) -> str:
    text = series_path.read_text(encoding="utf-8")
    if series_path.suffix in (".yaml", ".yml"):
        import yaml  # lazy import; only needed for YAML configs
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    chars = data.get("characters", {}) or {}
    main = chars.get("main") or (next(iter(chars.values())) if chars else {})
    block = (main.get("description_block") or "").strip()
    style = (data.get("style", {}) or {}).get("description_block", "").strip()
    return (
        "Character reference sheet: a single character, clear face and full outfit, "
        "neutral plain background, soft even lighting.\n"
        f"{block}\n{style}"
    )


def resolve_reference(ep: Path, args, api_key: str) -> bytes | None:
    if args.reference:
        return Path(args.reference).read_bytes()
    if args.series:
        ref_path = ep / "character_ref.png"
        if ref_path.exists() and not args.overwrite:
            print(f"using existing reference {ref_path}")
            return ref_path.read_bytes()
        print("generating character reference image...")
        ref_bytes = generate([text_part(load_series_character(Path(args.series)))], api_key)
        ref_path.write_bytes(ref_bytes)
        print(f"  -> {ref_path}")
        return ref_bytes
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ep_dir", help="episode directory (must contain 03_prompts/)")
    ap.add_argument("--reference", help="character reference image to anchor identity")
    ap.add_argument("--series", help="series yaml/json to auto-generate a reference from")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY env var required")

    ep = Path(args.ep_dir)
    prompts_dir = ep / "03_prompts"
    img_dir = ep / "04_images"
    img_dir.mkdir(parents=True, exist_ok=True)

    ref_bytes = resolve_reference(ep, args, api_key)

    prompt_files = sorted(prompts_dir.glob("scene_*.txt"))
    if not prompt_files:
        sys.exit(f"no prompts in {prompts_dir}")

    for pf in prompt_files:
        m = re.match(r"scene_(\d+)\.txt$", pf.name)
        if not m:
            continue
        sid = m.group(1)
        out = img_dir / f"scene_{sid}.png"
        if out.exists() and not args.overwrite:
            print(f"skip {out.name} (exists; pass --overwrite to regenerate)")
            continue
        scene_prompt = pf.read_text(encoding="utf-8")
        if ref_bytes:
            parts = [
                image_part(ref_bytes),
                text_part(
                    "Keep this exact character (same face, hairstyle, and outfit) "
                    "identical to the reference image. Render the following scene "
                    "in 9:16 vertical framing:\n" + scene_prompt
                ),
            ]
        else:
            parts = [text_part(scene_prompt)]
        print(f"[{pf.name}] generating...")
        out.write_bytes(generate(parts, api_key))
        print(f"  -> {out}")


if __name__ == "__main__":
    main()
