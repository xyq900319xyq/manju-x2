#!/usr/bin/env python3
"""Quick atom tree inspector for MOV/MP4 files. Run: python3 inspect_atoms.py <file>"""

import struct
import sys

def dump_atoms(filepath, depth=3):
    with open(filepath, 'rb') as f:
        fsize = f.seek(0, 2)
        f.seek(0)
        pos = 0
        while pos < fsize and depth >= 0:
            f.seek(pos)
            if pos + 8 > fsize:
                break
            size = struct.unpack('>I', f.read(4))[0]
            tag = f.read(4).decode('latin-1', errors='replace')
            if size < 8 or pos + size > fsize:
                break
            # 64-bit extended size
            if size == 1 and pos + 16 <= fsize:
                size = struct.unpack('>Q', f.read(8))[0]
            print(f'{"  " * depth}pos={pos:>10} size={size:>10} tag={tag}')
            if tag in ('moov', 'trak', 'mdia', 'minf', 'stbl', 'udta', 'meta', 'ilst'):
                depth -= 1
            pos += size

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f'Usage: {sys.argv[0]} <file>')
        sys.exit(1)
    dump_atoms(sys.argv[1])
