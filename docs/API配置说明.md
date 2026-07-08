# API 配置说明

## 支持的 API

| Provider | Base URL | 备注 |
|---|---|---|
| **DeepSeek** | `https://api.deepseek.com/v1` | 官方,推荐 |
| **Agnes AI** | `https://apihub.agnes-ai.com/v1` | 中转,支持多模型 |
| **创维中转** | `https://chuangwei.cyou/v1` | 中转,支持 Gemini 等 |

填 **API key** 即可,base_url 默认就是上面这些。

## 填 key

1. 打开漫剧助手X-2
2. **设置** tab → **API 配置**
3. 选 provider → 粘贴 key → 保存
4. Key 用 Windows DPAPI 加密,只存当前用户,其他用户无法解密

## 多个 provider

可以同时配多个 provider,运行时可切换"活跃"。

例:
- DeepSeek (主力) + Agnes (备用)
- 设 `active: "deepseek"` 时所有请求走 DeepSeek
- 出问题时切到 `active: "agnes"`

## 测 key 是否有效

设置 → API 配置 → 点"测试连接"按钮(如果有的话)。
或手动生成一个测试项目看能不能出结果。

## Key 安全

- ✅ Key 用 Windows DPAPI 加密 (`%APPDATA%` 类似的本地存储)
- ✅ 不会上传到任何服务器
- ✅ 不会写进 git / 不会泄露
- ❌ 不要把 `config\hermes_api.json` 发给别人看(虽然加密了,跨用户解不开)

## 出错了

| 错误 | 解决 |
|---|---|
| 401 Unauthorized | key 错了或过期,重新填 |
| 429 Too Many Requests | 限流,等会儿再试 |
| Connection timeout | 网络问题,看 base_url 能不能 ping 通 |
| "Model not found" | model 名字错了,改成 provider 文档里推荐的 |

## 模型推荐

| Provider | 推荐 model | 用途 |
|---|---|---|
| DeepSeek | `deepseek-v4-pro` | 文本生成(分镜/视频提示词) |
| Agnes | `agnes-2.0-flash` | 文本生成(更快更便宜) |
| Agnes | `agnes-image-2.1-flash` | 生图 |
| Agnes | `agnes-video-v2.0` | 生视频 |

具体可用 model 以 provider 文档为准。
