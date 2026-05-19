#!/usr/bin/env python3
"""
Generate per-scene narration audio with ElevenLabs TTS.

Reads:  <ep_dir>/02_script.json
Writes: <ep_dir>/05_audio/scene_NN.mp3  (one per scene with non-empty narration)

Auth:
    export ELEVENLABS_API_KEY=...
    export ELEVENLABS_VOICE_ID=...   (or pass --voice)

Usage:
    python scripts/generate_tts.py output/cafe-diary/01 \\
        --voice 21m00Tcm4TlvDq8ikWAM
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests not installed. Run: pip install requests")


API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"


def synthesize(text: str, voice_id: str, api_key: str, model: str,
               stability: float, similarity_boost: float) -> bytes:
    r = requests.post(
        API_URL.format(voice=voice_id),
        headers={
            "xi-api-key": api_key,
            "accept": "audio/mpeg",
            "content-type": "application/json",
        },
        json={
            "text": text,
            "model_id": model,
            "voice_settings": {
                "stability": stability,
                "similarity_boost": similarity_boost,
            },
        },
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:300]}")
    return r.content


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ep_dir", help="episode directory (must contain 02_script.json)")
    ap.add_argument("--voice", default=os.environ.get("ELEVENLABS_VOICE_ID"),
                    help="ElevenLabs voice ID (or set ELEVENLABS_VOICE_ID)")
    ap.add_argument("--model", default="eleven_multilingual_v2",
                    help="TTS model (default eleven_multilingual_v2 — supports Korean)")
    ap.add_argument("--stability", type=float, default=0.5)
    ap.add_argument("--similarity-boost", type=float, default=0.75)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        sys.exit("ELEVENLABS_API_KEY env var required")
    if not args.voice:
        sys.exit("voice id required (--voice or ELEVENLABS_VOICE_ID)")

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
        audio = synthesize(text, args.voice, api_key, args.model,
                           args.stability, args.similarity_boost)
        out.write_bytes(audio)
        print(f"  -> {out} ({len(audio)} bytes)")


if __name__ == "__main__":
    main()
