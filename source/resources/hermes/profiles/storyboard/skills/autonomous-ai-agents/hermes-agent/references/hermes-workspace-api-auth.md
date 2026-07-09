# Hermes Workspace API Authentication

## Problem

Hermes Workspace 前端加载正常，但无法对话，显示错误：

```
Authentication error - check your API key in Settings
```

浏览器控制台或 `/api/send-stream` 返回 403：

```json
{
  "error": "Session continuation requires API key authentication. Configure API_SERVER_KEY to enable this feature."
}
```

## Root Cause

Hermes Gateway 的 **session API** 功能需要 `API_SERVER_KEY` 配置才能启用。

Workspace 的 `/api/send-stream` 端点调用 Gateway 的 `/v1/chat/completions` 时会传递 `sessionKey` 参数进行会话管理。如果 Gateway 没有配置 `API_SERVER_KEY`，session 功能被禁用，返回 403 错误。

## Solution

在 `~/.hermes/.env` 中添加 `API_SERVER_KEY`，然后重启 Gateway：

```bash
echo 'API_SERVER_KEY=workspace-secret-key-2026' >> ~/.hermes/.env
hermes gateway run --replace
```

**注意：**
- `~/.hermes/.env` 是 credential store，工具无法直接读写（安全机制）
- 必须手动执行上述命令
- 重启 Gateway 后刷新浏览器，Workspace 即可正常对话

## Verification

测试 Workspace API：

```bash
curl -X POST http://localhost:3000/api/send-stream \
  -H "Content-Type: application/json" \
  -d '{"sessionKey":"main","message":"test"}'
```

应该返回流式响应，而非 403 错误。

## Related Configuration

### Workspace `.env` (D:\Hermes\hermes-workspace\.env)

```bash
HERMES_API_URL=http://127.0.0.1:8642
CLAUDE_API_URL=http://127.0.0.1:8642
HERMES_AGENT_PATH=/home/administrator/.hermes/hermes-agent/
```

### Gateway 配置 (~/.hermes/.env)

```bash
API_SERVER_KEY=workspace-secret-key-2026  # 必需，启用 session API
```

### 可选：Workspace 密码保护

在 Workspace `.env` 中添加：

```bash
HERMES_PASSWORD=your-password-here
```

重启 Workspace 后，首次访问需要输入密码。

## Architecture

```
Browser → Workspace (localhost:3000)
            ↓ /api/send-stream
          Gateway (127.0.0.1:8642)
            ↓ /v1/chat/completions + sessionKey
          Hermes Agent
```

- **Workspace** 是前端 UI（TanStack Start + Vite）
- **Gateway** 提供 OpenAI 兼容的 API 端点
- **API_SERVER_KEY** 启用 Gateway 的 session 管理功能
- **HERMES_PASSWORD** 保护 Workspace UI（可选）

## Troubleshooting

### 1. Gateway 未启动

```bash
hermes gateway status
# 如果未运行：
hermes gateway run --replace
```

### 2. 端口冲突

检查 Gateway 端口（默认 8642）：

```bash
curl http://127.0.0.1:8642/v1/models
```

应该返回模型列表。

### 3. Workspace 无法连接 Gateway

检查 Workspace `.env` 中的 `HERMES_API_URL` 是否正确。

### 4. Dashboard 超时

首次访问 `/api/connection-status` 需要约 30 秒探测 Dashboard（端口 9119）。等待完成后刷新浏览器。

## Security Notes

- `API_SERVER_KEY` 是 Gateway session API 的认证密钥
- `HERMES_PASSWORD` 是 Workspace UI 的访问密码
- 两者独立，分别保护不同层级
- 生产环境建议使用强密码并启用 HTTPS
