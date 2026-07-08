# Hermes Workspace Deployment

Hermes Workspace (https://github.com/outsourc-e/hermes-workspace) 是 Hermes Agent 的 Web 前端界面，基于 Vite + React + TanStack Start 构建。通过 HTTP API 与 Hermes Agent Gateway 通信。

## 快速部署

```bash
# 1. 克隆仓库
git clone https://github.com/outsourc-e/hermes-workspace.git
cd hermes-workspace

# 2. 安装依赖
pnpm install

# 3. 配置环境变量（见下方）
nano .env

# 4. 启动开发服务器
pnpm run start:dev
# 或生产构建
pnpm build && pnpm start
```

访问 http://localhost:3000

## 环境变量配置

创建 `.env` 文件（**关键**：变量名必须与 vite.config.ts 匹配）：

```bash
# Hermes Agent API 地址
CLAUDE_API_URL=http://127.0.0.1:8642

# Hermes Agent 源码路径（必须指向包含 gateway/run.py 的目录）
HERMES_AGENT_PATH=/home/administrator/.hermes/hermes-agent

# 服务器配置
PORT=3000
HOST=127.0.0.1
```

### 常见错误

❌ **错误 1：配置了 `HERMES_API_URL` 但 Vite 读取 `CLAUDE_API_URL`**
- **症状**：Vite 启动后卡住，端口未监听
- **原因**：`vite.config.ts` 读取的是 `CLAUDE_API_URL` 环境变量
- **修复**：在 `.env` 中使用 `CLAUDE_API_URL`

❌ **错误 2：`HERMES_AGENT_PATH` 指向配置目录而非源码目录**
- **症状**：Vite 健康检查失败，提示找不到 `gateway/run.py`
- **错误配置**：`HERMES_AGENT_PATH=/home/administrator/.hermes`（这是配置目录）
- **正确配置**：`HERMES_AGENT_PATH=/home/administrator/.hermes/hermes-agent`（源码目录）
- **验证**：`ls $HERMES_AGENT_PATH/gateway/run.py` 应存在

❌ **错误 3：用 `node` 直接运行 `node_modules/.bin/vite`**
- **症状**：`SyntaxError: missing ) after argument list`
- **原因**：`node_modules/.bin/vite` 是 shell 脚本，不是 JS 文件
- **修复**：使用 `pnpm exec vite dev` 或 `pnpm run start:dev`

## Hermes Agent API 配置

Workspace 需要 Hermes Agent 启用 HTTP API Server。

### 1. 启用 API Server

编辑 `~/.hermes/.env`，添加：

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
```

### 2. 重启 Gateway

```bash
hermes gateway restart
```

### 3. 验证 API 可用

```bash
# 检查端口监听
ss -tlnp | grep 8642

# 或
curl http://127.0.0.1:8642/health
```

## 启动流程

### 开发模式（推荐）

```bash
cd /path/to/hermes-workspace
pnpm run start:dev
```

- 自动热重载
- 详细错误信息
- 首次启动编译耗时约 60 秒（正常）

### 生产模式

```bash
pnpm build
pnpm start
```

### 后台运行

```bash
# WSL 环境
cd /mnt/d/Hermes/hermes-workspace
nohup pnpm run start:dev > /tmp/workspace.log 2>&1 &

# 查看日志
tail -f /tmp/workspace.log
```

## 架构模式：Simple vs Swarm

Hermes Workspace 支持两种架构模式：

### 1. Simple 模式（推荐新手）

**特点**：
- 直接与 Hermes Agent Gateway API 通信（`/v1/chat/completions`）
- 无需额外配置 profiles、skills、wrappers
- 适合单用户、简单对话场景

**部署**：按上述"快速部署"步骤即可。

### 2. Swarm 模式（高级多 agent 协作）

**特点**：
- 通过 **tmux 会话**与多个 Hermes profiles 交互（`/api/swarm-direct-chat`）
- 需要完整的 swarm 基础设施：
  - `~/.hermes/profiles/<worker-id>/` 目录（每个 worker 一个 profile）
  - 对应的 `<worker-id>-core` skills
  - `~/.local/bin/<wrapper-name>` wrapper 脚本
  - `swarm.yaml` 配置文件（定义 workers、tools、skills）
- 适合多 agent 协作、任务分解、专业化分工场景

**前提条件**：
- 必须先配置完整的 swarm 基础设施（10+ profiles、skills、wrappers）
- 需要理解 Hermes profiles、skills、Kanban 等高级概念
- 参考 `AGENTS.md` 和 `swarm.yaml` 配置示例

**错误信号**：
- ❌ "Authentication error — check your API key in Settings"（但 Gateway API 正常）
- ❌ 前端能加载，但发送消息无响应
- ❌ 日志显示 `tmux not installed` 或 `profile path not found`

**根本原因**：Workspace 尝试通过 tmux 启动不存在的 worker profiles。

**解决方案**：
1. **如果你只是想要 Web 聊天界面**：使用其他更简单的前端（Open WebUI、LibreChat、Chatbox），它们直接调用 `/v1/chat/completions`，无需 swarm 基础设施。
2. **如果你需要 swarm 功能**：先完成 swarm 基础设施配置（超出本文档范围，参考 Workspace 仓库的 `AGENTS.md`）。

## 常见问题

### 首次访问超时或"没有反应"

**症状**：浏览器打开 `http://localhost:3000/` 后，页面加载但无法发送消息，或 `/api/connection-status` 超时。

**原因**：首次探测 Gateway 和 Dashboard 能力需要 20-30 秒（`probeGateway()` 并行探测多个端点）。前端可能在探测完成前超时。

**解决方案**：
1. **等待首次探测完成**（约 30 秒），然后刷新浏览器
2. **手动触发探测**：在终端执行
   ```bash
   curl http://localhost:3000/api/connection-status
   ```
   等待返回（可能需要 30-60 秒），然后刷新浏览器

**验证探测成功**：
```bash
curl http://localhost:3000/api/connection-status
# 应返回：{"status":"enhanced","label":"Enhanced",...}
```

探测结果会缓存，后续访问立即响应。

### "Authentication error" 但 Gateway API 正常

**症状**：
- `curl http://127.0.0.1:8642/v1/chat/completions` 返回正常响应
- 但 Workspace 前端显示 "Authentication error — check your API key in Settings"

**根本原因**：Workspace 使用 **Swarm 模式**（通过 tmux 与 profiles 交互），但你的环境缺少 swarm 基础设施。

**诊断**：
```bash
# 检查是否存在 profiles 目录
ls ~/.hermes/profiles/

# 检查 Workspace 是否配置了 swarm
cat /path/to/hermes-workspace/swarm.yaml
```

如果 `profiles/` 目录为空或不存在，说明你的环境是标准 Hermes Agent，不支持 Workspace 的 swarm 模式。

**解决方案**：见上方"架构模式"章节。

### Dashboard 服务未启动

**症状**：`/api/connection-status` 返回 `"dashboard": false`

**原因**：Workspace 需要 Hermes Dashboard（端口 9119）提供会话管理、技能配置等功能。

**解决方案**：
```bash
# 启动 Dashboard
hermes dashboard

# 验证
curl http://127.0.0.1:9119/api/status
```

Dashboard 和 Gateway 是独立服务，都需要运行。

## 诊断技巧

### 进程无输出时捕获日志

后台进程的 stdout/stderr 可能未正确捕获。使用 `script` 或 `tee`：

```bash
# 方法 1：tee 到文件
pnpm exec vite dev 2>&1 | tee /tmp/vite.log

# 方法 2：script 命令
script -c "pnpm run start:dev" /tmp/vite.log
```

### 检查 Vite 配置

```bash
# 查看 vite.config.ts 读取的环境变量
grep -A 5 "process.env" vite.config.ts
```

### 验证 Hermes Agent 路径

```bash
# 检查源码目录结构
ls -la $HERMES_AGENT_PATH/gateway/run.py
ls -la $HERMES_AGENT_PATH/run_agent.py
```

## 架构说明

- **Vite 自动启动逻辑**：`vite.config.ts` 包含健康检查，会自动启动 Hermes Agent（如果未运行）
- **通信方式**：Workspace 通过 HTTP API 与 Gateway 通信，不直接访问 Hermes 配置或会话数据
- **会话隔离**：Web 界面的会话独立于 CLI 和 Gateway 的其他平台会话

## Windows + WSL 部署

在 WSL 中部署 Workspace，Windows 浏览器访问：

```bash
# WSL 中启动
cd /mnt/d/Hermes/hermes-workspace
pnpm run start:dev

# Windows 浏览器打开
powershell.exe -Command "Start-Process 'http://localhost:3000'"
```

WSL2 的 localhost 自动转发到 Windows，无需额外配置。

## 相关资源

- 仓库：https://github.com/outsourc-e/hermes-workspace
- Hermes Agent 文档：https://hermes-agent.nousresearch.com/docs
- Hermes Agent API 配置：`hermes config set API_SERVER_ENABLED true`
