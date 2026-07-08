# 调用方式

## 命令行调用

```bash
# 单次查询（推荐前端使用）
hermes -p asset-designer chat -q "剧本内容" --quiet

# 或直接管道
echo "剧本内容" | hermes -p asset-designer chat -q "$(cat)" --quiet
```

## Python 调用

```python
import subprocess, os

env = os.environ.copy()
env["HERMES_HOME"] = os.path.expanduser("~/.hermes/profiles/asset-designer")

result = subprocess.run(
    ["/home/administrator/.local/bin/hermes", "-p", "asset-designer",
     "chat", "-q", script_content, "--quiet"],
    capture_output=True, text=True, timeout=600,
    env=env
)

# 过滤 reasoning 输出（参考 hermes-one-shot-integration skill）
combined = result.stdout + "\n" + (result.stderr or "")
sid_pos = combined.find("session_id:")
reason_pos = combined.find("┌─ Reason")
if sid_pos > 0 and reason_pos >= 0:
    output = combined[reason_pos:sid_pos]
    # 取实际内容（跳过 Reason 标题行）
    m = re.search(r'(?:^|\n)(人物资产|场景资产|物品资产)', output, re.MULTILINE)
    if m:
        output = output[m.start():].strip()
```

## Workspace 调用

在 Hermes Workspace 中选择 `asset-designer` profile，直接对话即可。粘贴剧本后 agent 会自动按 skill 规范输出。
