"""v1.1.5.14 发布脚本(raw binary POST)。"""
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
TAG = "v1.1.5.14"
TITLE = "漫剧助手X-2 v1.1.5.14 \u2014 \u88c5\u524d\u6574\u76ee\u5f55\u5220 _internal/(\u5f7b\u5e95\u89e3\u51b3 v1.1.5.13 \u88c5\u4e0d\u4e0a\u95ee\u9898)"

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: 需要环境变量 MANJU_X2_PAT")


def _load_body():
    p = ROOT / "docs" / "更新日志.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.14.*?(?=\n## v1\.1\.5\.13\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: docs/更新日志.md 找不到 v1.1.5.14 段")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.14_Setup.exe"
    md5 = (RELEASE_DIR / "X-2_v1.1.5.14_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.14_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += f"""

## 安装包校验

- 文件: `X-2_v1.1.5.14_Setup.exe`
- 大小: {size:,} bytes ({size / 1024 / 1024:.2f} MB)
- MD5: `{md5}`
- SHA256: `{sha256}`

## 升级方式

覆盖安装即可。也可在软件内点"检查更新"一键升级。

> ⚠️ **重点修复**: v1.1.5.13 之前的所有版本(包括 v1.1.5.8~v1.1.5.13)装完都还是 v1.1.4,
> 根因是 Inno Setup 装时 `{app}\\_internal\\` 整目录被 Windows 锁住(hermes.exe 子进程 / Defender
> 实时扫描 / 360 占用),`[Files]` 段 `restartreplace` flag 对单个被锁文件生效但对几千
> 个 _internal 文件效率极低且经常失败,装完后 launcher EXE 换了但 _internal/ 还是
> 旧文件 → 启动显示 v1.1.4。
>
> v1.1.5.14 加 `procedure CurStepChanged(CurStep: TSetupStep)`,在 Inno Setup 装文件**前**
> (`ssInstall` 阶段)主动:
> 1. taskkill 杀光 `漫剧助手X-2.exe` / `hermes.exe` / `python.exe` / `pythonw.exe`
> 2. Sleep 3 秒等 Windows 文件句柄完全释放
> 3. `cmd /C del /F /Q "{app}\\漫剧助手X-2.exe"` 强删 launcher EXE + 改名 .locked 兜底
> 4. `cmd /C rmdir /S /Q "{app}\\_internal\\"` 强删整目录 + 改名 .internal.locked 兜底
> 然后 Inno Setup 装到**干净目录**,绝对没文件锁。
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
    print("== 发布 v1.1.5.14 ==")
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
    for name in ["X-2_v1.1.5.14_Setup.exe", "X-2_v1.1.5.14_Setup.exe.md5", "X-2_v1.1.5.14_Setup.exe.sha256"]:
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
