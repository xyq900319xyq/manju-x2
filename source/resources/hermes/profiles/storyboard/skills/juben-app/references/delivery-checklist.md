# Pre-Delivery Checklist

Run EVERY step before zipping and sending to user. Any failure = do NOT deliver.

## 1. Runtime Health
```bash
runtime/python.exe -c "import flask,waitress,yaml,requests,hermes_cli;print('OK')"
```

## 2. Server Startup
```bash
runtime/python.exe app/server.pyc
# Should output: Storyboard App v4 启动: http://localhost:5000
# Then: * Running on http://127.0.0.1:5000
# Kill after confirming with Ctrl+C
```

## 3. Import Sanity
```bash
grep "^import" server.py | grep -c "sys"  # must return 1
grep "{{" launcher.py                       # must return 0 matches
grep "{repr(secret)}" launcher.py           # must return 0 matches
```

## 4. API Flow Test (using Flask test client)
```python
import sys, os, json, yaml, time
os.environ["USER_DATA"] = os.path.join(os.environ["APPDATA"], "Juben")
sys.path.insert(0, "app")
import importlib.util
spec = importlib.util.spec_from_file_location("server", "app/server.pyc")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

with server.app.test_client() as c:
    # Save API
    with open(os.path.expanduser("~/.hermes/profiles/storyboard/config.yaml")) as f:
        cfg = yaml.safe_load(f)["model"]
    r = c.post("/api/settings/hermes-config", json={
        "api_key": cfg["api_key"], "base_url": cfg["base_url"],
        "model": cfg["default"], "provider": cfg["provider"]
    })
    assert r.get_json().get("ok"), f"API save failed: {r.get_json()}"
    
    # Create project
    r = c.post("/api/projects", json={"name":"e2e_check"})
    pid = r.get_json()["id"]
    
    # Create episode
    r = c.post(f"/api/projects/{pid}/episodes", json={
        "title":"test","script":"主角走在街上","episode_num":1,"generate":False
    })
    eid = r.get_json()["episode_id"]
    
    # Generate
    r = c.post(f"/api/projects/{pid}/episodes/{eid}/generate", json={})
    task_id = r.get_json().get("task_id")
    assert task_id, "Generate failed to return task_id"
    
    # Wait for completion
    for i in range(60):
        time.sleep(5)
        r = c.get(f"/api/projects/{pid}")
        ep = next(e for e in r.get_json()["episodes"] if e["id"]==eid)
        if ep["status"] == "completed":
            assert len(ep.get("storyboard","")) > 100, "Storyboard too short"
            break
        elif ep["status"] == "error":
            raise Exception(f"Generation failed: {ep.get('storyboard','')}")
    else:
        raise Exception("Generation timed out")
    
    # Asset extraction
    r = c.post(f"/api/projects/{pid}/extract-assets", json={})
    assert r.get_json().get("asset_cache") or r.get_json().get("ok"), "Asset extraction failed"
    
    # Seedance prompt
    r = c.post(f"/api/projects/{pid}/episodes/{eid}/generate-prompt", json={})
    assert r.get_json().get("task_id"), "Prompt generation failed to return task_id"

print("✅ ALL E2E TESTS PASSED")
```

## 5. Zip Contents
```python
import zipfile, marshal
with zipfile.ZipFile("剧本分镜助手_v1.0.zip", 'r') as z:
    ns = z.namelist()
    required = ['剧本分镜助手.exe','app/server.pyc','runtime/python.exe','hermes/profiles.dat','dreamina.exe']
    for r in required:
        assert r in ns, f"MISSING: {r}"
    # Check server.pyc has _find_profiles_base
    z.extract('app/server.pyc', '/tmp/check')
    with open('/tmp/check/app/server.pyc','rb') as f:
        f.read(16)
        code = marshal.load(f)
    has = any(hasattr(c,'co_name') and c.co_name=='_find_profiles_base' for c in code.co_consts)
    assert has, "server.pyc missing _find_profiles_base"
    # No source leaks
    leaks = [n for n in ns if n.endswith('.py') and 'hermes' not in n and 'runtime' not in n]
    assert not leaks, f"Source files leaked: {leaks}"
print("✅ ZIP verified")
```
