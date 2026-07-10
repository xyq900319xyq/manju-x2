# waoowaoo 图片生成数量控制 — 完整代码链路

## 关键文件

| 文件 | 作用 |
|------|------|
| `/app/src/lib/image-generation/count.ts` | 默认值、范围、normalize 函数 |
| `/app/src/lib/image-generation/count-preference.ts` | localStorage 读写 |
| `/app/src/lib/image-generation/use-image-generation-count.ts` | React hook |
| `/app/src/lib/workers/handlers/character-image-task-handler.ts` | 后端实际执行生成循环 |
| `/app/src/app/[locale]/workspace/[projectId]/modes/novel-promotion/components/assets/CharacterSection.tsx` | onRegenerate 路由逻辑 |
| `/app/src/app/[locale]/workspace/[projectId]/modes/novel-promotion/components/assets/character-card/CharacterCard.tsx` | UI 触发 |
| `/app/src/lib/query/mutations/character-image-ops-mutations.ts` | API 调用 |

## CharacterSection.tsx 中的关键逻辑（行 329-353）

```ts
onRegenerate={(count) => {
    const imageUrls = appearance.imageUrls || []
    const validImageCount = imageUrls.filter(url => !!url).length

    if (validImageCount === 1) {
        // 只有 1 张有效图 → 重新生成单张（1 个请求）
        const selectedIndex = appearance.selectedIndex ?? 0
        void onRegenerateSingle(character.id, appearance.id, selectedIndex)
    } else {
        // 0 张或 2+ 张 → 整组重新生成（count 个请求）
        void onRegenerateGroup(character.id, appearance.id, count)
    }
}}
```

## CharacterCard.tsx 中的触发点

**单图 compact 模式**：刷新按钮调用 `onRegenerate()` — **无 count 参数**

**多图 selection 模式**：重新生成按钮调用 `onRegenerate(generatedImageCount)` — 传已有图片数

## character-image-task-handler.ts 中的生成循环

```ts
const count = normalizeImageGenerationCount('character', payload.count)  // 默认 3
const indexes = singleIndex !== undefined
    ? [Number(singleIndex)]                           // 单张：只生成 1 个
    : Array.from({ length: count }, (_v, i) => i)     // 否则：生成 count 个

for (let i = 0; i < indexes.length; i++) {
    const prompt = artStyle 
        ? `${addCharacterPromptSuffix(raw)}，${artStyle}` 
        : addCharacterPromptSuffix(raw)
    const imageKey = await generateProjectLabeledImageToStorage(...)  // 每次 1 次 API 调用
}
```

## 修改默认值的正确方式（生产模式）

生产模式（`next start`）下源码修改不生效，必须同时改源码和所有编译产物：

```bash
# 1. 改源码
docker exec waoowaoo-app sed -i 's/defaultValue: 3/defaultValue: 1/g' /app/src/lib/image-generation/count.ts

# 2. 改所有编译产物（.next/ 下的 server chunks + static chunks）
docker exec waoowaoo-app sh -c 'for f in $(grep -rl "defaultValue:3" /app/.next/ 2>/dev/null); do
  sed -i "s/defaultValue:3/defaultValue:1/g" "$f"
  echo "Fixed: $f"
done'

# 3. 验证无遗漏
docker exec waoowaoo-app sh -c 'grep -rl "defaultValue:3" /app/.next/ | wc -l'  # 应为 0

# 4. 重启
cd /mnt/d/waoowaoo && docker compose restart app
```

典型受影响文件（9 个）：
- `/app/.next/server/app/api/novel-promotion/[projectId]/character/route.js`
- `/app/.next/server/app/api/novel-promotion/[projectId]/regenerate-group/route.js`
- `/app/.next/server/app/api/novel-promotion/[projectId]/location/route.js`
- `/app/.next/server/app/api/novel-promotion/[projectId]/reference-to-character/route.js`
- `/app/.next/server/app/api/asset-hub/locations/route.js`
- `/app/.next/server/app/api/asset-hub/reference-to-character/route.js`
- `/app/.next/server/app/api/asset-hub/characters/route.js`
- `/app/.next/server/chunks/9555.js`
- `/app/.next/server/chunks/3720.js`
- `/app/.next/static/chunks/1639-*.js`

注意：版本更新后 chunk 文件名可能变化，用 `grep -rl` 扫描比硬编码文件名更可靠。

Key: `image-count:character`
值: 1-6 的数字，由 `ImageGenerationInlineCountButton` 组件管理。

只在首次生成 (`onGenerate`) 时使用；刷新/重新生成 (`onRegenerate`) 不读 localStorage。
