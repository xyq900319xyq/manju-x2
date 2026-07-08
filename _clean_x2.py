"""漫剧助手X-2 用户版 hermes profile 脱敏 + dev 残留清理脚本。

执行两步:
1. 清空 source/resources/hermes/profiles/*/config.yaml + auth.json 里 dev 的明文 API key
   (sk- 前缀 + ark- 前缀 + sk-c3D 等其他典型 pattern)。
2. 删掉 dev 调试 / 状态残留:
   - state.db, state.db-shm, state.db-wal (SQLite session 状态)
   - *.bak, *.bak*, *.bak_diag, *.bak_real, *.corrupt.*.bak
   - config.yaml.dev.bak (脚本前一轮备份)
   - models_dev_cache.json (dev 缓存)
   - processes.json (dev 运行时数据)
   - memories/MEMORY.md, memories/USER.md (user 数据!)
   - sessions/request_dump_*.json (33 个 dev session dump)
   - bin/ (dev tooling)
   - auth.lock (runtime lock)
   - .skills_prompt_snapshot.json, .update_check (dev 缓存)
   - a/, s/, v/ 三个 first-letter alias profile (老 shortcut,不需要)
   - skills/ 子目录(.bundled_manifest, .usage.json, .usage.json.lock, .curator_state,
     .hub/lock.json, .archive/ 残留)
"""
import os
import re
from pathlib import Path

PROFILES = Path(r'D:\漫剧助手\manju-x2\source\resources\hermes\profiles')

# 多个 API key pattern (sk- / ark- / 16-byte hex-with-dash / 32+ 字符 base62 等等)
KEY_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9_\-\.]{5,}'),         # sk-c3D...TKoE(可能被截断到 10+ 字符)
    re.compile(r'ark-[A-Za-z0-9_\-]{10,}'),         # ark-57c6101a-...-04793
    re.compile(r'AKID[A-Za-z0-9]{16,}'),             # AWS
    re.compile(r'AIza[A-Za-z0-9_\-]{30,}'),          # Google API key
    re.compile(r'ghp_[A-Za-z0-9]{30,}'),             # GitHub PAT
    re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}'),       # Anthropic
    re.compile(r'sk-or-[A-Za-z0-9_\-]{20,}'),        # OpenRouter
    re.compile(r'xai-[A-Za-z0-9]{20,}'),             # xAI
]

# 语义化:任何 `api_key:` / `apikey:` / `token:` 后面跟非空值,都清空
SEMANTIC_APIKEY = re.compile(
    r'^(\s*-?\s*(?:api_?key|token|access_token|api_token)\s*:\s*)(["\']?)([^"\'#\s][^"\'#]*?)\2(\s*)(#.*)?$',
    re.MULTILINE
)

# 单 profile 目录下需要删除的文件 / 目录
FILES_TO_DELETE = [
    'state.db', 'state.db-shm', 'state.db-wal',
    'auth.lock',
    'config.yaml.dev.bak',
    'models_dev_cache.json',
    'processes.json',
    '.skills_prompt_snapshot.json',
    '.update_check',
    '.skills_prompt_snapshot.json',
    # auth.json.bak 留一个 backup trace 也删(没价值)
    'auth.json.bak', 'auth.json.bak2', 'auth.json.bak7',
    # config.yaml.bak 系列全删
    'config.yaml.bak', 'config.yaml.bak2', 'config.yaml.bak3', 'config.yaml.bak4',
    'config.yaml.bak5', 'config.yaml.bak6', 'config.yaml.bak7',
    'config.yaml.bak_diag', 'config.yaml.bak_real',
    'config.yaml.corrupt.20260702-160027.bak',
]

DIRS_TO_DELETE = [
    'memories',           # storyboard profile 下的 user/MEMORY 数据
    'sessions',           # storyboard profile 下的 33 个 request_dump
    'bin',                # storyboard profile 下的 tirith dev tooling
    'cache',              # 所有 profile 下的 openrouter_model_metadata cache
    'logs',               # 所有 profile 下的 agent.log / errors.log
]

# profile 级别 alias: a/ s/ v/ 是 dev 时期的 first-letter shortcut,用户版用不到
ALIAS_PROFILES = ['a', 's', 'v']

# skills/ 下面要删的 dev 缓存
SKILL_GLOBS_TO_DELETE = [
    '**/.bundled_manifest',
    '**/.usage.json',
    '**/.usage.json.bak',
    '**/.usage.json.lock',
    '**/.curator_state',
    '**/.hub/lock.json',
    '**/.archive/**',
]


def clean_yaml(p: Path) -> tuple[int, list[str]]:
    """清空 p 里所有匹配 KEY_PATTERNS 或 SEMANTIC_APIKEY 的明文 key。
    返回 (替换数, 替换后的 key snippet list)。
    """
    txt = p.read_text(encoding='utf-8')
    new = txt
    found: list[str] = []

    # 1) 先按 pattern 扫(sk-/ark- 等典型 prefix)
    for pat in KEY_PATTERNS:
        for m in pat.finditer(new):
            snippet = m.group()[:24] + ('...' if len(m.group()) > 24 else '')
            found.append(snippet)
        new = pat.sub('""', new)

    # 2) 再按语义扫(任何非空 api_key/token/access_token/api_token)
    def _semantic_repl(m: re.Match) -> str:
        prefix, quote, value, trailing, comment = m.groups()
        snippet = value[:24] + ('...' if len(value) > 24 else '')
        found.append(snippet)
        return f'{prefix}""{trailing}{comment or ""}'

    new = SEMANTIC_APIKEY.sub(_semantic_repl, new)

    if new == txt:
        return 0, []
    # 不再单独写 .dev.bak 了(那些也是 dev 残留,会被 FILES_TO_DELETE 删)
    p.write_text(new, encoding='utf-8')
    return len(found), found


def clean_auth_json(p: Path) -> int:
    """auth.json 里 credential_pool 应该是空,且不应该有 updated_at 时间戳。"""
    import json
    txt = p.read_text(encoding='utf-8')
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        return 0
    if d.get('providers') == {} and d.get('credential_pool') == {} and 'updated_at' in d:
        del d['updated_at']
        p.write_text(json.dumps(d, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        return 1
    return 0


def clean_one_profile(pdir: Path) -> dict:
    """对一个 profile 目录做完整脱敏 + 清理。返回统计 dict。"""
    stats = {'keys_cleared': 0, 'files_deleted': 0, 'dirs_deleted': 0, 'auth_cleaned': 0}

    if not pdir.is_dir():
        return stats

    # 1) 清 config.yaml
    for cfg in pdir.rglob('config.yaml'):
        n, snippets = clean_yaml(cfg)
        if n:
            stats['keys_cleared'] += n
            print(f'  [CLEAN] {cfg.relative_to(PROFILES.parent.parent.parent)}: {n} key(s) 清空')
            for s in snippets:
                print(f'          → {s}')

    # 2) 清 auth.json
    for auth in pdir.rglob('auth.json'):
        n = clean_auth_json(auth)
        if n:
            stats['auth_cleaned'] += 1

    # 3) 删 dev 残留文件
    for fname in FILES_TO_DELETE:
        f = pdir / fname
        if f.exists():
            f.unlink()
            stats['files_deleted'] += 1

    # 4) 删 dev 残留目录
    for dname in DIRS_TO_DELETE:
        d = pdir / dname
        if d.exists() and d.is_dir():
            import shutil
            shutil.rmtree(d)
            stats['dirs_deleted'] += 1

    # 5) 清 skills/ 下的 dev 缓存
    # 用 rglob + 显式 exist/is_dir 校验,避免 pathlib.glob `**/.archive/**`
    # 在父目录不存在时抛 FileNotFoundError(scandir fail)
    def _safe_rglob(base: Path, name: str) -> list[Path]:
        if not base.exists() or not base.is_dir():
            return []
        return [p for p in base.rglob(name) if p.exists()]

    for pattern in SKILL_GLOBS_TO_DELETE:
        if pattern.endswith('/**'):
            base_name = pattern[:-3]  # strip '/**'
            for f in _safe_rglob(pdir, base_name):
                if f.is_dir():
                    import shutil
                    shutil.rmtree(f, ignore_errors=True)
                    stats['dirs_deleted'] += 1
        else:
            base_name = pattern[3:] if pattern.startswith('**/') else pattern  # strip '**/' prefix
            for f in _safe_rglob(pdir, base_name):
                if f.is_file():
                    f.unlink()
                    stats['files_deleted'] += 1

    return stats


def main():
    print(f'PROFILES root: {PROFILES}')
    if not PROFILES.is_dir():
        print('  ! 路径不存在,退出')
        return

    total = {'keys_cleared': 0, 'files_deleted': 0, 'dirs_deleted': 0, 'auth_cleaned': 0}
    for pdir in sorted(PROFILES.iterdir()):
        # 跳过 alias profile (a/, s/, v/)
        if pdir.name in ALIAS_PROFILES:
            import shutil
            if pdir.exists():
                shutil.rmtree(pdir)
                print(f'  [DEL alias profile] {pdir.name}/')
                total['dirs_deleted'] += 1
            continue
        if not pdir.is_dir():
            continue
        print(f'\n--- profile: {pdir.name} ---')
        s = clean_one_profile(pdir)
        for k, v in s.items():
            total[k] += v
            if v:
                print(f'  [{k}] +{v}')

    print(f'\n===== 合计 =====')
    print(f'  清空明文 API key:        {total["keys_cleared"]}')
    print(f'  清空 auth.json 时间戳:   {total["auth_cleaned"]}')
    print(f'  删除 dev 残留文件:       {total["files_deleted"]}')
    print(f'  删除 dev 残留目录:       {total["dirs_deleted"]} (含 3 个 alias profile)')


if __name__ == '__main__':
    main()
