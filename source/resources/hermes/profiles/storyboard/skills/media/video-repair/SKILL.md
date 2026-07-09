---
name: video-repair
description: Diagnose and fix video files rejected by editors (剪映/CapCut, Premiere, DaVinci) that play fine in media players. Covers container issues, non-standard metadata, timebase mismatches, and broken atoms — not encoding problems.
---

# Video Repair

When a video editor says a file is "corrupted" or "damaged" but media players play it fine, the issue is almost always in the **container metadata**, not the encoded streams. Encoding problems produce visible glitches; container problems confuse parsers.

## Trigger conditions

- User says an editor (剪映/CapCut, Premiere, DaVinci, Final Cut) rejects a file
- File plays fine in VLC/MPV/Windows Media Player
- ffprobe shows warnings like "Unknown cover type", "Invalid atom", etc.
- Need to fix without changing container format or re-encoding

## Diagnostic workflow

### Step 1: Scan the file

```bash
ffprobe -v verbose -i "$FILE" 2>&1 | grep -iE "error|warning|corrupt|invalid|unknown|cover|missing"
```

Note every warning — even benign-looking ones. Editors are stricter than players.

### Step 2: Compare with a known-working sibling

If the project has other files from the same source that work:

```bash
ffprobe -v verbose -i "$WORKING_FILE" 2>&1 | grep -iE "error|warning|corrupt|invalid|unknown|cover|missing"
```

If the working file has the **same** warnings, those are NOT the cause. Look deeper.

### Step 3: Check structural differences

Compare key properties between broken and working files:

```bash
# Timebase (CRITICAL — editors are very sensitive to this)
ffprobe -v 0 -show_entries stream=codec_name,time_base,r_frame_rate -of default=noprint_wrappers=1 "$FILE"

# Atom order (moov position matters for some editors)
python3 -c "
import struct
with open('$FILE','rb') as f:
    pos=0; fsize=f.seek(0,2); f.seek(0)
    while pos<fsize:
        f.seek(pos); size=struct.unpack('>I',f.read(4))[0]; tag=f.read(4)
        print(f'{tag.decode()}@{pos}', end=' ')
        pos+=size
"
```

### Step 4: Decode test

Confirm the actual streams are intact by decoding to null:

```bash
ffmpeg -v error -i "$FILE" -f null -
```

Zero output = streams are clean. The problem is container-only.

## Common fixes

### Fix 1: Clean remux with preserved timebase

The most common issue: ffmpeg's MOV/MP4 muxer changes the video timebase to a computed value (often 1/15360) that editors reject. **Always specify `-video_track_timescale`** to match the original.

```bash
# For MOV (preserve container format)
ffmpeg -i "$FILE" -c copy -map 0 -video_track_timescale 30 -f mov "$OUTPUT"

# For MP4
ffmpeg -i "$FILE" -c copy -map 0 -video_track_timescale 30 -f mp4 "$OUTPUT"
```

**Pitfall**: `-movflags +faststart` moves moov to the beginning. Some editors (especially older versions) expect moov at the end for MOV files. Only use faststart if you know the editor supports it.

**Pitfall**: ffmpeg remux strips iTunes-style udta metadata (`Hw`, `bitrate`, custom tags). If those matter, see "Surgical atom removal" below.

### Fix 2: Strip problematic cover art

Non-standard cover art in udta (like JSON instead of JPEG/PNG binary) can trigger "Unknown cover type" warnings. For a clean remux that drops udta entirely:

```bash
ffmpeg -i "$FILE" -c copy -map 0 -map_metadata -1 -video_track_timescale 30 -f mov "$OUTPUT"
```

### Fix 3: Surgical atom removal (preserve everything else)

When you need to keep `-video_track_timescale` intact AND preserve udta metadata, use the binary patching approach in `references/binary-atom-patching.md`.

## Support files

- `references/binary-atom-patching.md` — surgical atom removal without ffmpeg remux
- `scripts/inspect_atoms.py` — quick atom tree dump (`python3 scripts/inspect_atoms.py <file>`)

## Verification

After fixing, verify against the same criteria as the working file:

```bash
ffprobe -v verbose -i "$FIXED_FILE" 2>&1 | grep -iE "error|warning|corrupt"
# Should produce no output

ffprobe -v 0 -show_entries stream=time_base -of default=noprint_wrappers=1 "$FIXED_FILE"
# Should match working file's timebase
```

## Pitfalls

- **Never trust the first warning you see**. The file that works may have the same warning. Always compare.
- **ffmpeg `-c copy` is NOT truly lossless for MOV**. It rewrites the entire moov atom, including sample tables and timebase. Properties like stbl layout, timebase granularity, and udta structure change.
- **剪映 (CapCut) is exceptionally picky about timebase**. It expects clean integer timebases (1/30, 1/25, 1/24). Computed values like 1/15360 trigger rejection.
- **Don't change the container format unless the user asks**. MOV → MP4 changes major_brand and compatible_brands, which may break other tools in the user's pipeline.
- **Make a backup before any in-place fix**. The original file may be needed for comparison.
