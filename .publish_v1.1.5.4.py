"""v1.1.5.4 发布脚本(raw binary)。"""
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
TAG = "v1.1.5.4"
TITLE = "漫剧助手X-2 v1.1.5.4 — 清空分镜/清空 prompt/提取到视频 UI 刷新 bug 修复"

ROOT = Path(r"D:\漫剧助手\manju-x2")
RELEASE_DIR = ROOT / "release"

TOKEN = os.environ.get("MANJU_X2_PAT")
if not TOKEN:
    sys.exit("ERROR: 需要环境变量 MANJU_X2_PAT")


def _load_body():
    p = ROOT / "docs" / "更新日志.md"
    text = p.read_text(encoding="utf-8")
    m = re.search(r"## v1\.1\.5\.4.*?(?=\n## v1\.1\.5\.3\b)", text, re.DOTALL)
    if not m:
        sys.exit("ERROR: docs/更新日志.md 找不到 v1.1.5.4 段")
    body = m.group(0).rstrip()
    setup = RELEASE_DIR / "X-2_v1.1.5.4_Setup.exe"
    md5 = (RELEASE_DIR / "X-2_v1.1.5.4_Setup.exe.md5").read_text(encoding="utf-8").strip()
    sha256 = (RELEASE_DIR / "X-2_v1.1.5.4_Setup.exe.sha256").read_text(encoding="utf-8").strip()
    size = setup.stat().st_size
    body += f"""

## 安装包校验

- 文件: `X-2_v1.1.5.4_Setup.exe`
- 大小: {size:,} bytes ({size / 1024 / 1024:.2f} MB)
- MD5: `{md5}`
- SHA256: `{sha256}`

## 升级方式

覆盖安装即可,设置/数据/模型配置不丢(v1.1.5.3 修的)。也可在软件内点"检查更新"一键升级。
"""
    return body


def _create_release(body):
    url = f"https://api.github.com/repos/{OWNER}/{REPO}/releases"
    payload = json.dumps({
        "tag_name": TAG,
        "target_commitish": "main",
        "name": TITLE,
        "body": body,
        "draft": False,
        "prerelease": False,
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "manju-x2-publisher",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
            print(f"  ✓ release 创建: {data['html_url']}")
            return data["upload_url"].split("{")[0], data["id"]
    except urllib.error.HTTPError as e:
        b = e.read().decode("utf-8", errors="replace")
        if e.code == 422 and "already_exists" in b:
            print(f"  ⚠ release {TAG} 已存在,直接复用")
            with urllib.request.urlopen(urllib.request.Request(
                f"{url}/tags/{TAG}",
                headers={
                    "Authorization": f"Bearer {TOKEN}",
                    "User-Agent": "manju-x2-publisher",
                    "Accept": "application/vnd.github+json",
                },
            )) as r:
                data = json.loads(r.read().decode("utf-8"))
                return data["upload_url"].split("{")[0], data["id"]
        sys.exit(f"ERROR: 创 release 失败 {e.code}: {b}")


def _upload_asset(upload_prefix, release_id, file_path):
    name = file_path.name
    size = file_path.stat().st_size
    print(f"  上传 {name} ({size:,} bytes)...")
    body = file_path.read_bytes()
    url = f"{upload_prefix}?name={urllib.parse.quote(name)}"
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "User-Agent": "manju-x2-publisher",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/octet-stream",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode("utf-8"))
            print(f"    ✓ {name} 上传成功 ({data['size']:,} bytes)")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")
        sys.exit(f"ERROR: 上传 {name} 失败 {e.code}: {err}")


def main():
    print(f"=== 发布 {TITLE} ===\n")
    body = _load_body()
    print(f"  body 长度: {len(body)} chars")
    upload_prefix, release_id = _create_release(body)
    print()
    for fname in [
        "X-2_v1.1.5.4_Setup.exe",
        "X-2_v1.1.5.4_Setup.exe.md5",
        "X-2_v1.1.5.4_Setup.exe.sha256",
    ]:
        _upload_asset(upload_prefix, release_id, RELEASE_DIR / fname)
    print(f"\nRelease: https://github.com/{OWNER}/{REPO}/releases/tag/{TAG}")


if __name__ == "__main__":
    main()
