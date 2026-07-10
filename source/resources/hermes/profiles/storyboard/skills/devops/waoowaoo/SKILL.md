---
name: waoowaoo
description: Deploy, debug, and operate the waoowaoo open-source AI short drama/comic tool via Docker Compose on Windows + WSL. Covers deployment, China network workarounds, API key debugging, and template mismatch fixes.
---

# waoowaoo — AI 短剧/漫画制作工具运维

Docker Compose 部署的开源 AI 短剧/漫画生成工具（Next.js + MySQL + Redis + MinIO）。

## 触发条件
- 部署、启动、停止、重启 waoowaoo
- waoowaoo 图片/视频/语音生成失败
- API 配置问题（模型选择、key 配置、模板不匹配）
- 数据库直连调试
- 日志分析

## 部署

> ⚠️ **Status (2026-05-22): waoowaoo has been deleted.** The user moved to 魔因漫创 (moyin-creator) as their primary AI short drama tool. This skill is retained as reference for the image generation count analysis, task debugging patterns, and content export workflow — all of which may be applicable to similar Docker Compose + Next.js + BullMQ apps.

### 前置条件
- Docker Desktop（安装到 D 盘以节省 C 盘空间）
- 在中国大陆：`ghcr.io` 被墙，需用 `ghcr.dockerproxy.com` 镜像

### 快速启动
```powershell
# Docker Desktop bin 路径
$env:PATH = "D:\Program Files\Docker\resources\bin;" + $env:PATH

# 在中国拉取镜像
docker pull ghcr.dockerproxy.com/saturndec/waoowaoo:latest
docker tag ghcr.dockerproxy.com/saturndec/waoowaoo:latest ghcr.io/saturndec/waoowaoo:latest

# 拉取其余镜像
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull minio/minio:RELEASE.2025-02-28T09-55-16Z

# 启动
cd D:\waoowaoo
docker compose up -d
```

### 服务端口
| 服务 | 端口 | 凭证 |
|------|------|------|
| App | 13000 | — |
| Bull Board | 13010 | — |
| MySQL | 13306 | root/waoowaoo123 |
| Redis | 16379 | 无密码 |
| MinIO API | 19000 | minioadmin/minioadmin |
| MinIO Console | 19001 | minioadmin/minioadmin |

### 常用命令
```powershell
# 查看状态
docker compose ps

# 查看日志
docker logs waoowaoo-app --tail 100

# 重启
docker compose restart app

# 数据库直连
docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 waoowaoo -e "SQL"
```

## API 调试

### API Key 加密存储
woowaoo 的 API Key 在数据库中是 **AES-256-GCM 加密** 的。不能直接从数据库取出来用。
- 加密算法：AES-256-GCM
- 密钥派生：PBKDF2-SHA256, salt=`waoowaoo-api-key-salt-v1`, 100000 迭代
- 密钥来源：环境变量 `API_ENCRYPTION_KEY`（开源版默认 `waoowaoo-opensource-fixed-key-2026`）
- 密文格式：`iv:authTag:ciphertext`（hex 编码，三段式冒号分隔）

解密脚本见 `references/api-key-decrypt.md`。

### 图片生成模板不匹配（OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND）

**根因**：API 返回 `{"data": [{"b64_json": "..."}]}` 但模板期望 `{"data": [{"url": "..."}]}`

**诊断步骤**：
1. 从日志定位图片模型 key（如 `openai-compatible:uuid::model-name`）
2. 从 `user_preferences.customProviders` JSON 中找 provider 的 `baseUrl` 和 `apiKey`
3. 用 `references/api-key-decrypt.md` 中的脚本解密 key
4. `curl` 直调 API 的 `/v1/images/generations` 看实际返回格式
5. 对比模板配置（在 `customModels` JSON 的 `compatMediaTemplate` 字段）

**修复方向**：
- 改模板 `outputUrlPath` 从 `$.data[0].url` 到 `$.data[0].b64_json`（需同时改代码支持 base64→data URL 转换）
- 或查 API 是否支持 `response_format: "url"` 参数
- 或换 chat completions 端点（返回到 data URL 的 markdown 图片）

详见 `references/api-image-template-debug.md`。

## 数据库直连更新模板（绕过 Shell 转义问题）

Shell 中 JSON 转义易出错，用 Python MySQL 直连：

```python
import mysql.connector, json

conn = mysql.connector.connect(
    host='127.0.0.1', port=13306,
    user='root', password='waoowaoo123', database='waoowaoo'
)
cursor = conn.cursor()

# 读取
cursor.execute("SELECT customModels FROM user_preferences WHERE userId=%s", (user_id,))
row = cursor.fetchone()
models = json.loads(row[0])

# 修改模板（如加 response_format）
for m in models:
    if 'gpt-image' in m.get('modelId', ''):
        m['compatMediaTemplate']['create']['bodyTemplate']['response_format'] = 'url'

# 写回
cursor.execute("UPDATE user_preferences SET customModels=%s WHERE userId=%s",
               (json.dumps(models, ensure_ascii=False), user_id))
conn.commit()
conn.close()
```

修改后需重启 app：`docker restart waoowaoo-app`

## 角色 Prompt 自定义

角色图片生成 prompt 由三部分拼接，详见 `references/character-prompt-structure.md`。

### 即插即用的模板变量
身体模板中可用的变量（来自 `template-image.ts:70-77`）：
`{{model}}`, `{{prompt}}`, `{{image}}`, `{{images}}`, `{{aspectRatio}}`, `{{resolution}}`, `{{size}}`, `{{extra}}`

### 比例修改：`3:2` → `16:9`
⚠️ 编译代码中 `'3:2'` 同时作为比例映射表的键名和常量值，盲目 `sed` 替换会破坏映射表（产生重复 `16:9` 键）。

**正确做法：直接在 bodyTemplate 硬编码 `size` 值**，跳过 `aspectRatioToOpenAISize()` 映射：
```json
{ "model": "{{model}}", "prompt": "{{prompt}}", "response_format": "url", "size": "1792x1024" }
```
`16:9 → 1792x1024` 是 `generator-api.ts` 中的标准映射。此方式对 GPT 系列模型有效；对其他 provider 需验证支持的 size。

源码中的 `CHARACTER_ASSET_IMAGE_RATIO` 常量（`constants.ts:201`）应同步修改但生产构建不会自动重编——因此模板硬编码是唯一可靠手段。

### 新增画风
1. 编辑容器内 `/app/src/lib/constants.ts` 的 `ART_STYLES` 数组（第 100-165 行）
2. 找出所有包含该数组的编译 JS 文件（`grep -rl 'realistic.*label.*真人' /app/.next/`，约 14 个）
3. 在每个文件的 `realistic"...}]` 后追加新条目 `,{value:"id",...}`
4. 重启容器

### 角色创建页显示画风选择器（项目模式）
源码 `CharacterCreationForm.tsx:172`：
```tsx
// Before:
{mode === 'asset-hub' && !isSubAppearance && (
// After:
{!isSubAppearance && (
```
编译文件（2 个 chunk）中对应的模式是 `"asset-hub"===VAR&&!VAR2&&` → `!VAR2&&`。

### 画风优先级
`character-image-task-handler.ts` 先用 `payload.artStyle`（请求级），fallback 到 `models.artStyle`（项目级 `novel_promotion_projects.artStyle`），**不是**用户全局默认值 `user_preferences.artStyle`。

## 图片生成数量与请求次数

**为什么每次生成人物图有 3 个请求？** 因为默认每次生成 **3 张候选图**，for 循环每张一次 API 调用。

### 完整代码链路

```
用户点击生成/刷新
  ↓
CharacterSection.tsx 判断：
  - validImageCount === 1 → onRegenerateSingle → 后端 imageIndex → 1 请求
  - validImageCount !== 1 → onRegenerateGroup(count) → count 默认 undefined
  ↓
POST /api/assets/{id}/generate   body: { count: undefined }
  ↓
character-image-task-handler.ts:
  normalizeImageGenerationCount('character', undefined) → defaultValue: 3
  ↓
for (i = 0; i < 3; i++)  →  3 次 API 调用
```

### 核心配置：`/app/src/lib/image-generation/count.ts`

```ts
character: {
    defaultValue: 3,   // ← 默认 3 张
    min: 1,
    max: 6,
    storageKey: 'image-count:character',  // localStorage key
}
```

`normalizeImageGenerationCount` 逻辑（`count.ts:52-60`）：
1. `payload.count` 如果是有效数字 → 用它
2. 否则 → 用 defaultValue（character 默认 3）
3. clamp 到 [min, max]

### 前端请求数判定

| 场景 | 触发的回调 | count 参数 | 请求数 |
|------|-----------|-----------|--------|
| 首次生成（compact 模式） | `onGenerate(count)` | localStorage 存储的值 | 1-6 |
| 单图模式点刷新 | `onRegenerate()` | **undefined → 默认 3** | 3 |
| 多图选择模式点重新生成 | `onRegenerate(generatedImageCount)` | 已有图片数 | =已有数 |
| 选择模式仅 1 张有效图 | `onRegenerateSingle(imageIndex)` | N/A | 1 |

### 减少请求数的方法

1. **前端**：首次生成时把数量选为 1（localStorage 会记住）
2. **改后端默认值**（一劳永逸）。生产模式（`next start`）下源码修改不生效，必须改编译产物：
   ```bash
   # 一次改完所有编译文件（source + .next/ static + .next/ server chunks）
   docker exec waoowaoo-app sed -i 's/defaultValue: 3/defaultValue: 1/g' /app/src/lib/image-generation/count.ts

   docker exec waoowaoo-app sh -c 'for f in $(grep -rl "defaultValue:3" /app/.next/ 2>/dev/null); do
     sed -i "s/defaultValue:3/defaultValue:1/g" "$f"
     echo "Fixed: $f"
   done'

   cd /mnt/d/waoowaoo && docker compose restart app
   ```
   验证无遗漏：`docker exec waoowaoo-app sh -c 'grep -rl "defaultValue:3" /app/.next/ | wc -l'` → 输出应为 0。
3. **改前端逻辑**：让刷新按钮也传 `count: 1`

详见 `references/image-generation-count.md`。

## 表结构

关键表：
- `user_preferences` — 用户配置（customProviders, customModels, llmApiKey 等）
- `tasks` / `task_events` — 任务队列和执行日志
- `novel_promotion_*` — 短剧推广项目数据
- `character_appearances` — 角色外观

## 任务失败诊断与重试

### 从日志定位失败任务
```bash
docker logs waoowaoo-app --tail 200 2>&1 | grep -E "ERROR|failed|worker\.failed"
```

关键日志字段：
- `taskId` / `jobId` — 任务 ID
- `taskType` — 任务类型（`script_to_storyboard_run`、`image_character` 等）
- `errorMessage` / `errorCode` — 失败原因
- `targetType` / `targetId` — 关联的实体

### 查任务详情
```bash
docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 waoowaoo -e \
  "SELECT id, type, status, targetType, targetId, episodeId, errorMessage \
   FROM tasks WHERE projectId='<PROJECT_ID>' ORDER BY createdAt DESC LIMIT 10;"
```

### 重试方式（按推荐度排序）

1. **Bull Board（推荐）**：`http://localhost:13010/admin/queues` → 对应队列 → `Failed` → 找到 job → **Retry**

2. **前端 UI**：不同任务类型对应不同界面位置：
   - `script_to_storyboard_run`：分镜(Storyboard)标签 → 找到对应集 → 刷新/重新生成

3. **MySQL 重置**（仅对 BullMQ 自动重试的任务有效，`attempts` 耗尽则无效）：
   ```bash
   docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 waoowaoo -e \
     "UPDATE tasks SET status='queued', attempt=0, errorCode=NULL, errorMessage=NULL \
      WHERE id='<TASK_ID>';"
   ```

### 常见任务失败类型

| 错误信息 | 原因 | 解决 |
|---------|------|------|
| `voice line N has invalid matchedPanel reference` | AI 台词分析输出中某句的 `panelIndex` 为 null | 重跑（模型偶尔输出不完整） |
| `OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND` | API 返回字段名与模板不匹配 | 见上方图片生成模板不匹配章节 |
| `task locale is missing` | 请求未携带 locale | 前端 bug，刷新页面重试 |

### ⚠️ 不要手动操作 BullMQ Redis Key

直接修改 BullMQ 的 Redis 数据结构（`bull:waoowaoo-text:<jobId>` 哈希、wait/completed 有序集合）会导致 worker 报 `WRONGTYPE` 错误并无限重试，只能重启容器恢复。始终通过 Bull Board UI 操作。

## 内容导出（含图片 + 文本）

全部内容存储在 MinIO（图片）和 MySQL（文本）。导出后再删除软件。

### 图片导出（MinIO → 本地）
```bash
# 列出所有文件
docker exec waoowaoo-minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker exec waoowaoo-minio mc ls --recursive local/waoowaoo/

# 导出到 MinIO 容器内 /tmp
docker exec waoowaoo-minio mc cp --recursive local/waoowaoo/ /tmp/waoowaoo_export/

# 拷贝到 Windows 主机
docker cp waoowaoo-minio:/tmp/waoowaoo_export/images/. "/mnt/d/目标文件夹/"
```

### 文本导出（MySQL → txt）
```bash
docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 --default-character-set=utf8mb4 waoowaoo -N -e "
SELECT CONCAT('=== 项目：', p.name, ' ===') FROM projects p JOIN novel_promotion_projects np ON np.projectId = p.id;
SELECT '';
SELECT '--- 角色 ---';
SELECT CONCAT(c.name, ' | 形象:', ca.changeReason, ' | 描述:', COALESCE(ca.description,'无'))
FROM novel_promotion_characters c
JOIN character_appearances ca ON ca.characterId = c.id;
SELECT '';
SELECT '--- 剧本 ---';
SELECT CONCAT('第', episodeNumber, '集: ', name, CHAR(10), COALESCE(novelText, '无内容'))
FROM novel_promotion_episodes ORDER BY episodeNumber;
" > "/mnt/d/目标文件夹/项目内容.txt"
```

## 完整删除

```bash
cd /mnt/d/waoowaoo
docker compose down -v          # 停止容器 + 删除数据卷
rm -rf /mnt/d/waoowaoo          # 删除项目目录
docker rmi ghcr.io/saturndec/waoowaoo:latest  # 删除镜像
docker image prune -f           # 清理悬空镜像
```

## 剧本过长的坑

`novel_promotion_episodes.novelText` 默认 `TEXT`（64KB），长剧本会截断。需改为 `MEDIUMTEXT`（16MB）：
```sql
ALTER TABLE novel_promotion_episodes MODIFY novelText MEDIUMTEXT;
```

## 参考文件
- `references/api-key-decrypt.md` — API Key 解密脚本与参数
- `references/api-image-template-debug.md` — 图片模板不匹配诊断与修复
- `references/character-prompt-structure.md` — 角色图片 Prompt 结构、固定后缀、画风选项
- `references/toonflow-auth-middleware.md` — Express 认证中间件与静态文件路径豁免（Toonflow 案例）

```
# 图片生成错误
OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND

# 文字处理正常
llm.raw.output
worker.waoowaoo-text

# 图片 Worker
worker.waoowaoo-image
image source generation started

# 模板相关
generateImageViaOpenAICompatTemplate
compatMediaTemplate
```
