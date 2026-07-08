"""CRUD 封装。"""
import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional

from .models import Asset, Episode, Project


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Database:
    def __init__(self, con: sqlite3.Connection):
        self.con = con

    # ---------------- projects ----------------
    def list_projects(self) -> List[Project]:
        cur = self.con.cursor()
        cur.execute("""
            SELECT p.*, COUNT(e.id) AS episode_count
            FROM projects p
            LEFT JOIN episodes e ON e.project_id = p.id
            GROUP BY p.id
            ORDER BY COALESCE(p.updated_at, p.created_at) DESC
        """)
        return [self._row_to_project(r) for r in cur.fetchall()]

    def get_project(self, project_id: str) -> Optional[Project]:
        cur = self.con.cursor()
        cur.execute("SELECT * FROM projects WHERE id=?", (project_id,))
        r = cur.fetchone()
        if not r:
            return None
        cur.execute(
            "SELECT COUNT(*) FROM episodes WHERE project_id=?", (project_id,)
        )
        cnt = cur.fetchone()[0]
        return self._row_to_project(r, episode_count=cnt)

    def create_project(
        self,
        name: str,
        description: str = "",
        style_id: str = "",
        render_type: str = "",
    ) -> Project:
        """v0.6.18：加 style_id / render_type 参数（项目级视觉风格 + 渲染类型）。

        复刻自原软件 D:\\剧本分镜助手\\server.py POST /api/projects
        接受 style_id / render_type。
        """
        if not name.strip():
            raise ValueError("项目名不能为空")
        pid = _new_id("p")
        now = _now()
        self.con.execute(
            "INSERT INTO projects(id, name, description, style_id, render_type, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (pid, name.strip(), description, style_id, render_type, now, now),
        )
        self.con.commit()
        return self.get_project(pid)

    def update_project(
        self,
        project_id: str,
        name: str = None,
        description: str = None,
        style_id: str = None,
        render_type: str = None,
    ) -> None:
        """v0.6.18：加 style_id / render_type 修改入口（PATCH 风格，只更指定字段）。"""
        fields, vals = [], []
        if name is not None:
            fields.append("name=?")
            vals.append(name.strip())
        if description is not None:
            fields.append("description=?")
            vals.append(description)
        if style_id is not None:
            fields.append("style_id=?")
            vals.append(style_id)
        if render_type is not None:
            fields.append("render_type=?")
            vals.append(render_type)
        if not fields:
            return
        fields.append("updated_at=?")
        vals.append(_now())
        vals.append(project_id)
        self.con.execute(
            f"UPDATE projects SET {','.join(fields)} WHERE id=?", vals
        )
        self.con.commit()

    def delete_project(self, project_id: str) -> None:
        self.con.execute("DELETE FROM projects WHERE id=?", (project_id,))
        self.con.commit()

    # ---------------- episodes ----------------
    def list_episodes(self, project_id: str) -> List[Episode]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM episodes WHERE project_id=? ORDER BY episode_num",
            (project_id,),
        )
        return [self._row_to_episode(r) for r in cur.fetchall()]

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        cur = self.con.cursor()
        cur.execute("SELECT * FROM episodes WHERE id=?", (episode_id,))
        r = cur.fetchone()
        return self._row_to_episode(r) if r else None

    def create_episode(
        self,
        project_id: str,
        title: str,
        script: str = "",
        episode_num: Optional[int] = None,
    ) -> Episode:
        """v0.6.28：去掉 render_type 参数，渲染类型统一走项目级。

        之前 v0.6.18 加的剧集级 render_type 实际是冗余的（项目级已经定好）。
        剧集表 render_type 列保留（schema 兼容），但永远 sync 自 project.render_type。
        """
        if not title.strip():
            raise ValueError("剧集标题不能为空")
        eid = _new_id("e")
        if episode_num is None:
            cur = self.con.cursor()
            cur.execute(
                "SELECT COALESCE(MAX(episode_num),0)+1 FROM episodes WHERE project_id=?",
                (project_id,),
            )
            episode_num = cur.fetchone()[0]
        now = _now()
        # v0.6.28：render_type 直接从项目级读，写入剧集行（保持同步，便于查询/统计）
        proj = self.get_project(project_id)
        render_type = proj.render_type if proj else ""
        self.con.execute(
            "INSERT INTO episodes(id, project_id, episode_num, title, script, render_type, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (eid, project_id, episode_num, title.strip(), script, render_type, now, now),
        )
        self.con.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (now, project_id)
        )
        self.con.commit()
        return self.get_episode(eid)

    def update_episode(self, episode_id: str, **kwargs) -> None:
        # v0.6.28：移除 render_type（统一走项目级，不允许剧集级 override）
        # 保留字段以兼容老数据，但忽略用户传入的 render_type kwarg
        allowed = {
            "title", "script", "storyboard", "status", "prompt", "prompt_status",
            "mode", "video_segments", "asset_status",
        }
        # 静默丢弃 render_type（不让它继续成为 API 一部分）
        kwargs.pop("render_type", None)
        fields, vals = [], []
        for k, v in kwargs.items():
            if k in allowed:
                fields.append(f"{k}=?")
                vals.append(v)
        if not fields:
            return
        fields.append("updated_at=?")
        vals.append(_now())
        vals.append(episode_id)
        self.con.execute(
            f"UPDATE episodes SET {','.join(fields)} WHERE id=?", vals
        )
        ep = self.get_episode(episode_id)
        if ep:
            self.con.execute(
                "UPDATE projects SET updated_at=? WHERE id=?",
                (_now(), ep.project_id),
            )
        self.con.commit()

    def delete_episode(self, episode_id: str) -> None:
        ep = self.get_episode(episode_id)
        self.con.execute("DELETE FROM episodes WHERE id=?", (episode_id,))
        if ep:
            self.con.execute(
                "UPDATE projects SET updated_at=? WHERE id=?",
                (_now(), ep.project_id),
            )
        self.con.commit()

    # ---------------- v0.6.20 音频选段（audio_selections） ----------------
    def set_audio_selection(self, project_id: str, asset_name: str, audio_file: str) -> None:
        """v0.6.20：写音频选段（DELETE + INSERT）。

        复刻自原软件 D:\\剧本分镜助手\\server.py:1717-1732 `select-audio`。
        一个资产同时只能选一个音频。
        """
        import uuid
        self.con.execute(
            "DELETE FROM audio_selections WHERE project=? AND asset=?",
            (project_id, asset_name),
        )
        self.con.execute(
            "INSERT INTO audio_selections(id, project, asset, audio_file)"
            " VALUES (?,?,?,?)",
            (uuid.uuid4().hex, project_id, asset_name, audio_file),
        )
        self.con.commit()

    def get_audio_selection(self, project_id: str, asset_name: str) -> str:
        """v0.6.20：查某资产选定的音频文件（路径）。无则返回空字符串。"""
        cur = self.con.cursor()
        cur.execute(
            "SELECT audio_file FROM audio_selections WHERE project=? AND asset=?",
            (project_id, asset_name),
        )
        row = cur.fetchone()
        return row["audio_file"] if row else ""

    def list_audio_selections(self, project_id: str) -> dict:
        """v0.6.20：列项目下所有资产的音频选段。

        Returns: {asset_name: audio_file} 字典。
        """
        cur = self.con.cursor()
        cur.execute(
            "SELECT asset, audio_file FROM audio_selections WHERE project=?",
            (project_id,),
        )
        return {r["asset"]: r["audio_file"] for r in cur.fetchall()}

    def clear_audio_selection(self, project_id: str, asset_name: str) -> None:
        """v0.6.20：清某资产的音频选段。

        复刻自原软件 server.py:1703-1714 `clear-audio`。
        """
        self.con.execute(
            "DELETE FROM audio_selections WHERE project=? AND asset=?",
            (project_id, asset_name),
        )
        self.con.commit()

    # ---------------- assets ----------------
    def list_assets(self, project_id: str) -> List[Asset]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM assets WHERE project_id=? ORDER BY kind, name",
            (project_id,),
        )
        return [self._row_to_asset(r) for r in cur.fetchall()]

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        cur = self.con.cursor()
        cur.execute("SELECT * FROM assets WHERE id=?", (asset_id,))
        r = cur.fetchone()
        return self._row_to_asset(r) if r else None

    def get_asset_by_name(
        self, project_id: str, kind: str, name: str
    ) -> Optional[Asset]:
        cur = self.con.cursor()
        cur.execute(
            "SELECT * FROM assets WHERE project_id=? AND kind=? AND name=?",
            (project_id, kind, name),
        )
        r = cur.fetchone()
        return self._row_to_asset(r) if r else None

    def upsert_asset(
        self,
        project_id: str,
        name: str,
        kind: str,
        description: str = "",
        image_prompt: str = "",
    ) -> Asset:
        """有则更新描述 + 中文指令词，无则插入。返回 Asset（含 id / created_at）。

        v0.7.0：新增 `image_prompt` 入参 — 资产条目里的"中文指令词"段。
        - 旧调用（不带 image_prompt）行为不变
        - 新增：已有资产时，若 image_prompt 非空且与现有值不同，UPDATE 进库
        """
        existing = self.get_asset_by_name(project_id, kind, name)
        now = _now()
        if existing:
            if description and description != existing.description:
                self.con.execute(
                    "UPDATE assets SET description=?, updated_at=? WHERE id=?",
                    (description, now, existing.id),
                )
                self.con.commit()
            # v0.7.0：image_prompt 非空且与现有不同 → UPDATE
            if image_prompt and image_prompt != existing.image_prompt:
                self.con.execute(
                    "UPDATE assets SET image_prompt=?, updated_at=? WHERE id=?",
                    (image_prompt, now, existing.id),
                )
                self.con.commit()
            return self.get_asset(existing.id)
        aid = _new_id("a")
        self.con.execute(
            "INSERT INTO assets(id, project_id, name, kind, description,"
            " image_prompt, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (aid, project_id, name, kind, description, image_prompt, now, now),
        )
        self.con.commit()
        # 更新项目的 updated_at
        self.con.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (now, project_id)
        )
        self.con.commit()
        return self.get_asset(aid)

    def delete_assets(self, project_id: str) -> int:
        """删除项目下所有资产（用于重新提取前清理）。返回删除条数。"""
        cur = self.con.cursor()
        cur.execute("DELETE FROM assets WHERE project_id=?", (project_id,))
        self.con.commit()
        return cur.rowcount

    def update_asset_image(
        self,
        asset_id: str,
        image_path: str,
        image_status: str,
    ) -> None:
        """v0.7.7 重打 20：API 层面禁止写 image_prompt。

        之前 SQL 是 `SET image_prompt=?`，即使 caller 不传参数（默认 ""），
        也会把 db 里 user 精心编辑的 1294 字 image_prompt 覆盖成空字符串！
        project memory 硬约束："image_prompt 只有 2 个权威写源（资产提取 upsert_asset
        + user 编辑 update_asset_prompt），生图是只读消费"。
        修法：移除 image_prompt 参数，SQL 也不动这列，从 API 层面强制。
        老的 caller 传 image_prompt="(用户上传)" / "(从历史图选择)" 这种 marker 字符串
        属于用 image_prompt 当"图片来源"用——也删了，那本来就不该塞进这列。
        要标记图片来源应该新加 image_source 字段（v0.7.8 再做）。
        """
        now = _now()
        self.con.execute(
            "UPDATE assets SET image_path=?, image_status=?,"
            " image_updated=?, updated_at=? WHERE id=?",
            (image_path, image_status, now, now, asset_id),
        )
        self.con.commit()

    def update_asset_prompt(self, asset_id: str, image_prompt: str) -> None:
        """v0.6.26：只更新资产的 image_prompt（不动图、状态、updated_at）。

        用于资产卡片上的行内 prompt 编辑器：用户改完提示词后即时存盘。
        复刻自原软件 templates/index.html:1218-1229 `savePromptEdit(idx)`
        （old 版只存 localStorage；manju 改成直接写 db，跨刷新保留）。
        """
        self.con.execute(
            "UPDATE assets SET image_prompt=? WHERE id=?",
            (image_prompt, asset_id),
        )
        self.con.commit()

    def update_asset_status(self, asset_id: str, image_status: str) -> None:
        """v0.6.26：只更新 image_status（不动 image_path / prompt / image_updated）。

        用于批量生图里：单个 dreamina 失败时只标 failed，不要求 caller 知道 image_path。
        复刻原软件 server.py:931 `r.update_status(asset.id, "failed")`。
        """
        self.con.execute(
            "UPDATE assets SET image_status=? WHERE id=?",
            (image_status, asset_id),
        )
        self.con.commit()

    # ---------------- v0.7.8 参考图（图生图）----------------

    def get_asset_ref_images(self, asset_id: str) -> List[str]:
        """v0.7.8：读单个资产的参考图列表（base64 data URL 数组）。

        列不存在（老 db 没升 v3）→ 幂等返回空 list。
        """
        cur = self.con.cursor()
        cur.execute("PRAGMA table_info(assets)")
        cols = {row[1] for row in cur.fetchall()}
        if "ref_images" not in cols:
            return []
        cur.execute("SELECT ref_images FROM assets WHERE id=?", (asset_id,))
        r = cur.fetchone()
        if not r or not r[0]:
            return []
        try:
            data = json.loads(r[0])
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def set_asset_ref_images(self, asset_id: str, ref_images: List[str]) -> None:
        """v0.7.8：覆盖写资产的参考图列表（base64 data URL 数组，JSON 存 db）。

        列不存在 → 幂等 ALTER TABLE 加列再写。最多 16 张(调用方负责截断)。
        """
        now = _now()
        cur = self.con.cursor()
        cur.execute("PRAGMA table_info(assets)")
        cols = {row[1] for row in cur.fetchall()}
        if "ref_images" not in cols:
            cur.execute(
                "ALTER TABLE assets ADD COLUMN ref_images TEXT NOT NULL DEFAULT '[]'"
            )
        cur.execute(
            "UPDATE assets SET ref_images=?, updated_at=? WHERE id=?",
            (json.dumps(ref_images or [], ensure_ascii=False), now, asset_id),
        )
        self.con.commit()

    # ---------------- row mappers ----------------
    def _row_to_project(self, r, episode_count: int = 0) -> Project:
        keys = set(r.keys())
        return Project(
            id=r["id"],
            name=r["name"],
            description=r["description"],
            style_id=r["style_id"],
            render_type=r["render_type"],
            created_at=r["created_at"],
            updated_at=r["updated_at"] if "updated_at" in keys else None,
            episode_count=(
                r["episode_count"] if "episode_count" in keys else episode_count
            ),
        )

    def _row_to_episode(self, r) -> Episode:
        keys = set(r.keys())
        return Episode(
            id=r["id"],
            project_id=r["project_id"],
            episode_num=r["episode_num"],
            title=r["title"],
            script=r["script"],
            storyboard=r["storyboard"],
            status=r["status"],
            prompt=r["prompt"] if "prompt" in keys else "",
            prompt_status=r["prompt_status"],
            video_segments=(
                r["video_segments"] if "video_segments" in keys else ""
            ),
            asset_status=r["asset_status"],
            # v0.6.18：剧集级 render_type（与 schema 字段对齐）
            render_type=r["render_type"] if "render_type" in keys else "",
            created_at=r["created_at"],
            updated_at=r["updated_at"] if "updated_at" in keys else None,
            mode=r["mode"],
        )

    def _row_to_asset(self, r) -> Asset:
        keys = set(r.keys())
        # v0.7.8：ref_images 字段 JSON 解析（base64 data URL 列表）
        # 老 db 没这列时 keys 里没有 ref_images,返回空 list
        ref_images: List[str] = []
        if "ref_images" in keys and r["ref_images"]:
            try:
                parsed = json.loads(r["ref_images"])
                if isinstance(parsed, list):
                    ref_images = [x for x in parsed if isinstance(x, str)]
            except Exception:
                ref_images = []
        return Asset(
            id=r["id"],
            project_id=r["project_id"],
            name=r["name"],
            kind=r["kind"],
            description=r["description"] if "description" in keys else "",
            image_path=r["image_path"] if "image_path" in keys else "",
            image_status=r["image_status"] if "image_status" in keys else "pending",
            image_prompt=r["image_prompt"] if "image_prompt" in keys else "",
            image_updated=r["image_updated"] if "image_updated" in keys else None,
            created_at=r["created_at"],
            updated_at=r["updated_at"] if "updated_at" in keys else None,
            ref_images=ref_images,
        )
