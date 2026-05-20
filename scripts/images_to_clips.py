#!/usr/bin/env python3
"""
Turn per-scene still images into short video clips with a Ken Burns
(zoompan) motion effect, so the assembled Short feels like real video.

Reads:  <ep_dir>/04_images/scene_NN.png
        <ep_dir>/02_script.json   (optional, for per-scene duration_sec)
Writes: <ep_dir>/04_clips/scene_NN.mp4   (1080x1920, 30fps)

After this, run scripts/compose.sh <ep_dir> as usual.

Usage:
    python scripts/images_to_clips.py output/cafe-diary/01 --duration 4
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

W, H, FPS = 1080, 1920, 30
MOTIONS = ["in", "left", "out", "right"]


def make_clip(img: Path, out: Path, duration: float, motion: str) -> None:
    frames = max(1, int(round(duration * FPS)))
    if motion == "in":
        z, x, y = "min(zoom+0.0010,1.12)", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "out":
        z, x, y = "if(eq(on,0),1.12,max(zoom-0.0010,1.0))", "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    elif motion == "left":
        z, x, y = "1.12", f"(iw-iw/zoom)*(on/{frames})", "ih/2-(ih/zoom/2)"
    else:  # right
        z, x, y = "1.12", f"(iw-iw/zoom)*(1-on/{frames})", "ih/2-(ih/zoom/2)"

    vf = (
        f"scale={W*2}:{H*2}:force_original_aspect_ratio=increase,"
        f"crop={W*2}:{H*2},"
        f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={W}x{H}:fps={FPS},"
        f"setsar=1"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-loop", "1", "-i", str(img),
        "-vf", vf, "-t", f"{duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ep_dir")
    ap.add_argument("--duration", type=float, default=4.0,
                    help="seconds per clip when script.json has no duration_sec")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg not found in PATH")

    ep = Path(args.ep_dir)
    img_dir = ep / "04_images"
    clips_dir = ep / "04_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    durations: dict[int, float] = {}
    script_path = ep / "02_script.json"
    if script_path.exists():
        for sc in json.loads(script_path.read_text(encoding="utf-8")).get("scenes", []):
            durations[int(sc["id"])] = float(sc.get("duration_sec", args.duration))

    images = sorted(img_dir.glob("scene_*.png"))
    if not images:
        sys.exit(f"no images in {img_dir}")

    for i, img in enumerate(images):
        m = re.match(r"scene_(\d+)\.png$", img.name)
        if not m:
            continue
        sid = int(m.group(1))
        out = clips_dir / f"scene_{sid:02d}.mp4"
        if out.exists() and not args.overwrite:
            print(f"skip {out.name} (exists; pass --overwrite to regenerate)")
            continue
        dur = durations.get(sid, args.duration)
        motion = MOTIONS[i % len(MOTIONS)]
        print(f"[scene {sid:02d}] {dur}s, motion={motion}")
        make_clip(img, out, dur, motion)
        print(f"  -> {out}")


if __name__ == "__main__":
    main()
