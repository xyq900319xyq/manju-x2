"""全量同步 D:\\hermes\\ → manju-x2 的 3 个 profile,只覆盖核心内容,跳过运行时数据。

策略:
- 覆盖: SOUL.md / config.yaml / memories/ / skills/**/* (核心内容)
- 保留 X-2 独有的 manju 自加 6 个 SKILL.md 整个目录树
- 跳过 hermes 运行时数据(state.db / logs / cron / cache / sessions / lock / .archive / .curator_backups / .bak / .hub / tirith / auth 等)
"""
import shutil
from pathlib import Path

X1 = Path(r"D:\hermes\profiles")
X2 = Path(r"D:\漫剧助手\manju-x2\source\resources\hermes\profiles")

# 运行时数据(hermes 自己跑出来,不打包)
SKIP_DIRS = {
    "logs", "cron", "bin", "cache",  # 顶级运行时目录
    "state.db", "state.db-shm", "state.db-wal",
    "response_store.db", "response_store.db-shm", "response_store.db-wal",
    "verification_evidence.db", "channel_directory.json", "gateway_state.json",
    "image_cache", "audio_cache", "output", "sandboxes", "curator",
    "hooks", "plans", "workspace", "home", "prompts", "singularity",
    "pairing", "terminal", "tests", ".archive", ".curator_backups",
    ".hub",  # hermes hub 状态
    "sessions",  # hermes session dumps
}
SKIP_FILES = {
    # 运行时数据库 / lock
    "state.db", "state.db-shm", "state.db-wal",
    "response_store.db", "response_store.db-shm", "response_store.db-wal",
    "verification_evidence.db", "auth.json", "auth.lock", "tirith",
    # cache 文件
    "ollama_cloud_models_cache.json", "provider_models_cache.json",
    "openrouter_model_metadata.json", "models_dev_cache.json", "model_catalog.json",
    # runtime metadata
    ".update_check", ".usage.json", ".usage.json.lock", ".curator_state",
    ".bundled_manifest", ".skills_prompt_snapshot.json", "lock.json",
    # lock files
    ".jobs.lock", ".tick.lock", ".__agent.lock", ".__errors.lock", ".__gui.lock",
    # heartbeat
    "ticker_heartbeat", "ticker_last_success",
    # 备份文件
    "skills.tar.gz", "manifest.json",
}

# 运行时 lock 通配(任何 .lock 结尾都跳)
LOCK_SUFFIX = ".lock"

# X-2 manju 自加的 6 个 SKILL.md 整个目录树(storyboard profile)
X2_ONLY_STORYBOARD_DIRS = {
    "skills/agnes-ai-api",
    "skills/asset-designer-core",
    "skills/creative/novel-screenplay-adaptation",
    "skills/creative/script-asset-designer",
    "skills/creative/seedance-prompt-generator",
    "skills/juben-app",
}


def should_skip(rel_path: Path) -> bool:
    parts = set(rel_path.parts)
    for s in SKIP_DIRS:
        if s in parts:
            return True
    name = rel_path.name
    if name in SKIP_FILES:
        return True
    if name.endswith(LOCK_SUFFIX) and name != "LICENSE.lock":  # 保险
        return True
    return False


def sync_profile(profile: str, keep_x2_only_dirs: set = None):
    """从 X-1 覆盖到 X-2。
    keep_x2_only_dirs: 整个目录树(以 rel 路径前缀)保留不动
    """
    src = X1 / profile
    dst = X2 / profile
    keep_x2_only_dirs = keep_x2_only_dirs or set()
    copied = skipped = kept = 0

    # 1. 遍历 X-1,覆盖/新增到 X-2
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if should_skip(rel):
            skipped += 1
            continue
        target = dst / rel
        # 目录存在性
        target.parent.mkdir(parents=True, exist_ok=True)
        # 拷贝(覆盖或新增)
        shutil.copy2(p, target)
        copied += 1

    # 2. 遍历 X-2,删除 X-1 没有的(除了 keep 目录)
    if dst.exists():
        for p in list(dst.rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(dst)
            rel_str = str(rel).replace("\\", "/")
            # 在 keep 目录下?跳过
            if any(rel_str == k or rel_str.startswith(k + "/") for k in keep_x2_only_dirs):
                kept += 1
                continue
            if should_skip(rel):
                continue
            if not (src / rel).exists():
                p.unlink()
                # 清空目录
                parent = p.parent
                while parent != dst:
                    try:
                        next(parent.iterdir())
                        break
                    except StopIteration:
                        if parent != dst:
                            parent.rmdir()
                            parent = parent.parent

    print(f"[{profile}] copied/skipped/kept={copied}/{skipped}/{kept}")


print("=" * 60)
print("全量同步 D:\\hermes\\ → manju-x2 (3 个 profile,只覆盖核心内容)")
print("=" * 60)
sync_profile("asset-designer")
sync_profile("seedance-prompt")
sync_profile("storyboard", keep_x2_only_dirs=X2_ONLY_STORYBOARD_DIRS)
print("\nDone!")
