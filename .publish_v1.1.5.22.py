"""v1.1.5.22 发布脚本 — 修复新用户首次启动闪退 BUG。

跟 .publish_v1.1.5.21.py 一样的 raw binary POST 流程,不 patch 旧 release。
"""
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
NEW_TAG = "v1.1.5.22"
NEW_TITLE = "manju-x2 v1.1.5.22 - P0 修复:新用户填完 API 后软件闪退无法启动"

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: need MANJU_X2_PAT env var")


def _request(method, url, body=None, content_type=None):
    headers = {"Authorization": "Bearer " + TOKEN, "User-Agent": "manju-x2-publisher/1.0"}
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


def _load_body():
    p = ROOT / "docs" / "\u66f4\u65b0\u65e5\u5fd7.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.22.*?(?=\n## v1\.1\.5\.21\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: changelog v1.1.5.22 not found")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.22_Setup.exe"
    if not setup.exists():
        sys.exit("ERROR: missing " + str(setup) + ",run build_x2.py first")
    md5 = (RELEASE_DIR / "X-2_v1.1.5.22_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.22_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += "\n\n## Installer\n\n"
    body += "- File: X-2_v1.1.5.22_Setup.exe\n"
    body += "- Size: " + str(size) + " bytes (" + str(round(size / 1024 / 1024, 2)) + " MB)\n"
    body += "- MD5: " + md5 + "\n"
    body += "- SHA256: " + sha256 + "\n"
    return body


def main():
    api = "https://api.github.com/repos/" + OWNER + "/" + REPO
    print("== publish v1.1.5.22 ==")

    # 1) 找 v1.1.5.22 release 是否已存在
    code, txt = _request("GET", api + "/releases/tags/" + NEW_TAG)
    if code == 200:
        rel = json.loads(txt)
        rel_id = rel["id"]
        for a in rel.get("assets", []):
            print("   - delete old v1.1.5.22 asset " + a["name"])
            _request("DELETE", api + "/releases/assets/" + str(a["id"]))
    elif code == 404:
        rel_id = None
    else:
        sys.exit("find v1.1.5.22 release failed: HTTP " + str(code))

    # 2) 创/更新 v1.1.5.22 release
    body = _load_body()
    payload = {"tag_name": NEW_TAG, "name": NEW_TITLE, "body": body, "draft": False, "prerelease": False}
    if rel_id is None:
        code, txt = _request("POST", api + "/releases", json.dumps(payload), "application/json")
    else:
        code, txt = _request("PATCH", api + "/releases/" + str(rel_id), json.dumps(payload), "application/json")
    if code not in (200, 201):
        sys.exit("release v1.1.5.22 failed: HTTP " + str(code) + " " + txt)
    rel = json.loads(txt)
    print("   OK release v1.1.5.22 " + ("created" if rel_id is None else "updated") + " url=" + rel.get("html_url", ""))

    # 3) 上传 v1.1.5.22 资产 (raw binary POST,不用 multipart - 硬约束 v1.1.1)
    upload_url = rel["upload_url"].split("{")[0]
    for name in ["X-2_v1.1.5.22_Setup.exe", "X-2_v1.1.5.22_Setup.exe.md5", "X-2_v1.1.5.22_Setup.exe.sha256"]:
        path = RELEASE_DIR / name
        if not path.exists():
            sys.exit("missing " + str(path))
        with open(path, "rb") as f:
            data = f.read()
        url = upload_url + "?name=" + urllib.parse.quote(name, safe="")
        code, txt = _request("POST", url, data, "application/octet-stream")
        if code not in (200, 201):
            sys.exit("upload " + name + " failed: HTTP " + str(code) + " " + txt)
        asset = json.loads(txt)
        print("   OK uploaded " + asset.get("browser_download_url", ""))
    print("== done ==")


if __name__ == "__main__":
    main()
