"""资产 markdown 解析。

输入：hermes asset-designer profile 输出的 markdown
输出：list of (kind, name, description) — kind ∈ {character, scene, prop}

格式示例（来自旧 server.py）：
```
## 人物资产
### 人物1：林天
- 【身份/背景】...
- 【外貌特征】...
- 【服装】...

### 人物2：苏雪
...

## 场景资产
### 场景1：九幽城外
...

## 物品资产
### 物品1：玄铁剑
...
```

v0.6.16 另加 `extract_asset_names(asset_cache)`：从同一份 markdown
里只抽资产**名字列表**（人/场/物三段），对应原软件 D:\剧本分镜助手\server.py
的 `extract_asset_names()`（1253 行），原软件用这个列表注入到下游
seedance 视频 prompt agent。本软件在 UI 里"📋 复制资产列表"按钮用。
"""
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("manju.assets")

# 段落标题 → kind
_SECTION_KIND = {
    "人物资产": "character",
    "场景资产": "scene",
    "物品资产": "prop",
}

# 反向：kind → (段落标题, 条目前缀)
_SECTION_BY_KIND = {
    "character": ("人物资产", "人物"),
    "scene": ("场景资产", "场景"),
    "prop": ("物品资产", "物品"),
}

# 资产条目：`### 人物1：林天` / `### 人物1:林天` / `### 人物1 林天`
# 兼容 人物1、人物01、人物001 等编号
_ENTRY_RE = re.compile(
    r"^#{2,4}\s*(人物|场景|物品)\s*\d+[：:]\s*(.+?)\s*$",
    re.MULTILINE,
)

# v0.7.0：抽取"中文指令词"段（生图 prompt）— 跨多行，止于"负向提示词"或下一个 ## 段
# 用户的真实样例（hermes 输出）：
#   - 中文指令词：专业角色设计参考图，"陈戈"，...（多行）... character model sheet
#   - 负向提示词：
#     - 具体排除项：xxx
# 也兼容 "-中文指令词"（无空格）、"中文指令词: "（英文冒号）
_IMG_PROMPT_RE = re.compile(
    r"(?:^|\n)[\s-]*中文指令词[：:]\s*([\s\S]+?)(?=\n[\s-]*(?:负向提示词|负向词|##\s|\Z))",
    re.MULTILINE,
)


def _filter_output(output: str) -> str:
    """过滤推理/思考内容：找到第一个真实资产条目（人物1/场景1/物品1）作为起点。
    兼容旧版逻辑：找不到则尝试找最后一个 ## 人物资产 标题。
    """
    if not output:
        return ""
    # 找第一个匹配的 ### 人物1/场景1/物品1
    for kind_word in ("人物", "场景", "物品"):
        m = re.search(rf"#{2,4}\s*{kind_word}1[：:]", output)
        if m:
            # 从这个位置向前找最近的 ## 标题
            start = m.start()
            prev = output.rfind("\n## ", 0, start)
            if prev >= 0:
                return output[prev + 1 :]
            return output[start:]
    # 降级：最后一个 ## 人物资产
    last = output.rfind("## 人物资产")
    if last >= 0:
        return output[last:]
    return output


def parse_asset_markdown(output: str) -> List[Tuple[str, str, str, str]]:
    """把 hermes 输出的 markdown 解析成资产列表。

    v0.7.0 改为 4-tuple：[(kind, name, description, image_prompt), ...]
    - kind:   'character' / 'scene' / 'prop'
    - name:   资产名（如 '林天'）
    - description: 资产描述文本（多行拼接）
    - image_prompt: v0.7.0 新增 — 资产里"中文指令词"段（生图 prompt），
                   解析失败则为空字符串
    """
    if not output:
        return []
    text = _filter_output(output)
    if not text.strip():
        return []

    # 先按 ## section 切分
    # sections: { '人物资产': '人物1：xxx\n- ...\n\n人物2：yyy\n...', ... }
    # v1.1.4:段标题正则兼容新版 hermes 输出格式
    #   - 旧:`## 人物资产` / `## 场景资产` / `## 物品资产`
    #   - 新(带中文序号):`# 一、人物资产` / `## 一、人物资产` / `# 二、场景资产` / `# 三、物品资产`
    #   - 新(带数字序号):`## 1. 人物资产` / `## 2. 场景资产`
    # 兼容 # ~ #### 任意级标题 + 可选 序号/顿号/句号/空格 + 三种资产段名
    _SECTION_RE = re.compile(
        r"^#{1,4}\s*"
        r"(?:(?:[\d]+|[一二三四五六七八九十]+)\s*[、.\s]\s*)?"
        r"(人物资产|场景资产|物品资产)\s*$"
    )
    sections: Dict[str, str] = {}
    current_key: Optional[str] = None
    current_buf: List[str] = []
    for line in text.splitlines():
        m = _SECTION_RE.match(line.strip())
        if m:
            if current_key is not None:
                sections[current_key] = "\n".join(current_buf).strip()
            current_key = m.group(1)
            current_buf = []
        else:
            if current_key is not None:
                current_buf.append(line)
    if current_key is not None:
        sections[current_key] = "\n".join(current_buf).strip()

    # 每个 section 内：按 ### 条目切
    # v1.1.4:空 desc 也保留(之前 `if desc:` 会把"只有名字没描述"的资产
    # 漏掉,新版 hermes 输出 `### 物品4：xxx` 后直接换下一条,desc 空就被丢)
    result: List[Tuple[str, str, str, str]] = []
    for section_title, content in sections.items():
        kind = _SECTION_KIND.get(section_title)
        if not kind:
            continue
        if not content:
            continue
        # 切分 ### 人物N：xxx 条目
        current_name: Optional[str] = None
        current_lines: List[str] = []
        for line in content.splitlines():
            m = re.match(r"^#{2,4}\s*(人物|场景|物品)\s*\d+[：:]\s*(.+?)\s*$", line)
            if m:
                if current_name is not None:
                    desc = "\n".join(current_lines).strip()
                    img_prompt = _extract_image_prompt(desc) if desc else ""
                    result.append((kind, current_name, desc, img_prompt))
                current_name = m.group(2).strip()
                current_lines = []
            else:
                if current_name is not None:
                    current_lines.append(line)
        if current_name is not None:
            desc = "\n".join(current_lines).strip()
            img_prompt = _extract_image_prompt(desc) if desc else ""
            result.append((kind, current_name, desc, img_prompt))
    log.info("parsed %d assets from markdown (len=%d)", len(result), len(text))
    return result


def _extract_image_prompt(desc: str) -> str:
    """v0.7.0：从资产描述里抽取"中文指令词"段作为生图 prompt。

    原软件 hermes 输出格式（用户实测）：
    ```
    - 中文指令词：专业角色设计参考图，...（多行）... character model sheet
    - 负向提示词：
      - 具体排除项：xxx
    ```

    返回"中文指令词："后到下一个 "^- 负向提示词" / "## " / 段尾之间的内容。
    """
    if not desc:
        return ""
    m = _IMG_PROMPT_RE.search(desc)
    if m:
        return m.group(1).strip()
    return ""


# ---------- v0.6.16 资产名列表（给下游 prompt agent 用）----------

# 名字段提取正则：### 人物1：xxx
# name 长度阈值：60 字符（与原软件 D:\剧本分镜助手\server.py:1270 一致，
# 过滤掉 LLM 偶尔把整段描述写进名字栏的异常 case）
# 不能用 .format()（{2,4} 会被当成替换字段），改用 f-string 拼
def _name_re_for(prefix: str) -> re.Pattern:
    return re.compile(rf"^#{{2,4}}\s*{prefix}\s*\d+[：:]\s*(.+)$", re.MULTILINE)


_NAME_NAME_MAX = 60


def extract_asset_names(asset_cache: str) -> Dict[str, List[str]]:
    """从资产缓存 markdown 抽取**纯名字列表**（不含描述），按 人物/场景/物品 三段。

    复刻自原软件 D:\剧本分镜助手\server.py:1253 `extract_asset_names()`。
    原软件用这个列表注入到下游 seedance 视频 prompt agent（line 1307-1310）。
    本软件在 UI "📋 复制资产列表" 按钮用，输出形如：

        人物资产：陈戈、师尊、王曦
        场景资产：东荒野林、剑阁
        物品资产：火折子、玄铁剑

    Returns:
        {
            "人物资产": ["陈戈", "师尊", ...],
            "场景资产": [...],
            "物品资产": [...],
        }
        —— 顺序与 asset_cache 中 `### 人物N：` 出现顺序一致。
        某段不存在时返回空列表而不是缺失 key。
    """
    out: Dict[str, List[str]] = {"人物资产": [], "场景资产": [], "物品资产": []}
    if not asset_cache:
        return out

    for section_key, prefix in (
        ("人物资产", "人物"),
        ("场景资产", "场景"),
        ("物品资产", "物品"),
    ):
        idx = asset_cache.find(f"## {section_key}")
        if idx < 0:
            continue
        # 切到下一个 ## 段
        start = idx + len(f"## {section_key}")
        nxt = re.search(r"\n##\s", asset_cache[start:])
        section = asset_cache[start : start + nxt.start()] if nxt else asset_cache[start:]

        re_name = _name_re_for(prefix)
        names: List[str] = []
        for m in re_name.finditer(section):
            n = m.group(1).strip()
            # 名字里不允许换行/引号（防 LLM 把整段塞进名字栏）
            n_one_line = n.splitlines()[0].strip().strip('"\'`')
            if n_one_line and len(n_one_line) < _NAME_NAME_MAX:
                names.append(n_one_line)
        out[section_key] = names
    return out


def format_asset_list_text(asset_cache: str) -> str:
    """从 asset_cache 抽取资产名列表，拼成单行多段的纯文本（用于复制 / 写盘 / 注入下游）。

    输出格式（与原软件 D:\剧本分镜助手\server.py:1272 完全一致）：

        人物资产：陈戈、师尊、王曦
        场景资产：东荒野林、剑阁
        物品资产：火折子、玄铁剑

    空段省略（避免输出 "人物资产：" 这种空尾巴）。
    """
    d = extract_asset_names(asset_cache)
    lines: List[str] = []
    for section_key in ("人物资产", "场景资产", "物品资产"):
        items = d.get(section_key) or []
        if not items:
            continue
        lines.append(f"{section_key}：{'、'.join(items)}")
    return "\n".join(lines)


def list_file_path(outputs_dir, project_id) -> Path:
    """资产列表写盘文件路径：outputs/<project_id>_asset_list.txt。"""
    return Path(outputs_dir) / f"{project_id}_asset_list.txt"
