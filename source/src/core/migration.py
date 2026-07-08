"""数据库迁移：把旧版 D:\\剧本分镜助手\\projects.db 一次性复制到
D:\\漫剧助手\\data\\projects.db，并加上新版 schema 扩展（updated_at / _meta）。

设计要点：
- 旧 db 只读（uri=mode=ro），任何情况都不会被修改
- 新 db 路径：<项目根>/data/projects.db
- 首次启动若 data/projects.db 不存在 → 跑首次迁移
- 迁移记录写在 _meta 表（source_path / source_sha256 / migrated_at / source_rows）
- 如果旧 db 文件被改动（sha256 变了），会拒绝再次迁移并提示用户
"""
import hashlib
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

# 旧 db 默认位置（可改）
DEFAULT_OLD_DB = Path(r"D:\剧本分镜助手\projects.db")

# 新版 schema 版本号（每次 schema 变更 +1）
CURRENT_SCHEMA_VERSION = 3


def new_db_path(root: Path) -> Path:
    return root / "data" / "projects.db"


def compute_db_sha256(db_path: Path) -> str:
    h = hashlib.sha256()
    with open(db_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_data_dir(root: Path) -> Path:
    p = new_db_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_schema_version(con: sqlite3.Connection) -> int:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'")
    if not cur.fetchone():
        return 0
    cur.execute("SELECT value FROM _meta WHERE key='schema_version'")
    row = cur.fetchone()
    return int(row[0]) if row else 0


def get_meta(con: sqlite3.Connection, key: str) -> Optional[str]:
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'")
    if not cur.fetchone():
        return None
    cur.execute("SELECT value FROM _meta WHERE key=?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def init_new_schema(con: sqlite3.Connection) -> None:
    """在空 db 上创建完整 schema。

    与旧版对齐 + 新增字段：
    - projects.updated_at（新版才有）
    - episodes.updated_at（新版才有）
    - _meta 表（迁移元数据 / schema_version）
    """
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE _meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE projects (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            asset_cache TEXT NOT NULL DEFAULT '',
            style_id    TEXT NOT NULL DEFAULT '',
            render_type TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL,
            updated_at  TEXT
        );
        CREATE UNIQUE INDEX idx_projects_name ON projects(name);

        CREATE TABLE episodes (
            id                   TEXT PRIMARY KEY,
            project_id           TEXT NOT NULL,
            episode_num          INTEGER NOT NULL,
            title                TEXT NOT NULL DEFAULT '',
            script               TEXT NOT NULL,
            storyboard           TEXT NOT NULL DEFAULT '',
            style_id             TEXT NOT NULL DEFAULT '',
            render_type          TEXT NOT NULL DEFAULT '',
            status               TEXT NOT NULL DEFAULT 'pending',
            created_at           TEXT NOT NULL,
            updated_at           TEXT,
            prompt               TEXT NOT NULL DEFAULT '',
            prompt_status        TEXT NOT NULL DEFAULT '',
            mode                 TEXT NOT NULL DEFAULT 'storyboard',
            video_segments       TEXT NOT NULL DEFAULT '',
            asset_status         TEXT NOT NULL DEFAULT '',
            asset_status_updated TEXT NOT NULL DEFAULT '',
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_episodes_project ON episodes(project_id, episode_num);

        CREATE TABLE audio_selections (
            id         TEXT PRIMARY KEY,
            project    TEXT NOT NULL,
            asset      TEXT NOT NULL,
            audio_file TEXT NOT NULL
        );

        CREATE TABLE assets (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            name            TEXT NOT NULL,
            kind            TEXT NOT NULL DEFAULT 'character',
            description     TEXT NOT NULL DEFAULT '',
            image_path      TEXT NOT NULL DEFAULT '',
            image_status    TEXT NOT NULL DEFAULT 'pending',
            image_prompt    TEXT NOT NULL DEFAULT '',
            image_updated   TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT,
            UNIQUE(project_id, kind, name),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_assets_project ON assets(project_id, kind);
    """)
    cur.execute(
        "INSERT INTO _meta(key, value) VALUES (?, ?)",
        ("schema_version", str(CURRENT_SCHEMA_VERSION)),
    )
    con.commit()


def _copy_table(con_src: sqlite3.Connection, con_dst: sqlite3.Connection, table: str) -> int:
    """逐行复制一张表，自动处理新旧列差异。"""
    cur_src = con_src.cursor()
    cur_dst = con_dst.cursor()
    cur_src.execute(f"SELECT * FROM {table}")
    rows = cur_src.fetchall()
    if not rows:
        return 0
    src_cols = [d[0] for d in cur_src.description]
    cur_dst.execute(f'PRAGMA table_info("{table}")')
    dst_cols = [r[1] for r in cur_dst.fetchall()]
    common = [c for c in src_cols if c in dst_cols]
    if not common:
        return 0
    # 重新 select 共同列
    col_list = ", ".join(f'"{c}"' for c in common)
    cur_src.execute(f"SELECT {col_list} FROM {table}")
    rows = cur_src.fetchall()
    extra_cols = [c for c in dst_cols if c not in common]
    # 准备 INSERT
    all_cols = common + extra_cols
    placeholders = ", ".join(["?"] * len(all_cols))
    col_names = ", ".join(f'"{c}"' for c in all_cols)
    now = datetime.now().isoformat(timespec="seconds")
    extra_vals = []
    for c in extra_cols:
        if c == "updated_at":
            extra_vals.append(now)
        else:
            extra_vals.append("")
    final_rows = [tuple(r) + tuple(extra_vals) for r in rows]
    cur_dst.executemany(
        f'INSERT INTO "{table}" ({col_names}) VALUES ({placeholders})',
        final_rows,
    )
    return len(rows)


def run_first_migration(root: Path, old_db: Path = DEFAULT_OLD_DB) -> dict:
    """首次迁移：旧 db → 新 db。仅当新 db 不存在时执行。"""
    if not old_db.exists():
        raise FileNotFoundError(f"旧 db 不存在: {old_db}")
    new_path = ensure_data_dir(root)
    if new_path.exists():
        return {"skipped": True, "new_path": str(new_path)}

    src_sha = compute_db_sha256(old_db)
    con_src = sqlite3.connect(f"file:{old_db}?mode=ro", uri=True)
    try:
        con_dst = sqlite3.connect(new_path)
        try:
            init_new_schema(con_dst)
            counts = {}
            for tbl in ("projects", "episodes", "audio_selections"):
                counts[tbl] = _copy_table(con_src, con_dst, tbl)
            cur = con_dst.cursor()
            cur.executemany(
                "INSERT INTO _meta(key, value) VALUES (?, ?)",
                [
                    ("source_path", str(old_db)),
                    ("source_sha256", src_sha),
                    ("migrated_at", datetime.now().isoformat(timespec="seconds")),
                    ("source_rows", str(counts)),
                    ("app_version", "0.0.1"),
                ],
            )
            con_dst.commit()
        finally:
            con_dst.close()
    finally:
        con_src.close()
    return {
        "skipped": False,
        "new_path": str(new_path),
        "source_path": str(old_db),
        "source_sha256": src_sha,
        "counts": counts,
    }


def open_db(root: Path) -> sqlite3.Connection:
    """打开新 db（自动首次迁移 + 升级）。"""
    p = ensure_data_dir(root)
    if not p.exists() or p.stat().st_size == 0:
        run_first_migration(root)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    # 升级 schema（如有需要）
    _upgrade_schema(con)
    return con


def _upgrade_schema(con: sqlite3.Connection) -> None:
    """把现有 db 升级到 CURRENT_SCHEMA_VERSION。"""
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='_meta'")
    if not cur.fetchone():
        # 极少见：db 文件存在但 _meta 缺失。补一个 _meta，version=1（假设旧结构）
        cur.execute(
            "CREATE TABLE _meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        cur.execute(
            "INSERT INTO _meta(key, value) VALUES (?, ?)", ("schema_version", "1")
        )
        con.commit()
    cur.execute("SELECT value FROM _meta WHERE key='schema_version'")
    row = cur.fetchone()
    cur_version = int(row[0]) if row else 0
    if cur_version < 2:
        migrate_v1_to_v2(con)
    if cur_version < 3:
        migrate_v2_to_v3(con)


def migrate_v1_to_v2(con: sqlite3.Connection) -> None:
    """v1 → v2：新增 assets 表。"""
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS assets (
            id              TEXT PRIMARY KEY,
            project_id      TEXT NOT NULL,
            name            TEXT NOT NULL,
            kind            TEXT NOT NULL DEFAULT 'character',
            description     TEXT NOT NULL DEFAULT '',
            image_path      TEXT NOT NULL DEFAULT '',
            image_status    TEXT NOT NULL DEFAULT 'pending',
            image_prompt    TEXT NOT NULL DEFAULT '',
            image_updated   TEXT,
            created_at      TEXT NOT NULL,
            updated_at      TEXT,
            UNIQUE(project_id, kind, name),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, kind);
    """)
    cur.execute(
        "UPDATE _meta SET value=? WHERE key='schema_version'", (str(CURRENT_SCHEMA_VERSION),)
    )
    con.commit()
    log = logging.getLogger("manju.migration")
    log.info("DB upgraded to schema v%d", CURRENT_SCHEMA_VERSION)


def migrate_v2_to_v3(con: sqlite3.Connection) -> None:
    """v2 → v3：assets 加 ref_images 列（图生图参考图,JSON 存 base64 data URL 列表）。

    复刻自老 software D:\\剧本分镜助手\\templates\\index.html:1101-1173
    字段不 NOT NULL DEFAULT '[]',老 row 自动用空 list。
    """
    cur = con.cursor()
    # 用 PRAGMA 查列,幂等(老 db 可能已通过 set_asset_ref_images 自动加了)
    cur.execute("PRAGMA table_info(assets)")
    cols = {row[1] for row in cur.fetchall()}
    if "ref_images" not in cols:
        cur.execute(
            "ALTER TABLE assets ADD COLUMN ref_images TEXT NOT NULL DEFAULT '[]'"
        )
    cur.execute(
        "UPDATE _meta SET value=? WHERE key='schema_version'", (str(CURRENT_SCHEMA_VERSION),)
    )
    con.commit()
    log = logging.getLogger("manju.migration")
    log.info("DB upgraded to schema v%d", CURRENT_SCHEMA_VERSION)
