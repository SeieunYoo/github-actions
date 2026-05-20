#!/usr/bin/env bash
# Compose a final 9:16 Shorts mp4 from per-scene clips, narration, BGM, and subtitles.
#
# Usage:
#   ./scripts/compose.sh <episode_dir>
#
# Expects inside <episode_dir>:
#   04_clips/scene_*.mp4   (required — one per scene, sorted by filename)
#   05_audio/scene_*.mp3   (optional — narration per scene; matched by basename)
#   bgm.mp3                (optional — looped, ducked under narration)
#   subtitles.srt          (optional — burned into the video)
#
# Outputs:
#   <episode_dir>/final.mp4   (1080x1920, H.264, AAC)

set -euo pipefail

EP_DIR="${1:?usage: compose.sh <episode_dir>}"
CLIPS_DIR="$EP_DIR/04_clips"
AUDIO_DIR="$EP_DIR/05_audio"
BGM="$EP_DIR/bgm.mp3"
SRT="$EP_DIR/subtitles.srt"
OUT="$EP_DIR/final.mp4"

TARGET_W=1080
TARGET_H=1920
FPS=30

command -v ffmpeg  >/dev/null || { echo "ffmpeg not found in PATH"  >&2; exit 1; }
command -v ffprobe >/dev/null || { echo "ffprobe not found in PATH" >&2; exit 1; }

mapfile -t CLIPS < <(ls "$CLIPS_DIR"/scene_*.mp4 2>/dev/null | sort)
if [[ ${#CLIPS[@]} -eq 0 ]]; then
    echo "no clips found in $CLIPS_DIR (expected scene_*.mp4)" >&2
    exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# --- 1. Normalize each clip to 9:16 1080x1920 @ 30fps, no audio ---
CONCAT_LIST="$TMP/concat.txt"
: > "$CONCAT_LIST"
for i in "${!CLIPS[@]}"; do
    src="${CLIPS[$i]}"
    norm="$TMP/norm_$(printf '%03d' "$i").mp4"
    ffmpeg -y -loglevel error -i "$src" \
        -vf "scale=${TARGET_W}:${TARGET_H}:force_original_aspect_ratio=increase,crop=${TARGET_W}:${TARGET_H},setsar=1,fps=${FPS}" \
        -c:v libx264 -pix_fmt yuv420p -an "$norm"
    echo "file '$norm'" >> "$CONCAT_LIST"
done

# --- 2. Concat into a single silent video ---
SILENT="$TMP/silent.mp4"
ffmpeg -y -loglevel error -f concat -safe 0 -i "$CONCAT_LIST" -c copy "$SILENT"
DUR=$(ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 "$SILENT")
echo "video duration: ${DUR}s"

# --- 3. Build narration track by concatenating per-scene mp3s (in scene order) ---
NARR_LIST="$TMP/narr.txt"
: > "$NARR_LIST"
HAS_NARR=0
for clip in "${CLIPS[@]}"; do
    sid=$(basename "$clip" .mp4)            # e.g. "scene_01"
    nar="$AUDIO_DIR/${sid}.mp3"
    if [[ -f "$nar" ]]; then
        echo "file '$nar'" >> "$NARR_LIST"
        HAS_NARR=1
    fi
done

NARR=""
if [[ $HAS_NARR -eq 1 ]]; then
    NARR="$TMP/narr.m4a"
    ffmpeg -y -loglevel error -f concat -safe 0 -i "$NARR_LIST" -c:a aac "$NARR"
fi

# --- 4. Mix audio (narration + bgm, ducked) ---
AUDIO=""
if [[ -n "$NARR" && -f "$BGM" ]]; then
    AUDIO="$TMP/audio.m4a"
    ffmpeg -y -loglevel error -i "$NARR" -i "$BGM" -filter_complex \
        "[0:a]volume=1.0[a0];\
         [1:a]volume=0.25,aloop=loop=-1:size=2e9[a1];\
         [a0][a1]amix=inputs=2:duration=first:dropout_transition=0[aout]" \
        -map "[aout]" -t "$DUR" -c:a aac "$AUDIO"
elif [[ -n "$NARR" ]]; then
    AUDIO="$NARR"
elif [[ -f "$BGM" ]]; then
    AUDIO="$TMP/audio.m4a"
    ffmpeg -y -loglevel error -i "$BGM" -filter_complex \
        "[0:a]volume=0.4,aloop=loop=-1:size=2e9[aout]" \
        -map "[aout]" -t "$DUR" -c:a aac "$AUDIO"
fi

# --- 5. Final mux (+ optional subtitle burn-in) ---
VF_ARGS=()
if [[ -f "$SRT" ]]; then
    # ffmpeg subtitle filter needs ":" and "'" escaped inside the filter string.
    SRT_ESC=$(printf '%s' "$SRT" | sed -e "s/\\\\/\\\\\\\\/g" -e "s/:/\\\\:/g" -e "s/'/\\\\'/g")
    VF_ARGS=(-vf "subtitles='${SRT_ESC}'")
fi

if [[ -n "$AUDIO" ]]; then
    ffmpeg -y -loglevel error -i "$SILENT" -i "$AUDIO" \
        -map 0:v -map 1:a \
        "${VF_ARGS[@]}" \
        -c:v libx264 -pix_fmt yuv420p -c:a aac -shortest "$OUT"
else
    ffmpeg -y -loglevel error -i "$SILENT" \
        "${VF_ARGS[@]}" \
        -c:v libx264 -pix_fmt yuv420p "$OUT"
fi

echo "wrote $OUT (${DUR}s, ${TARGET_W}x${TARGET_H})"
