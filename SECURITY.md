# 安全策略

## 支持的版本

| 版本 | 支持状态 |
|---|---|
| v1.0.0 (latest) | ✅ 活跃支持 |

旧版本不提供安全更新,**强烈建议升级到最新版**。

## 报告漏洞

发现安全漏洞?**请勿在 GitHub Issues 公开**(会暴露给攻击者)。

请发邮件到: **&lt;your-email&gt;**(待发版人填)

邮件包含:
- 漏洞描述
- 复现步骤
- 影响范围
- 你的联系信息(可选)

我们承诺:
- **24 小时内**首次响应
- **7 天内**评估严重程度 + 给修复计划
- 修复后**公开致谢**(除非你要求匿名)

## 安全实践

漫剧助手X-2 本身的安全设计:
- ✅ **API key 加密**:Windows DPAPI 加密存到 `config\secrets.bin`(绑定 Windows 用户)
- ✅ **无明文 key**: hermes_api.json 模板所有 `api_key` 字段为空
- ✅ **0 dev 密钥**: 用户版物理隔离 dev 端仓库
- ✅ **HTTPS**: 所有 API 调用走 HTTPS(LLM / 图像 / 视频 / 图床)
- ✅ **SSL verify**: 兼容旧 server 时才 `verify=False`(复刻老 software 行为)
- ✅ **输入校验**: 路径白名单 / SQL 参数化 / HTML escape

## 已知风险

- **DPAPI 跨用户隔离**: API key 绑 Windows 用户账号,换账号 / 重装系统后无法解密(需重填)
- **本地明文数据库**: SQLite `data\manju.db` 不加密(项目内容),电脑被别人用可读
- **hermes.exe 子进程**: 生图 / 视频通过 hermes CLI 调(临时 spawn),有进程残留风险

## 不在范围内的

- 第三方 API(DeepSeek / Agnes / 创维中转 / imgbb)的安全问题 → 找对应官方
- hermes.exe 的安全问题 → 找 hermes 项目
- 用户电脑 / 操作系统的安全问题 → 找微软 / 杀软厂商
