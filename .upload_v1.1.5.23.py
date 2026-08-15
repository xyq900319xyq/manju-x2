"""v1.1.5.23 Setup.exe 上传脚本（curl timeout 兼容版）。

.publish_v1.1.5.23.py 用 urllib 60s / 600s 都超时,改用 http.client
直接发 raw binary POST,timeout 给 1800s(30 分钟)。
"""
import os
import ssl
import sys
import urllib.parse
from pathlib import Path

import http.client

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: need MANJU_X2_PAT env var")


def upload_asset(upload_url_template: str, name: str, file_path: Path, timeout: int = 1800):
    url = upload_url_template.split("{")[0] + "?name=" + urllib.parse.quote(name, safe="")
    print(f"[upload] {name} from {file_path}  size={file_path.stat().st_size} bytes")
    body = file_path.read_bytes()
    # urllib.parse 拿 host + path
    parsed = urllib.parse.urlparse(url)
    ctx = ssl._create_unverified_context()
    conn = http.client.HTTPSConnection(parsed.hostname, parsed.port or 443, timeout=timeout, context=ctx)
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "User-Agent": "manju-x2-publisher/1.0",
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(body)),
    }
    try:
        conn.request("POST", parsed.path + "?" + parsed.query, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read().decode("utf-8", errors="replace")
        if resp.status not in (200, 201):
            print(f"  FAIL status={resp.status} body={data[:500]}")
            return False
        print(f"  OK status={resp.status}")
        return True
    finally:
        conn.close()


def get_upload_url() -> str:
    conn = http.client.HTTPSConnection("api.github.com", timeout=60)
    conn.request(
        "GET",
        "/repos/xyq900319xyq/manju-x2/releases/tags/v1.1.5.23",
        headers={
            "Authorization": "Bearer " + TOKEN,
            "User-Agent": "manju-x2-publisher/1.0",
            "Accept": "application/vnd.github+json",
        },
    )
    resp = conn.getresponse()
    if resp.status != 200:
        sys.exit(f"find release failed: HTTP {resp.status} body={resp.read()[:500]!r}")
    import json
    data = json.loads(resp.read())
    return data["upload_url"]


def main():
    upload_url = get_upload_url()
    print(f"upload_url={upload_url}")
    for name in ["X-2_v1.1.5.23_Setup.exe", "X-2_v1.1.5.23_Setup.exe.md5", "X-2_v1.1.5.23_Setup.exe.sha256"]:
        path = RELEASE_DIR / name
        if not path.exists():
            sys.exit(f"missing {path}")
        ok = upload_asset(upload_url, name, path)
        if not ok:
            sys.exit(1)
    print("== done ==")


if __name__ == "__main__":
    main()
