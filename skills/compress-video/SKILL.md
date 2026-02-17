---
name: compress-video
description: Compresses video files (especially macOS screen recordings) using ffmpeg with visually lossless quality. Use when the user wants to compress, shrink, or reduce the size of a video or screen recording.
allowed-tools: Bash
---

# Compress Video Skill

Compresses video files using ffmpeg with visually lossless settings. Especially effective on macOS screen recordings which use unnecessarily high bitrates.

## Prerequisites

ffmpeg must be installed:

```bash
which ffmpeg || brew install ffmpeg
```

## When to Use

- User asks to "compress", "shrink", or "reduce size" of a video
- User has a large screen recording they want to share
- User mentions a `.mov` or `.mp4` file is too big

## How to Compress

### 1. Find the video

**CRITICAL: macOS screen recording filenames contain invisible Unicode characters (non-breaking spaces around AM/PM). You CANNOT use the filename as shown by `ls` directly — it WILL fail with "No such file or directory". You MUST use `find` to get a usable file path.**

To list available recordings (for display to the user only — do NOT copy-paste these filenames into commands):

```bash
ls -lt ~/Desktop/ | grep -i "screen recording" | head -10
```

To get a usable file path, ALWAYS use `find`:

```bash
FILE=$(find ~/Desktop -maxdepth 1 -name "*YYYY-MM-DD*" -print -quit)
```

Replace `YYYY-MM-DD` with the date from the `ls` output above.

### 2. Inspect the source file

```bash
ffprobe -hide_banner "$FILE" 2>&1
```

Report to the user: duration, resolution, codec, bitrate, and file size.

### 3. Compress

**IMPORTANT: Always use CRF 18 unless the user explicitly asks for a different quality level or smaller file size.** CRF 18 is visually lossless — the compressed video will look identical to the original to the human eye. Do NOT use a higher CRF value by default; only deviate if the user specifically requests it.

```bash
ffmpeg -i "$FILE" -c:v libx264 -preset slow -crf 18 -c:a copy "/path/to/output.mp4"
```

**Flags:**

| Flag | Purpose |
|------|---------|
| `-c:v libx264` | Re-encode video with H.264 |
| `-preset slow` | Better compression ratio (trades encode speed for smaller file) |
| `-crf 18` | **DEFAULT. Visually lossless. Always use this unless told otherwise.** |
| `-c:a copy` | Copy audio as-is, no re-encoding |

**Output naming convention:** Place the compressed file next to the original with "compressed" appended:

```
Original: Screen Recording 2026-02-11 at 1.15.48 PM.mov
Output:   Screen Recording 2026-02-11 compressed.mp4
```

### 4. Report results

After compression, report:
- Original size vs compressed size
- Percent reduction
- Output file path

## CRF Guide

If the user requests different quality/size tradeoffs:

| CRF | Quality | Use case |
|-----|---------|----------|
| 0 | Mathematically lossless | Archival (huge files) |
| 18 | Visually lossless | Default — no perceptible loss |
| 23 | Good quality | Smaller file, slight softening |
| 28 | Acceptable quality | Much smaller, visible loss |

Lower CRF = better quality, bigger file. Adjust if the user asks for "smaller" (try 23) or "best quality" (keep 18 or try 15).

## Tips

- Screen recordings compress extremely well (80-95% reduction) because most pixels stay static between frames
- The `slow` preset takes longer but produces noticeably smaller files than `medium` — worth it for large recordings
- Always use `-c:a copy` to avoid re-encoding audio unnecessarily
- For very long recordings (10+ minutes), consider using `-preset medium` to avoid long encode times
