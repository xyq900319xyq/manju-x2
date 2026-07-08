# Hermes Profile Structure Bug

## The Bug

`profiles.dat` is a password-protected zip that extracts profile directories (`storyboard/`, `asset-designer/`, `seedance-prompt/`) directly into the temp directory. But Hermes CLI expects them wrapped in a `profiles/` subdirectory:

```
# What profiles.dat extracts:
MSIxxx/storyboard/config.yaml
MSIxxx/asset-designer/config.yaml

# What Hermes expects:
MSIxxx/profiles/storyboard/config.yaml
MSIxxx/profiles/asset-designer/config.yaml
```

When the structure is wrong, Hermes says: `Error: Profile 'storyboard' does not exist. Create it with: hermes profile create storyboard`

## The Fix

### Launcher (decrypt function)
After extracting profiles.dat, wrap contents in `profiles/`:
```python
profiles_dir = os.path.join(tmp, "profiles")
if not os.path.exists(profiles_dir):
    os.makedirs(profiles_dir)
    for item in os.listdir(tmp):
        if item != "profiles":
            shutil.move(os.path.join(tmp, item), os.path.join(profiles_dir, item))
tmp = profiles_dir  # Now tmp points to the profiles/ dir
```

### Server (_find_profiles_base function)
Search for `profiles/storyboard/config.yaml`:
```python
for d in os.listdir(_tmp.gettempdir()):
    if d.startswith("MSI"):
        p = os.path.join(_tmp.gettempdir(), d)
        if os.path.exists(os.path.join(p, "profiles", "storyboard", "config.yaml")):
            return p
```

### Server (HERMES_HOME)
Set HERMES_HOME to the ROOT (the MSI temp dir), NOT the profile subdirectory:
```python
env["HERMES_HOME"] = base  # base = MSIxxx/profiles/
# Hermes internally appends profile_name to find config.yaml
```

## Verification
```bash
# After decrypt, check structure:
ls %TEMP%/MSI*/profiles/storyboard/config.yaml
ls %TEMP%/MSI*/profiles/asset-designer/config.yaml
ls %TEMP%/MSI*/profiles/seedance-prompt/config.yaml
```
