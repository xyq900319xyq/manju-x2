# Binary Atom Patching for MOV/MP4

Used when ffmpeg remux is too destructive (changes timebase, strips udta, rewrites stbl). This surgically removes or neutralizes a single problematic atom while leaving every other byte untouched.

## When to use

- ffmpeg remux changes timebase and you can't set `-video_track_timescale` correctly
- Need to preserve iTunes-style udta metadata that ffmpeg strips
- The only problem is one bad atom (e.g., non-standard cover art)

## Technique: Zero out a bad udta entry

Target: an ilst item with non-standard data that confuses parsers.

### Find the target

Use the atom inspector script to identify the exact offset and size:

```python
import struct

def find_atom_path(data, target_path):
    """Walk nested atoms by tag names. Returns list of (offset, size, tag)."""
    pos = 8  # skip top-level header
    result = None
    
    def search(data, offset, target_idx, path_so_far):
        nonlocal result
        if result is not None:
            return
        if target_idx >= len(target_path):
            result = path_so_far
            return
        pos = offset
        target_tag = target_path[target_idx]
        while pos < len(data):
            if pos + 8 > len(data):
                break
            size = struct.unpack('>I', data[pos:pos+4])[0]
            tag = data[pos+4:pos+8].decode('latin-1', errors='replace')
            if size < 8 or pos + size > len(data):
                break
            if tag == target_tag:
                search(data, pos + 8, target_idx + 1, path_so_far + [(pos, size, tag)])
            pos += size
    
    search(data, 0, 0, [])
    return result

# Usage: find the cover art in QuickTime metadata
with open('bad.mov', 'rb') as f:
    # Find moov atom first, then search inside udta
    ...
```

### Neutralize the entry

Once you have the offset of the problematic item inside the ilst, zero out its payload while keeping atom sizes intact:

```python
# item_offset: offset of the ilst item atom within the file
# item_size: size of the item atom
# payload_offset: offset of data payload within the item (typically 24-32 bytes in)

with open('file.mov', 'r+b') as f:
    f.seek(item_offset + payload_offset)
    payload_len = item_size - payload_offset
    f.write(b'\x00' * payload_len)
```

### Verification

After patching, verify with ffprobe and compare atom tree with a known-working sibling.

## QuickTime iTunes Metadata Structure

```
moov
  udta
    meta (hdlr='mdta')
      hdlr — handler type
      keys — key name table (index → key string)
      ilst — item list
        [key_index_1]  — item, contains 'data' atom
        [key_index_2]
        ...
```

Common keys seen in practice:
- `Hw` — hardware flag
- `bitrate` — target bitrate string
- `com.apple.quicktime.artwork` — cover art (should be JPEG/PNG binary, type 0x0D/0x0E)
- `maxrate` — max bitrate string
- `te_is_reencode` — re-encode flag
- `encoder` — encoder string (e.g., "Lavf61.1.100")

## Real-world example

A file had `com.apple.quicktime.artwork` stored as JSON with type=0 (implicit) instead of type=13 (JPEG). ffprobe warned "Unknown cover type: 0x1". The payload was 958 bytes of JSON starting with `{"data":{"editType":"default"...`.

Siblings with the same structure worked fine in the editor — the cover art was NOT the cause of rejection. The real issue was timebase change from ffmpeg remux. Lesson: always compare with working files before assuming which warning is fatal.
