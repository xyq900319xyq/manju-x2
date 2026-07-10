"""左侧项目/剧集树。"""
from typing import Dict, List, Optional
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu
from PySide6.QtCore import Qt, Signal

from core.models import Project, Episode

PROJECT_ROLE = Qt.ItemDataRole.UserRole + 1
EPISODE_ROLE = Qt.ItemDataRole.UserRole + 2

_STATUS_ICON = {
    "completed": "✓",
    "processing": "⏳",
    "error": "✗",
    "pending": "·",
}


class ProjectTree(QTreeWidget):
    project_selected = Signal(object)   # str or None
    episode_selected = Signal(object)   # str or None
    context_new_episode = Signal(str)
    context_rename_project = Signal(str)
    context_delete_project = Signal(str)
    context_edit_episode = Signal(str)
    context_delete_episode = Signal(str)
    # v0.6.18 #8：📋 导出整剧集 prompts 菜单（项目右键）
    context_export_prompts = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectTree")  # v0.7.0：给 QSS 加专门的样式钩子
        self.setHeaderLabels(["项目 / 剧集"])
        self.setColumnCount(1)
        self.setMinimumWidth(280)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        self.itemSelectionChanged.connect(self._on_selection)
        self._items: Dict[str, QTreeWidgetItem] = {}

    # ---------- 公共 API ----------
    def load_projects(self, projects: List[Project]) -> None:
        self.clear()
        self._items.clear()
        for p in projects:
            self.add_project(p)

    def add_project(self, project: Project) -> QTreeWidgetItem:
        item = QTreeWidgetItem([self._project_label(project)])
        item.setData(0, PROJECT_ROLE, project.id)
        item.setToolTip(0, project.description or project.name)
        self.addTopLevelItem(item)
        self._items[project.id] = item
        # v1.1.5:返回 item,让 main_window 用 setCurrentItem 触发 selection
        # (addTopLevelItem 不会自动触发 itemSelectionChanged,user 新建项目
        # 后 _current_project 还是 None → toolbar"新建剧集"按钮是灰的)
        return item

    def update_project(self, project: Project) -> None:
        item = self._items.get(project.id)
        if not item:
            return
        item.setText(0, self._project_label(project))
        item.setToolTip(0, project.description or project.name)

    def remove_project(self, project_id: str) -> None:
        # v1.1.5【C8 修复】:takeTopLevelItem 会触发 itemSelectionChanged
        # (Qt 行为:删的就是 currentItem 时 → currentItem 变 None → signal emit)
        # → main_window._on_project_selected(None) 被调 → _current_project
        # / _current_episode 设 None + 切到空态 → 跟 _on_delete_project 自己的
        # cleanup 逻辑重复执行,可能导致 tab 被 _replace_tab 改两次,user 看到
        # UI 闪烁或切错 tab。修法:remove 前 blockSignals,remove 后
        # unblockSignals 之前,若想精确控制 selection 状态由 main_window 决定。
        item = self._items.pop(project_id, None)
        if not item:
            return
        idx = self.indexOfTopLevelItem(item)
        if idx >= 0:
            self.blockSignals(True)
            try:
                self.takeTopLevelItem(idx)
            finally:
                self.blockSignals(False)

    def set_episodes(self, project_id: str, episodes: List[Episode]) -> None:
        proj_item = self._items.get(project_id)
        if not proj_item:
            return
        # v0.7.8.49:已有剧集列表且数量一致 → 跳过重建(切回同项目不重画)
        if proj_item.childCount() == len(episodes):
            return
        # v1.1.5【C8 修复】:takeChildren 同样会触发 itemSelectionChanged
        # (如果当前选的是这个项目下的某个剧集,删 child 把 currentItem 变 None)
        # → main_window._on_episode_selected(None) early return,无害,但
        # 跟 _on_delete_episode 自己的 cleanup 逻辑有重叠,这里保险 block 一下。
        self.blockSignals(True)
        try:
            proj_item.takeChildren()
            for ep in episodes:
                self._add_episode_item(proj_item, ep)
            proj_item.setExpanded(True)
        finally:
            self.blockSignals(False)
        # 同步括号里的数字
        p = self._project_from_item_text(proj_item.text(0))
        if p is not None:
            proj_item.setText(0, self._project_label(p, len(episodes)))

    def add_episode(self, episode: Episode, project_name: str = "") -> QTreeWidgetItem:
        proj_item = self._items.get(episode.project_id)
        if not proj_item:
            # v1.1.5:返回空 item 而不是 None(类型一致)
            return QTreeWidgetItem()
        child = self._add_episode_item(proj_item, episode)
        # 更新括号数字
        txt = proj_item.text(0)
        if "(" in txt:
            base, num = txt.rsplit("(", 1)
            try:
                cnt = int(num.rstrip(")"))
                if project_name and not base.startswith(project_name):
                    base = project_name
                proj_item.setText(0, f"{base}({cnt + 1})")
            except ValueError:
                pass
        # v1.1.5:返回新建的 child item,让 main_window 用 setCurrentItem 触发
        # _on_episode_selected(原 addChild 不触发 itemSelectionChanged,user
        # 新建剧集后 _current_episode 还是 None/旧的,看不到新剧集的分镜 tab)
        return child

    def remove_episode(self, episode_id: str) -> None:
        # v1.1.5【C8 修复】:removeChild 同样会触发 itemSelectionChanged
        # (如果删的就是 currentItem → currentItem 变 None → signal emit)
        # → main_window._on_episode_selected(None) early return,无害,但
        # 跟 _on_delete_episode 自己的 cleanup 逻辑有重叠,这里保险 block。
        # 修法:整个循环用 blockSignals 包起来。
        self.blockSignals(True)
        try:
            for i in range(self.topLevelItemCount()):
                top = self.topLevelItem(i)
                for j in range(top.childCount()):
                    child = top.child(j)
                    if child.data(0, EPISODE_ROLE) == episode_id:
                        top.removeChild(child)
                        return
        finally:
            self.blockSignals(False)

    # ---------- 渲染 ----------
    def _project_label(self, p: Project, count: Optional[int] = None) -> str:
        c = count if count is not None else p.episode_count
        return f"📁 {p.name}  ({c})"

    def _project_from_item_text(self, text: str) -> Optional[Project]:
        # 仅用于更新括号数字时的占位
        if "(" in text and text.endswith(")"):
            name = text.rsplit("(", 1)[0].strip()
            for emoji in ("📁 ",):
                if name.startswith(emoji):
                    name = name[len(emoji):]
            return Project(id="", name=name)
        return None

    def _add_episode_item(self, parent: QTreeWidgetItem, ep: Episode) -> QTreeWidgetItem:
        icon = _STATUS_ICON.get(ep.status, "·")
        if ep.title:
            label = f"{icon} 第{ep.episode_num}集：{ep.title}"
        else:
            label = f"{icon} 第{ep.episode_num}集"
        child = QTreeWidgetItem([label])
        child.setData(0, EPISODE_ROLE, ep.id)
        child.setToolTip(0, f"状态: {ep.status} | 提示词: {ep.prompt_status or '-'} | 资产: {ep.asset_status or '-'}")
        parent.addChild(child)
        return child

    # ---------- 事件 ----------
    def _on_selection(self) -> None:
        item = self.currentItem()
        if not item:
            self.project_selected.emit(None)
            self.episode_selected.emit(None)
            return
        ep_id = item.data(0, EPISODE_ROLE)
        if ep_id:
            self.episode_selected.emit(ep_id)
        else:
            proj_id = item.data(0, PROJECT_ROLE)
            self.project_selected.emit(proj_id)

    def _on_context_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if not item:
            return
        menu = QMenu(self)
        ep_id = item.data(0, EPISODE_ROLE)
        proj_id = item.data(0, PROJECT_ROLE)
        if ep_id:
            menu.addAction("✏️ 编辑剧集", lambda: self.context_edit_episode.emit(ep_id))
            menu.addSeparator()
            menu.addAction("🗑️ 删除剧集", lambda: self.context_delete_episode.emit(ep_id))
        elif proj_id:
            menu.addAction("➕ 新建剧集", lambda: self.context_new_episode.emit(proj_id))
            menu.addAction("✏️ 编辑项目", lambda: self.context_rename_project.emit(proj_id))
            # v0.6.18 #8：导出整剧集 prompts
            menu.addSeparator()
            menu.addAction("📋 导出整剧集 prompts", lambda: self.context_export_prompts.emit(proj_id))
            menu.addSeparator()
            menu.addAction("🗑️ 删除项目", lambda: self.context_delete_project.emit(proj_id))
        menu.exec(self.viewport().mapToGlobal(pos))
