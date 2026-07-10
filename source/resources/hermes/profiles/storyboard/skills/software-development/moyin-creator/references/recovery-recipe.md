# Image Recovery Recipe — Moyin Creator

## Problem
Generated images exist as PNG files in `media/scenes/` but are not linked to scene records in `scenes.json` or `sclass.json`.

## Quick diagnosis
1. Check `runtime.db` → `SELECT * FROM studio_run_tasks WHERE category LIKE '%contact%' OR category LIKE '%ortho%' ORDER BY created_at DESC`
2. If `status=completed` but `summary_json` has no `imageUrl` → bug confirmed
3. Verify PNGs exist: `ls media/scenes/ | grep {approx_timestamp}`

## Full fix script

```python
import json, os, glob, shutil
from datetime import datetime

PROJECT_DIR = '/mnt/d/魔因项目'  # adjust path
SCENES_FILE = os.path.join(PROJECT_DIR, 'projects/_p/{project-id}/scenes.json')
SCLASS_FILE = os.path.join(PROJECT_DIR, 'projects/_p/{project-id}/sclass.json')
MEDIA_DIR = os.path.join(PROJECT_DIR, 'media/scenes')

# 1. Backup
for f in [SCENES_FILE, SCLASS_FILE]:
    backup = f + '.backup_' + datetime.now().strftime('%Y%m%d_%H%M%S')
    shutil.copy2(f, backup)

# 2. Build PNG timestamp map
png_map = {}
for p in glob.glob(os.path.join(MEDIA_DIR, '*.png')):
    fname = os.path.basename(p)
    ts_str = fname.split('_')[0]
    try:
        png_map[int(ts_str)] = fname
    except ValueError:
        pass

# 3. Load scenes and match
with open(SCENES_FILE) as f:
    scenes_data = json.load(f)

scenes = scenes_data['state']['scenes']
for s in scenes:
    sid = s.get('id', '')
    parts = sid.split('_')
    scene_ts = int(parts[0]) if parts and parts[0].isdigit() else s.get('createdAt', 0)
    if not scene_ts:
        continue
    
    # Find closest PNG by timestamp
    best_fname = min(png_map.items(), key=lambda x: abs(x[0] - scene_ts))[1]
    
    # Fix imageUrl
    s['imageUrl'] = f'local-image://scenes/{best_fname}'
    s['imageStatus'] = 'completed'
    s['imageProgress'] = 100
    s['imageError'] = None

with open(SCENES_FILE, 'w') as f:
    json.dump(scenes_data, f, ensure_ascii=False, separators=(',', ':'))

# 4. Fix sclass.json — find the contact-sheet grid PNG
all_pngs = glob.glob(os.path.join(MEDIA_DIR, '*.png'))
all_pngs.sort(key=os.path.getmtime, reverse=True)
# The grid composite is typically the largest PNG near the contact-sheet task time
grid_png = max(all_pngs, key=os.path.getsize)

with open(SCLASS_FILE) as f:
    sclass_data = json.load(f)

groups = sclass_data['state']['projectData'].get('shotGroups', [])
if groups:
    g = groups[0]  # or find by name
    g['gridImageUrl'] = f'local-image://scenes/{os.path.basename(grid_png)}'
    entry = {
        "id": f"recovery_{int(datetime.now().timestamp()*1000)}",
        "timestamp": int(datetime.now().timestamp() * 1000),
        "action": "recovered_grid",
        "imageUrl": g['gridImageUrl'],
        "status": "completed"
    }
    g.setdefault('groupBoardHistory', []).append(entry)

with open(SCLASS_FILE, 'w') as f:
    json.dump(sclass_data, f, ensure_ascii=False, separators=(',', ':'))

print("Done. Restart Moyin Creator to see results.")
```

## Verification
After fix, check:
- `scenes.json` → each scene has `imageUrl` starting with `local-image://scenes/`
- `sclass.json` → first group has `gridImageUrl` set
- Restart software → images should appear in scene library and S-Class grid view
