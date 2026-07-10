"""精准对比 X-1 (D:\\hermes) vs X-2 (manju-x2 repo) 3 个 profile 的所有文件。
用 md5 hash 比对,看内容是否真的一致。
"""
import hashlib
from pathlib import Path


def file_hash(p: Path) -> str:
    if not p.exists():
        return "(缺)"
    try:
        h = hashlib.md5()
        h.update(p.read_bytes())
        return h.hexdigest()[:12]
    except Exception as e:
        return f"(err:{type(e).__name__})"


X1 = Path(r"D:\hermes\profiles")
X2 = Path(r"D:\漫剧助手\manju-x2\source\resources\hermes\profiles")

SKIP_PATTERNS = [
    "logs", "cron", "cache", "state.db", ".lock", ".env",
    "auth.lock", "state.db-shm", "state.db-wal",
    "response_store.db", "response_store.db-shm", "response_store.db-wal",
    "verification_evidence.db", "channel_directory.json", "gateway_state.json",
    "models_dev_cache.json", "auth.json", "tirith",
    ".bundled_manifest", ".update_check", ".usage.json", ".curator_state",
    ".hub", ".skills_prompt_snapshot.json", "scripts",
    ".archive", "skills/skills",  # X-2 seedance-prompt 里嵌套的奇怪路径
]


def is_skipped(p: Path) -> bool:
    rel = p.relative_to(p.parents[len(p.parts) - p.parent.parts.__len__():][0]) if False else p
    s = str(p).replace("\\", "/")
    for pat in SKIP_PATTERNS:
        if pat in s:
            return True
    return False


for prof in ["asset-designer", "seedance-prompt", "storyboard"]:
    print(f"\n{'=' * 80}\n## profile: {prof}\n{'=' * 80}")
    p1 = X1 / prof
    p2 = X2 / prof

    # 1. SOUL.md / MEMORY.md / config.yaml 单独对比
    for fname in ["SOUL.md", "config.yaml", "memories/MEMORY.md", "memories/USER.md"]:
        f1 = p1 / fname
        f2 = p2 / fname
        h1, h2 = file_hash(f1), file_hash(f2)
        if h1 == "(缺)" and h2 == "(缺)":
            continue
        marker = "OK" if h1 == h2 else "DIFF"
        if h1 == "(缺)":
            marker = "X-2独有"
        elif h2 == "(缺)":
            marker = "X-1独有"
        print(f"  [{marker:8s}] {fname:30s}  X-1={h1}  X-2={h2}  size X-1={f1.stat().st_size if f1.exists() else 0:,} X-2={f2.stat().st_size if f2.exists() else 0:,}")

    # 2. SKILL.md 全递归
    skills1 = {}
    skills2 = {}
    for p in p1.rglob("*"):
        if not p.is_file():
            continue
        if is_skipped(p):
            continue
        if p.name in ("SKILL.md", "DESCRIPTION.md"):
            rel = p.relative_to(p1)
            skills1[str(rel).replace("\\", "/")] = file_hash(p)

    for p in p2.rglob("*"):
        if not p.is_file():
            continue
        if is_skipped(p):
            continue
        if p.name in ("SKILL.md", "DESCRIPTION.md"):
            rel = p.relative_to(p2)
            skills2[str(rel).replace("\\", "/")] = file_hash(p)

    all_keys = sorted(set(skills1) | set(skills2))
    same = diff = x1_only = x2_only = 0
    for k in all_keys:
        v1 = skills1.get(k, "(缺)")
        v2 = skills2.get(k, "(缺)")
        if v1 == "(缺)":
            print(f"  [X-2独有] {k}")
            x2_only += 1
        elif v2 == "(缺)":
            print(f"  [X-1独有] {k}")
            x1_only += 1
        elif v1 == v2:
            same += 1
        else:
            print(f"  [内容DIFF] {k}  X-1={v1}  X-2={v2}")
            diff += 1
    print(f"  → SKILL.md+DESCRIPTION.md: 一致 {same} / 内容不同 {diff} / X-1独有 {x1_only} / X-2独有 {x2_only}")
