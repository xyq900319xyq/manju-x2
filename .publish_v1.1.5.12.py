"""v1.1.5.12 发布脚本(raw binary POST)。"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

OWNER = "xyq900319xyq"
REPO = "manju-x2"
TAG = "v1.1.5.12"
TITLE = "漫剧助手X-2 v1.1.5.12 — 一键更新彻底修根因(dlg 挡 QMessageBox)"

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: 需要环境变量 MANJU_X2_PAT")


def _load_body():
    p = ROOT / "docs" / "更新日志.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.12.*?(?=\n## v1\.1\.5\.11\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: docs/更新日志.md 找不到 v1.1.5.12 段")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.12_Setup.exe"
    md5 = (RELEASE_DIR / "X-2_v1.1.5.12_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.12_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += f"""

## 安装包校验

- 文件: `X-2_v1.1.5.12_Setup.exe`
- 大小: {size:,} bytes ({size / 1024 / 1024:.2f} MB)
- MD5: `{md5}`
- SHA256: `{sha256}`

## 升级方式

覆盖安装即可,设置/数据/模型配置不丢(v1.1.5.3 修的)。也可在软件内点"检查更新"一键升级。

> ⚠️ 如果你之前装 v1.1.5.8 ~ v1.1.5.11 没生效(更新后还是老版本),这次新版彻底解了 dlg 挡 QMessageBox 问题,会真正完成 EXE 替换。
> ⚠️ 如果你**还停留在 v1.1.4**,自己的一键更新 BUG 让一键更新失败,需要**手动**关 manju-x2 → 双击 `X-2_v1.1.5.12_Setup.exe` 装。
"""
    return body


def _request(method, url, body=None, content_type=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "manju-x2-publisher/1.0"}
    if content_type:
        headers["Content-Type"] = content_type
    data = body.encode("utf-8") if isinstance(body, str) else body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = None
    try:
        import ssl
        ctx = ssl._create_unverified_context()
    except Exception:
        pass
    try:
        with urllib.request.urlopen(req, timeout=60, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")


def main():
    api = f"https://api.github.com/repos/{OWNER}/{REPO}"
    print("== 发布 v1.1.5.12 ==")
    print("1) get release by tag (查是否已存在)...")
    code, txt = _request("GET", f"{api}/releases/tags/{TAG}")
    if code == 200:
        rel = json.loads(txt)
        rel_id = rel["id"]
        for a in rel.get("assets", []):
            print(f"   - delete asset {a['name']} (id={a['id']})")
            _request("DELETE", f"{api}/releases/assets/{a['id']}")
    elif code == 404:
        rel_id = None
    else:
        sys.exit(f"查 release 失败: HTTP {code} {txt}")

    body = _load_body()
    payload = {"tag_name": TAG, "name": TITLE, "body": body, "draft": False, "prerelease": False}
    if rel_id is None:
        print("2) create release...")
        code, txt = _request("POST", f"{api}/releases", json.dumps(payload), "application/json")
    else:
        print("2) update release...")
        code, txt = _request("PATCH", f"{api}/releases/{rel_id}", json.dumps(payload), "application/json")
    if code not in (200, 201):
        sys.exit(f"release 失败: HTTP {code} {txt}")
    rel = json.loads(txt)
    print(f"   ✓ release {'created' if rel_id is None else 'updated'} id={rel['id']}  url={rel.get('html_url')}")

    upload_url = rel["upload_url"].split("{")[0]
    for name in ["X-2_v1.1.5.12_Setup.exe", "X-2_v1.1.5.12_Setup.exe.md5", "X-2_v1.1.5.12_Setup.exe.sha256"]:
        path = RELEASE_DIR / name
        size = path.stat().st_size
        print(f"3) upload {name} ({size:,} bytes)...")
        with open(path, "rb") as f:
            data = f.read()
        url = upload_url + "?name=" + urllib.parse.quote(name, safe="")
        code, txt = _request("POST", url, data, "application/octet-stream")
        if code not in (200, 201):
            sys.exit(f"upload {name} 失败: HTTP {code} {txt}")
        asset = json.loads(txt)
        print(f"   ✓ uploaded  url={asset.get('browser_download_url')}")

    print()
    print("== 发布成功 ==")
    print(f"release URL: {rel.get('html_url')}")


if __name__ == "__main__":
    main()
