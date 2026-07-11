"""v1.1.5.17 发布脚本(raw binary POST)。"""
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
TAG = "v1.1.5.17"
TITLE = "manju-x2 v1.1.5.17 - takeown + icacls unlock Windows file lock"

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: need MANJU_X2_PAT env var")


def _load_body():
    p = ROOT / "docs" / "更新日志.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.17.*?(?=\n## v1\.1\.5\.16\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: changelog not found")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.17_Setup.exe"
    md5 = (RELEASE_DIR / "X-2_v1.1.5.17_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.17_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += "\n\n## Installer\n\n"
    body += "- File: X-2_v1.1.5.17_Setup.exe\n"
    body += "- Size: " + str(size) + " bytes (" + str(round(size / 1024 / 1024, 2)) + " MB)\n"
    body += "- MD5: " + md5 + "\n"
    body += "- SHA256: " + sha256 + "\n"
    return body


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


def main():
    api = "https://api.github.com/repos/" + OWNER + "/" + REPO
    print("== publish v1.1.5.17 ==")
    code, txt = _request("GET", api + "/releases/tags/" + TAG)
    if code == 200:
        rel = json.loads(txt)
        rel_id = rel["id"]
        for a in rel.get("assets", []):
            print("   - delete asset " + a["name"])
            _request("DELETE", api + "/releases/assets/" + str(a["id"]))
    elif code == 404:
        rel_id = None
    else:
        sys.exit("find release failed: HTTP " + str(code))

    body = _load_body()
    payload = {"tag_name": TAG, "name": TITLE, "body": body, "draft": False, "prerelease": False}
    if rel_id is None:
        code, txt = _request("POST", api + "/releases", json.dumps(payload), "application/json")
    else:
        code, txt = _request("PATCH", api + "/releases/" + str(rel_id), json.dumps(payload), "application/json")
    if code not in (200, 201):
        sys.exit("release failed: HTTP " + str(code) + " " + txt)
    rel = json.loads(txt)
    print("   OK release " + ("created" if rel_id is None else "updated") + " url=" + rel.get("html_url", ""))

    upload_url = rel["upload_url"].split("{")[0]
    for name in ["X-2_v1.1.5.17_Setup.exe", "X-2_v1.1.5.17_Setup.exe.md5", "X-2_v1.1.5.17_Setup.exe.sha256"]:
        path = RELEASE_DIR / name
        with open(path, "rb") as f:
            data = f.read()
        url = upload_url + "?name=" + urllib.parse.quote(name, safe="")
        code, txt = _request("POST", url, data, "application/octet-stream")
        if code not in (200, 201):
            sys.exit("upload " + name + " failed")
        asset = json.loads(txt)
        print("   OK uploaded " + asset.get("browser_download_url", ""))
    print("== done ==")


if __name__ == "__main__":
    main()
