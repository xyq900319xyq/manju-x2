# 漫剧助手X-2 发版前后指南

> 配套 `GITHUB_RELEASE.md`(发版操作步骤)。
> 本文档覆盖:**发版前**(social 营销) + **发版后**(24h/7d/30d 监控 + 应急响应)。

---

## 一、发版前 Social Media 模板

### 1. 微信朋友圈 / 微信群(中长文)

```
🎉 漫剧助手X-2 v1.0.0 首发!

AI 漫剧创作助手用户版,1 个 Setup.exe 全搞定(91 MB,无需 Python,无需 hermes)。

✨ 能做什么:
- 输入剧情大纲 → 自动生成分镜(每集多个 Segments)
- 角色 / 场景 / 道具 资产图自动生成
- 视频提示词适配 Seedance / Veo / Sora
- 支持 DeepSeek / Agnes / 创维中转 等多种 API

🛡️ 安全:
- API key 用 Windows DPAPI 加密(绑定用户账号)
- 免 UAC 安装,默认装到 C:\漫剧助手X-2\
- 零开发数据泄漏(物理隔离)

📥 下载:https://github.com/xyq900319xyq/manju-x2/releases/latest
📖 文档:https://github.com/xyq900319xyq/manju-x2/blob/main/docs/INSTALL.md
💬 反馈:https://github.com/xyq900319xyq/manju-x2/issues

#AI创作 #漫剧 #分镜 #视频生成
```

### 2. 微博(140 字以内 + 链接)

```
漫剧助手X-2 v1.0.0 首发 🎉
1 个 Setup.exe 装好就用,AI 生成分镜/视频提示词
支持 DeepSeek/Agnes/创维中转,免 UAC 装
API key Windows DPAPI 加密
下载 → github.com/xyq900319xyq/manju-x2/releases/latest

#AI漫剧# #视频生成# #开源软件#
```

### 3. X / Twitter(英文,280 字符)

```
🚀 ManjuX-2 v1.0.0 released!

AI manga drama creation tool - Windows only, single Setup.exe (91 MB).
Generate storyboards & video prompts from plot outlines.
Supports DeepSeek/Agnes, DPAPI encryption for API keys.

Download: https://github.com/xyq900319xyq/manju-x2/releases/latest

#AI #storyboard #opensource
```

### 4. 知乎(长文,带截图)

```
# 漫剧助手X-2 v1.0.0:从剧本到分镜到视频提示词的一站式 AI 工具

## 痛点

做 AI 漫剧 / 短剧 / 解说视频的朋友应该都遇到过:
- 写完剧情大纲,还要手动拆场次,分镜
- 想画角色 / 场景参考图,要切到 Midjourney
- 写视频提示词,得研究 Seedance 文档
- 切来切去,效率低

## 解决

[截图:主界面 - 剧本 tab]

[截图:wizard 6 步配置 API]

漫剧助手X-2 把以上流程串成一个工作流:

1. **输入剧情大纲**(自然语言)
2. **AI 生成分镜**(每集 N 个 Segments,每段 5-15 秒)
3. **生成资产图**(角色 / 场景 / 道具,带参考图一致性)
4. **生成视频提示词**(适配 Seedance / Veo / Sora)

## 技术亮点

- **DPAPI 加密**:API key 用 Windows DPAPI 加密(绑定用户账号,跨用户读不出)
- **免 UAC 安装**:Inno Setup `PrivilegesRequired=lowest`,默认装到 C:\漫剧助手X-2\
- **自包含 hermes**:PyInstaller + 独立 hermes.exe,用户电脑无需装 Python
- **多 API 支持**:DeepSeek / Agnes / 创维中转 / 自定义 OpenAI 兼容

## 下载

https://github.com/xyq900319xyq/manju-x2/releases/latest

## 反馈

[评论区]欢迎大家试用反馈,issues 我会一一回复。
```

### 5. 抖音 / B 站 视频脚本(30-60 秒,演示用)

```
[开场 0-3s]
"做漫剧最痛苦的是什么?"
"手写分镜 / 切不同 AI 工具 / 反复调整 prompt"

[介绍 3-8s]
"试试漫剧助手X-2"
"1 个 Setup.exe 装好就用"
[截图:安装过程,装好双击]

[演示 8-40s]
- 输入剧情大纲:"主角林轩是天才剑修,被诬陷偷剑..."
- 点 "生成分镜"
- 30 秒后:看到完整分镜(场景/对话/动作/时长)
- 切到 "资产" tab
- 点 "生成角色图"
- 看到角色图,自动存到 outputs
- 切到 "提示词" tab
- 点 "生成视频提示词"
- 看到 Seedance 格式的提示词

[结尾 40-60s]
"全部过程 5 分钟,不用切换工具"
"支持 DeepSeek / Agnes / 创维中转"
"API key 加密存到本机,不会泄漏"
"下载链接在评论区"

[文字叠加]
"漫剧助手X-2"
"AI 漫剧创作助手"
"github.com/xyq900319xyq/manju-x2"
```

### 6. 简评类(少数派 / V2EX / 即刻)

```
# 漫剧助手X-2 v1.0.0 开了

断断续续开发了 N 个月,用户版 v1.0.0 终于发了。
1 个 91 MB 的 Setup.exe,免 UAC 装到 C:\ 就能用。

技术栈:
- PySide6 GUI
- hermes-agent 作为 LLM CLI 引擎
- PyInstaller 打包成 onedir
- Inno Setup 做安装器
- Windows DPAPI 加密 API key

代码全开源(用户版),dev 端商业版另算。

GitHub: https://github.com/xyq900319xyq/manju-x2

欢迎 PR / Issue。
```

---

## 二、发版后 24 小时监控清单

发版后**前 24h 是关键**(灰度用户密集反馈期)。

### 监控项

#### 1. GitHub Releases 页面

- **下载次数**:每 4h 看一次
  - 正常:0-50 (刚发 24h 内)
  - 关注:> 100(爆款)/ 突然 0(可能被 GitHub 屏蔽)
- **附件下载分布**:
  - Setup.exe:应该最多
  - md5/sha256:应该很少(技术用户用)
- **标签**:确认 "Latest" 标记正确

#### 2. GitHub Issues

- **新 issue 数**:每 2h 看一次
  - 正常:0-5 (24h 内)
  - 关注:突然> 10(可能批量报错)/ 0(可能用户没找到 issue 入口)
- **按标签分类**:
  - `bug`:需要技术调查
  - `enhancement`:未来版本
  - `question`:FAQ 可能已答
  - **没标签的**:user 自定义
- **优先级分流**:
  - 🔴 P0(阻塞):< 4h 响应
  - 🟡 P1(影响使用):< 24h
  - 🟢 P2(小问题):< 1 周

#### 3. 微信群 / 朋友圈反馈

- 主动询问:在群里发"装好用过的反馈下"
- 关注:崩溃 / 卡住 / API 报错 / 不会操作

#### 4. 关键错误码(从 logs 统计)

如果有自己的 analytics(当前 v1.0.0 **没有** telemetry),这步跳过。
未来 v1.1.0 可以加 opt-in 错误上报。

### 24h 应急响应

| 现象 | 紧急度 | 操作 |
|---|---|---|
| Setup.exe 装不上(签名/兼容) | 🔴 P0 | 1h 内出 hotfix v1.0.1 |
| wizard 弹不出来 | 🔴 P0 | 1h 内排查,rebuild |
| API key 加密失效 | 🔴 P0 | 立即 issue 公告 + 出 v1.0.1 |
| 崩溃闪退(< 1% 用户) | 🟡 P1 | 24h 内排查 |
| UI 显示问题 | 🟡 P1 | 24h 内修 |
| API 调用失败 | 🟡 P1 | 检查 API provider 状态,公告 |
| 文档错别字 | 🟢 P2 | 1 周内修 |

### 24h 数据记录

填这个表(每天 commit 到 git 作 log):

```markdown
## v1.0.0 发版监控 - 2026-07-XX

**发版时间**: 2026-07-XX HH:MM
**当前时间**: 2026-07-XX HH:MM (发后 N 小时)

### 数据
- 下载次数: X (24h +X)
- GitHub stars: +X (累计 X)
- 新 issues: X (累计 X)
  - bug: X
  - enhancement: X
  - question: X
- 关闭 issues: X
- 微信群反馈: X 条

### 关注
- [ ] 关键 issue: ...
- [ ] 紧急 PR: ...
- [ ] 公告: ...

### 决策
- [ ] 不发 hotfix(无 P0)
- [ ] 发 hotfix v1.0.1(原因: ...)
- [ ] 文档更新(原因: ...)
```

---

## 三、发版后 7 天监控

### 7d 目标

- ✅ 0 P0 阻塞 issue
- ✅ < 5 个 P1 重要 issue
- ✅ 下载次数 > 100
- ✅ GitHub stars > 20(早期推广效果)

### 7d 行动

1. **汇总 issue 趋势**(看哪些问题集中)
2. **更新 FAQ.md**(从 issues 提取)
3. **更新 INSTALL.md**(如果有用户装错)
4. **发周报**(在群里/朋友圈)
5. **决定 v1.0.1 内容**(从 V1.0.1_PLAN.md + 新 issue 修)

### 周报模板(发到群/朋友圈)

```
漫剧助手X-2 v1.0.0 发版周报 📊

发版后第 7 天数据:
✅ 下载次数: 234 (+45 比预期少,可能 GitHub 限速)
✅ 新 issues: 8(bug 3, enhancement 4, question 1)
✅ 已关闭: 5
🔴 P0 阻塞: 0
🟡 P1 待修: 2

主要问题:
1. 中文 UI 显示英文(装时漏勾 Chinese)
2. 视频生成偶发超时

下个版本 v1.0.1 计划(2026-07-22):
- 修中文 UI
- 加视频 API 重试
- 修 v1.0.0 报告的 5 个 P1 bug

感谢大家的反馈 🙏
```

---

## 四、发版后 30 天监控

### 30d 目标

- ✅ 0 P0 阻塞
- ✅ P1 重要 issue 全部有解决方案
- ✅ 下载次数 > 500
- ✅ GitHub stars > 50
- ✅ v1.0.1 / v1.0.2 / v1.1.0 路线图明确

### 30d 行动

1. **汇总 v1.0.0 → v1.0.1 修复清单**
2. **发 v1.0.1**(按 V1.0.1_PLAN.md + 新 issues)
3. **收集 feature request**(Issues 标 `enhancement`)
4. **写月度总结**(博客 / 微信)
5. **规划 v1.1.0**(从 enhancement issues 排序)

---

## 五、应急响应(出问题时的回滚)

### 场景 A: 发现 P0 bug(装不上 / 崩溃)

1. **2h 内**:
   - GitHub issue 置顶 + Label `P0-blocker`
   - Release 页面加警告(Edit release)
2. **8h 内**:
   - 修代码 + 跑 `python build_x2.py` 出 v1.0.1
   - 通知所有 user(微信群 + 朋友圈 + 微博)
3. **24h 内**:
   - v1.0.1 发布(走 GITHUB_RELEASE.md 7 步)
   - v1.0.0 release 标 "Pre-release / 弃用" + 加 v1.0.1 链接

### 场景 B: API provider 挂掉

- DeepSeek / Agnes / 创维中转 任何一个挂,用户全部无法生成
1. **立即**:
   - Issue 公告
   - 微信群通知
2. **短期**:
   - 文档加 status 链接
3. **长期**:
   - 加多 provider 故障转移
   - 准备本地 fallback

### 场景 C: GitHub 限流 / 被墙

1. **临时**:
   - 加 Gitee mirror
   - 用 CDN 加速
2. **长期**:
   - 加 release 镜像(国内)
   - 准备私有分发渠道

### 场景 D: 紧急回滚(dev 端 0.7.8.x → 用户版 v1.0.0)

如果 dev 端有需求切回 v1.0.0(例如比较 v1.0.0 vs dev 行为):
1. **dev 端**:
   - `D:\漫剧助手\` 保持不动(dev 主战场)
2. **用户版**:
   - 装 v1.0.0 旧版 = 装 Setup.exe(覆盖)
   - 不需要 rollback 操作,默认 v1.0.0 是 stable

---

## 六、关键链接(发版后必更新)

发版后第一件事:把这些链接加到 release description + 群置顶:

```
📥 下载: https://github.com/xyq900319xyq/manju-x2/releases/latest
📖 文档: https://github.com/xyq900319xyq/manju-x2/blob/main/docs/INSTALL.md
❓ FAQ: https://github.com/xyq900319xyq/manju-x2/blob/main/docs/FAQ.md
📋 更新日志: https://github.com/xyq900319xyq/manju-x2/blob/main/docs/更新日志.md
🐛 反馈: https://github.com/xyq900319xyq/manju-x2/issues
💬 讨论: https://github.com/xyq900319xyq/manju-x2/discussions(可选)
🔒 安全: https://github.com/xyq900319xyq/manju-x2/security/advisories/new
```

---

## 七、长期维护 checklist(发版后 1-3 月)

### 每月
- [ ] review issues 标签
- [ ] merge 小 PR
- [ ] 更新依赖(`pip list --outdated`)
- [ ] 跑 `python build_x2.py` 验证能 build
- [ ] 发月度报告

### 每季度
- [ ] 升级 hermes-agent 依赖
- [ ] 升级 PySide6 依赖
- [ ] 升级 Inno Setup
- [ ] 升 PyInstaller
- [ ] 跑完整回归测试(VM_TEST_CHECKLIST)
- [ ] 决定下季度版本

### 每年
- [ ] 升级 Python 主版本
- [ ] 重新评估 API provider(有没有更好/更便宜的)
- [ ] 重新设计架构(可能换 web 化 / 移动化)

---

## 附:数据指标定义

| 指标 | 怎么算 | 健康值(参考) |
|---|---|---|
| 日下载数 | GitHub Release API 拿 `assets[].download_count` | > 10(24h) / > 50(7d) / > 200(30d) |
| Stars | GitHub API `stargazers_count` | > 20(7d) / > 50(30d) |
| Issues 关闭率 | closed / (open + closed) | > 70% |
| P0 平均响应时间 | (首次响应时间 - issue 创建时间) | < 4h |
| v1.0.x 升级率 | v1.0.1 下载 / v1.0.0 下载 | > 50%(7d) / > 80%(30d) |
| 崩溃率(待 telemetry) | crash_count / active_users | < 1% |

---

**配合使用**:
- 发版前:`GITHUB_RELEASE.md`(7 步操作)
- 发版后:本文档(social + 监控 + 应急)
- 跨版本:`V1.0.1_PLAN.md`(bug 计划)
