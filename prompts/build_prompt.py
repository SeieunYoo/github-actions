#!/usr/bin/env python3
"""
Build VEO3 prompts from a series config + script.json.

The series config is YAML or JSON with this shape:

    series_name: "..."
    characters:
      main:
        name: "..."
        description_block: |
          A 25-year-old Korean woman with shoulder-length wavy black hair...
    world:
      description_block: |
        A cozy small Korean-style cafe interior...
    style:
      description_block: "soft cinematic, slightly desaturated, 35mm film grain"
      default_camera: "static medium shot"
    negative:
      - "low quality"
      - "distorted face"
      - "inconsistent character"

The script.json shape is defined in docs/workflow.md.

Usage:
    python prompts/build_prompt.py \\
        --series  docs/series/example.yaml \\
        --script  output/example/01/02_script.json \\
        --out     output/example/01/03_prompts/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml  # optional; only needed for .yaml/.yml configs
except ImportError:
    yaml = None


PROMPT_TEMPLATE = """[CHARACTER]
{character}

[BACKGROUND]
{background}

[ACTION]
{action}

[CAMERA]
{camera}

[STYLE]
{style}

[NEGATIVE]
{negative}

[ASPECT_RATIO]
9:16

[DURATION]
{duration}s
"""


def load_series(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        if yaml is None:
            sys.exit("PyYAML not installed. Run `pip install pyyaml`, or use a JSON config.")
        return yaml.safe_load(text)
    return json.loads(text)


def get_character_block(series: dict, character_id: str | None) -> str:
    chars = series.get("characters", {})
    if not chars:
        return ""
    if character_id and character_id in chars:
        target = chars[character_id]
    else:
        # Default to "main", else the first character defined.
        target = chars.get("main") or next(iter(chars.values()))
    return (target.get("description_block") or "").strip()


def build_prompt(series: dict, scene: dict) -> str:
    style = series.get("style", {}) or {}
    return PROMPT_TEMPLATE.format(
        character=get_character_block(series, scene.get("character")),
        background=(series.get("world", {}).get("description_block") or "").strip(),
        action=(scene.get("visual_direction") or "").strip(),
        camera=(scene.get("camera") or style.get("default_camera") or "static medium shot").strip(),
        style=(style.get("description_block") or "").strip(),
        negative=", ".join(series.get("negative") or [])
        or "low quality, distorted face, inconsistent character, wrong aspect ratio",
        duration=scene.get("duration_sec", 6),
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--series", required=True, help="path to series config (.yaml/.yml/.json)")
    ap.add_argument("--script", required=True, help="path to script.json")
    ap.add_argument("--out", required=True, help="output directory for scene_NN.txt files")
    args = ap.parse_args()

    series = load_series(Path(args.series))
    script = json.loads(Path(args.script).read_text(encoding="utf-8"))

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenes = script.get("scenes") or []
    if not scenes:
        sys.exit("script.json has no 'scenes'")

    for scene in scenes:
        sid = int(scene["id"])
        prompt = build_prompt(series, scene)
        fn = out_dir / f"scene_{sid:02d}.txt"
        fn.write_text(prompt, encoding="utf-8")
        print(f"wrote {fn}")


if __name__ == "__main__":
    main()
