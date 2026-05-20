#!/usr/bin/env python3
"""
Generate per-scene narration audio with Microsoft Edge TTS (free, no API key).

Reads:  <ep_dir>/02_script.json
Writes: <ep_dir>/05_audio/scene_NN.mp3  (one per scene with non-empty narration)

Install:
    pip install edge-tts

Usage:
    python scripts/generate_tts.py output/cafe-diary/01 --voice ko-KR-SunHiNeural

List Korean voices:
    edge-tts --list-voices | grep ko-KR
    # e.g. ko-KR-SunHiNeural (female), ko-KR-InJoonNeural (male), ko-KR-HyunsuNeural
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

try:
    import edge_tts
except ImportError:
    sys.exit("edge-tts not installed. Run: pip install edge-tts")


async def synthesize(text: str, voice: str, rate: str, out: Path) -> None:
    # Write to a temp file first so a failed/partial run never leaves an
    # empty mp3 that the skip-if-exists check would mistake for success.
    tmp = out.with_suffix(".mp3.part")
    try:
        await edge_tts.Communicate(text, voice, rate=rate).save(str(tmp))
        os.replace(tmp, out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ep_dir", help="episode directory (must contain 02_script.json)")
    ap.add_argument("--voice", default="ko-KR-SunHiNeural", help="Edge TTS voice name")
    ap.add_argument("--rate", default="+0%", help="speech rate, e.g. +10%% or -5%%")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    ep = Path(args.ep_dir)
    script_path = ep / "02_script.json"
    if not script_path.exists():
        sys.exit(f"missing {script_path}")

    script = json.loads(script_path.read_text(encoding="utf-8"))
    out_dir = ep / "05_audio"
    out_dir.mkdir(parents=True, exist_ok=True)

    for scene in script.get("scenes") or []:
        sid = int(scene["id"])
        text = (scene.get("narration") or "").strip()
        if not text:
            continue
        out = out_dir / f"scene_{sid:02d}.mp3"
        if out.exists() and not args.overwrite:
            print(f"skip {out.name} (exists; pass --overwrite to regenerate)")
            continue
        preview = text[:40].replace("\n", " ")
        print(f"[scene {sid:02d}] {preview}...")
        asyncio.run(synthesize(text, args.voice, args.rate, out))
        print(f"  -> {out}")


if __name__ == "__main__":
    main()
