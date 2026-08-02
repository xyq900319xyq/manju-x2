"""v1.1.5.21 发布脚本(安全补丁) — raw binary POST,改 v1.1.5.20 release 加警告,发 v1.1.5.21。"""
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
OLD_TAG = "v1.1.5.20"
NEW_TAG = "v1.1.5.21"
NEW_TITLE = "manju-x2 v1.1.5.21 - \u5b89\u5168\u8865\u4e01(\u6e05\u7406 hermes profile \u6cc4\u9732\u7684\u7528\u6237 API key)"

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


def _patch_old_release_warning(api, rel_id, old_body):
    """v1.1.5.20 release 顶部加警告横幅(不删 release,保留 download link)。"""
    warn = (
        "> :warning: **\u5b89\u5168\u63d0\u9192\uff1a\u672c\u7248\u672c\u7684 4 \u4e2a hermes profile (asset-designer / seedance-prompt / storyboard / storyboard2) "
        "\u7684 config.yaml \u542b\u7528\u6237 API key \u6cc4\u9732\u3002\u8bf7\u7acb\u5373\u5347\u7ea7\u5230 v1.1.5.21 \u6216\u4ee5\u540e\u7248\u672c,"
        "\u5e76\u53bb DeepSeek / Agnes \u540e\u53f0\u8f6e\u6362\uff08\u5e9f\u5f03\uff09\u65e7 API key\u3002**\n\n"
        "---\n\n"
    )
    if "\u5b89\u5168\u63d0\u9192" in old_body:
        print("   - v1.1.5.20 release \u5df2\u6709\u8b66\u544a,\u8df3\u8fc7")
        return
    new_body = warn + old_body
    payload = {"body": new_body}
    code, txt = _request("PATCH", api + "/releases/" + str(rel_id), json.dumps(payload), "application/json")
    if code not in (200, 201):
        sys.exit("patch v1.1.5.20 release body failed: HTTP " + str(code) + " " + txt)
    print("   OK v1.1.5.20 release \u5df2\u52a0\u8b66\u544a\u6a2a\u5e45")


def _load_body():
    p = ROOT / "docs" / "\u66f4\u65b0\u65e5\u5fd7.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.21.*?(?=\n## v1\.1\.5\.20\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: changelog v1.1.5.21 not found")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.21_Setup.exe"
    md5 = (RELEASE_DIR / "X-2_v1.1.5.21_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.21_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += "\n\n## Installer\n\n"
    body += "- File: X-2_v1.1.5.21_Setup.exe\n"
    body += "- Size: " + str(size) + " bytes (" + str(round(size / 1024 / 1024, 2)) + " MB)\n"
    body += "- MD5: " + md5 + "\n"
    body += "- SHA256: " + sha256 + "\n"
    return body


def main():
    api = "https://api.github.com/repos/" + OWNER + "/" + REPO
    print("== publish v1.1.5.21 ==")

    # 1) \u627e\u5230 v1.1.5.20 release \u52a0\u8b66\u544a
    code, txt = _request("GET", api + "/releases/tags/" + OLD_TAG)
    if code == 200:
        rel = json.loads(txt)
        _patch_old_release_warning(api, rel["id"], rel.get("body", ""))
    else:
        print("   - v1.1.5.20 release \u4e0d\u5b58\u5728,\u8df3\u8fc7\u8b66\u544a\u6b65\u9aa4")

    # 2) \u627e v1.1.5.21 release \u662f\u5426\u5df2\u5b58\u5728
    code, txt = _request("GET", api + "/releases/tags/" + NEW_TAG)
    if code == 200:
        rel = json.loads(txt)
        rel_id = rel["id"]
        for a in rel.get("assets", []):
            print("   - delete old v1.1.5.21 asset " + a["name"])
            _request("DELETE", api + "/releases/assets/" + str(a["id"]))
    elif code == 404:
        rel_id = None
    else:
        sys.exit("find v1.1.5.21 release failed: HTTP " + str(code))

    # 3) \u521b/\u66f4\u65b0 v1.1.5.21 release
    body = _load_body()
    payload = {"tag_name": NEW_TAG, "name": NEW_TITLE, "body": body, "draft": False, "prerelease": False}
    if rel_id is None:
        code, txt = _request("POST", api + "/releases", json.dumps(payload), "application/json")
    else:
        code, txt = _request("PATCH", api + "/releases/" + str(rel_id), json.dumps(payload), "application/json")
    if code not in (200, 201):
        sys.exit("release v1.1.5.21 failed: HTTP " + str(code) + " " + txt)
    rel = json.loads(txt)
    print("   OK release v1.1.5.21 " + ("created" if rel_id is None else "updated") + " url=" + rel.get("html_url", ""))

    # 4) \u4e0a\u4f20 v1.1.5.21 \u8d44\u4ea7
    upload_url = rel["upload_url"].split("{")[0]
    for name in ["X-2_v1.1.5.21_Setup.exe", "X-2_v1.1.5.21_Setup.exe.md5", "X-2_v1.1.5.21_Setup.exe.sha256"]:
        path = RELEASE_DIR / name
        if not path.exists():
            sys.exit("missing " + str(path))
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
