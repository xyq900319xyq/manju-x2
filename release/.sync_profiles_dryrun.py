"""dry-run v2: 用正确的 SKIP 列表,显示会覆盖/删除/保留的文件。"""
from pathlib import Path

X1 = Path(r"D:\hermes\profiles")
X2 = Path(r"D:\漫剧助手\manju-x2\source\resources\hermes\profiles")

SKIP_DIRS = {
    "logs", "cron", "bin", "cache",
    "state.db", "state.db-shm", "state.db-wal",
    "response_store.db", "response_store.db-shm", "response_store.db-wal",
    "verification_evidence.db", "channel_directory.json", "gateway_state.json",
    "image_cache", "audio_cache", "output", "sandboxes", "curator",
    "hooks", "plans", "workspace", "home", "prompts", "singularity",
    "pairing", "terminal", "tests", ".archive", ".curator_backups",
    ".hub", "sessions",
}
SKIP_FILES = {
    "state.db", "state.db-shm", "state.db-wal",
    "response_store.db", "response_store.db-shm", "response_store.db-wal",
    "verification_evidence.db", "auth.json", "auth.lock", "tirith",
    "ollama_cloud_models_cache.json", "provider_models_cache.json",
    "openrouter_model_metadata.json", "models_dev_cache.json", "model_catalog.json",
    ".update_check", ".usage.json", ".usage.json.lock", ".curator_state",
    ".bundled_manifest", ".skills_prompt_snapshot.json", "lock.json",
    ".jobs.lock", ".tick.lock", ".__agent.lock", ".__errors.lock", ".__gui.lock",
    "ticker_heartbeat", "ticker_last_success",
    "skills.tar.gz", "manifest.json",
}

X2_ONLY_DIRS = {
    "skills/agnes-ai-api",
    "skills/asset-designer-core",
    "skills/creative/novel-screenplay-adaptation",
    "skills/creative/script-asset-designer",
    "skills/creative/seedance-prompt-generator",
    "skills/juben-app",
}


def should_skip(rel: Path) -> bool:
    parts = set(rel.parts)
    if parts & SKIP_DIRS:
        return True
    name = rel.name
    if name in SKIP_FILES:
        return True
    if name.endswith(".lock"):
        return True
    return False


for profile in ["asset-designer", "seedance-prompt", "storyboard"]:
    src, dst = X1 / profile, X2 / profile
    bar = "=" * 60
    print("\n" + bar)
    print("## " + profile)
    print(bar)
    copy_list, del_list = [], []
    skip_count = 0

    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if should_skip(rel):
            skip_count += 1
            continue
        target = dst / rel
        rel_str = str(rel).replace("\\", "/")
        if not target.exists() or p.read_bytes() != target.read_bytes():
            copy_list.append(rel_str)

    for p in dst.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(dst)
        rel_str = str(rel).replace("\\", "/")
        if any(rel_str == k or rel_str.startswith(k + "/") for k in X2_ONLY_DIRS):
            continue
        if should_skip(rel):
            continue
        if not (src / rel).exists():
            del_list.append(rel_str)

    print(f"  覆盖/新增: {len(copy_list)} 个")
    for f in copy_list[:10]:
        print(f"    COPY  {f}")
    if len(copy_list) > 10:
        print(f"    ... 及其他 {len(copy_list) - 10} 个")
    print(f"  X-2 独有要删: {len(del_list)} 个")
    for f in del_list[:10]:
        print(f"    DEL   {f}")
    if len(del_list) > 10:
        print(f"    ... 及其他 {len(del_list) - 10} 个")
    print(f"  跳过(运行时): {skip_count} 个")
    print(f"  X-2 保留(manju自加): 6 个 SKILL.md 目录树")
