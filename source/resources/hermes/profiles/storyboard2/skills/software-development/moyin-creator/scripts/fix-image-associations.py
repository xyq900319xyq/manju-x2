#!/usr/bin/env python3
"""
Fix broken image associations in Moyin Creator project data.
Matches PNG files in media/scenes/ to scene records by timestamp,
then patches scenes.json and sclass.json with correct imageUrl values.

Usage: python3 fix_moyin_images.py <project_dir> <project_id>
Example: python3 fix_moyin_images.py "/mnt/d/魔因项目" "80120cc3-122b-49ba-b1f8-ba98ff2b992c"
"""
import json, os, glob, shutil, sys
from datetime import datetime

def main():
    if len(sys.argv) < 3:
        print("Usage: fix_moyin_images.py <project_dir> <project_id>")
        print("Example: fix_moyin_images.py '/mnt/d/魔因项目' '80120cc3-122b-49ba-b1f8-ba98ff2b992c'")
        sys.exit(1)

    project_dir = sys.argv[1]
    project_id = sys.argv[2]

    scenes_file = os.path.join(project_dir, f'projects/_p/{project_id}/scenes.json')
    sclass_file = os.path.join(project_dir, f'projects/_p/{project_id}/sclass.json')
    media_dir = os.path.join(project_dir, 'media/scenes')

    # Validate paths
    for f in [scenes_file, sclass_file]:
        if not os.path.exists(f):
            print(f"ERROR: File not found: {f}")
            sys.exit(1)

    # Backup
    for f in [scenes_file, sclass_file]:
        backup = f + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        shutil.copy2(f, backup)
        print(f"Backed up: {backup}")

    # Build PNG timestamp map
    png_map = {}
    for p in glob.glob(os.path.join(media_dir, '*.png')):
        fname = os.path.basename(p)
        ts_str = fname.split('_')[0]
        try:
            png_map[int(ts_str)] = {'fname': fname, 'size': os.path.getsize(p)}
        except ValueError:
            pass

    print(f"Found {len(png_map)} PNG files in {media_dir}")

    # Fix scenes
    with open(scenes_file) as f:
        scenes_data = json.load(f)

    scenes = scenes_data.get('state', {}).get('scenes', [])
    fixed_scenes = 0

    for s in scenes:
        sid = s.get('id', '')
        parts = sid.split('_')
        scene_ts = int(parts[0]) if parts and parts[0].isdigit() else s.get('createdAt', 0)
        if not scene_ts:
            continue

        # Find closest PNG by timestamp (within 500ms)
        best = min(
            ((abs(ts - scene_ts), info) for ts, info in png_map.items()),
            key=lambda x: x[0]
        )
        diff, info = best
        if diff > 500:
            continue

        expected_url = f'local-image://scenes/{info["fname"]}'
        current_url = s.get('imageUrl', '') or ''

        if current_url != expected_url:
            s['imageUrl'] = expected_url
            s['imageStatus'] = 'completed'
            s['imageProgress'] = 100
            s['imageError'] = None
            fixed_scenes += 1
            print(f"  Fixed: {s.get('name', '?')} → {info['fname']}")

    with open(scenes_file, 'w') as f:
        json.dump(scenes_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"scenes.json: {fixed_scenes} fixed")

    # Fix sclass grid
    with open(sclass_file) as f:
        sclass_data = json.load(f)

    groups = sclass_data.get('state', {}).get('projectData', {}).get('shotGroups', [])
    if groups:
        # Find the largest recent PNG as candidate grid image
        all_pngs = [(info['size'], info['fname']) for info in png_map.values()]
        all_pngs.sort(reverse=True)
        grid_fname = all_pngs[0][1] if all_pngs else None

        if grid_fname:
            g = groups[0]
            grid_url = f'local-image://scenes/{grid_fname}'
            if g.get('gridImageUrl') != grid_url:
                g['gridImageUrl'] = grid_url
                entry = {
                    "id": f"recovery_{int(datetime.now().timestamp()*1000)}",
                    "timestamp": int(datetime.now().timestamp() * 1000),
                    "action": "recovered_grid",
                    "imageUrl": grid_url,
                    "status": "completed"
                }
                g.setdefault('groupBoardHistory', []).append(entry)
                print(f"sclass.json: gridImageUrl → {grid_fname}")

    with open(sclass_file, 'w') as f:
        json.dump(sclass_data, f, ensure_ascii=False, separators=(',', ':'))

    print("\nDone. Restart Moyin Creator to see results.")

if __name__ == '__main__':
    main()
