#!/usr/bin/env python3
"""
Generate per-scene video clips with Google's Veo via the Gemini API.

Reads:  <ep_dir>/03_prompts/scene_NN.txt
Writes: <ep_dir>/04_clips/scene_NN.mp4

Auth:
    export GEMINI_API_KEY=...

Usage:
    python scripts/generate_clips.py output/cafe-diary/01 \\
        --aspect 9:16 --duration 8

NOTE: Veo's API is in active development. The endpoint, model name,
and response shape may change. If calls fail with 4xx, verify against
https://ai.google.dev/gemini-api/docs/video and adjust MODEL / payload.
Override the model with VEO_MODEL=... if needed.
"""
from __future__ import annotations

import argparse
import base64
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("requests not installed. Run: pip install requests")


API_BASE = "https://generativelanguage.googleapis.com/v1beta"
MODEL = os.environ.get("VEO_MODEL", "veo-3.0-generate-preview")
POLL_INTERVAL_SEC = 10
POLL_TIMEOUT_SEC = 600


def submit(prompt: str, api_key: str, aspect_ratio: str, duration: int) -> str:
    url = f"{API_BASE}/models/{MODEL}:predictLongRunning?key={api_key}"
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "durationSeconds": duration,
            "sampleCount": 1,
        },
    }
    r = requests.post(url, json=body, timeout=60)
    r.raise_for_status()
    return r.json()["name"]


def wait(op_name: str, api_key: str) -> dict:
    url = f"{API_BASE}/{op_name}?key={api_key}"
    deadline = time.time() + POLL_TIMEOUT_SEC
    while time.time() < deadline:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        op = r.json()
        if op.get("done"):
            if "error" in op:
                raise RuntimeError(f"Veo error: {op['error']}")
            return op.get("response", {})
        time.sleep(POLL_INTERVAL_SEC)
    raise TimeoutError(f"timed out waiting for {op_name}")


def download(response: dict, out_path: Path, api_key: str) -> None:
    samples = (
        response.get("generateVideoResponse", {}).get("generatedSamples")
        or response.get("generatedSamples")
        or []
    )
    if not samples:
        raise RuntimeError(f"no samples in response: {response}")
    video = samples[0].get("video", {})
    if "uri" in video:
        sep = "&" if "?" in video["uri"] else "?"
        with requests.get(f"{video['uri']}{sep}key={api_key}", stream=True, timeout=180) as r:
            r.raise_for_status()
            with out_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    f.write(chunk)
    elif "bytesBase64Encoded" in video:
        out_path.write_bytes(base64.b64decode(video["bytesBase64Encoded"]))
    else:
        raise RuntimeError(f"unrecognized video sample shape: {samples[0]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ep_dir", help="episode directory (must contain 03_prompts/)")
    ap.add_argument("--aspect", default="9:16")
    ap.add_argument("--duration", type=int, default=8, help="seconds per clip")
    ap.add_argument("--overwrite", action="store_true", help="regenerate even if mp4 exists")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("GEMINI_API_KEY env var required")

    ep = Path(args.ep_dir)
    prompts_dir = ep / "03_prompts"
    clips_dir = ep / "04_clips"
    clips_dir.mkdir(parents=True, exist_ok=True)

    prompt_files = sorted(prompts_dir.glob("scene_*.txt"))
    if not prompt_files:
        sys.exit(f"no prompts in {prompts_dir}")

    for pf in prompt_files:
        m = re.match(r"scene_(\d+)\.txt$", pf.name)
        if not m:
            continue
        sid = m.group(1)
        out = clips_dir / f"scene_{sid}.mp4"
        if out.exists() and not args.overwrite:
            print(f"skip {out.name} (exists; pass --overwrite to regenerate)")
            continue
        prompt = pf.read_text(encoding="utf-8")
        print(f"[{pf.name}] submitting...")
        op = submit(prompt, api_key, args.aspect, args.duration)
        print(f"[{pf.name}] op={op}, polling every {POLL_INTERVAL_SEC}s...")
        resp = wait(op, api_key)
        download(resp, out, api_key)
        print(f"[{pf.name}] -> {out}")


if __name__ == "__main__":
    main()
