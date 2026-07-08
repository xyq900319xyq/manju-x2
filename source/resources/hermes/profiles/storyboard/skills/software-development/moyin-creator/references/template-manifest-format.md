# Template Manifest Format (v0.2.8+)

## Where it's used

- "GPT Image 2 模板库根目录" — Settings panel field
- "Seedance 2.0 模板库根目录" — Settings panel field

Both use the same manifest.json format but in separate directories.

## Validation logic (from asar analysis)

```
resolveGptImageTemplateLibraryRoot(inputPath):
  → normalized = normalizePath(inputPath.trim())
  → manifestPath = path.join(normalized, "manifest.json")
  → return { libraryRoot: normalized, manifestPath }

validateGptImageTemplateRoot(rootPath):
  → resolved = resolveGptImageTemplateLibraryRoot(rootPath)
  → if !fs.existsSync(resolved.manifestPath) → status: "missing"
  → manifest = JSON.parse(fs.readFileSync(resolved.manifestPath))
  → if !Array.isArray(manifest.prompts) → throw "prompts must be an array"
  → count prompts, count assets, count missing assets
  → return { status: "ok", totalCount, assetCount, missingAssetCount, generatedAt, sourceUrl }
```

## Status values

| Status | Label | Condition |
|--------|-------|-----------|
| `"ok"` | 已连接 | manifest.json exists + prompts is array |
| `"missing"` | 缺少目录 | manifest.json not found |
| `"invalid"` | 目录无效 | manifest.json exists but wrong format |
| `"unconfigured"` | 未配置 | No path set |

## Prompt object fields (full reference)

```
prompt.id            → templateId (stable identifier)
prompt.slug          → URL-friendly slug, used for folder naming
prompt.title         → Display name
prompt.prompt        → Raw prompt text with {argument name=...} placeholders
prompt.translatedPrompt → Translated prompt variant
prompt.description   → Searchable description
prompt.model         → Default: "gpt-image-2"
prompt.locale        → e.g. "zh-CN"
prompt.language      → e.g. "中文"
prompt.category      → If not set, auto-inferred by inferGptImageTemplateCategory()
prompt.author.name   → Author display
prompt.author.link   → Author URL
prompt.pageUrl       → Source page URL
prompt.sourceLink    → Source link
prompt.sourcePublishedAt → ISO date
prompt.thumbnailUrl  → Remote thumbnail URL (fallback if no local asset)
prompt.referenceImageUrls → Array of remote reference image URLs
prompt.mediaImageUrls → Array of remote media image URLs
prompt.videoUrls     → Array of remote video URLs
prompt.assets[]      → Array of asset objects
prompt.assets[].kind → "thumbnail" | "reference-image" | "media-image"
prompt.assets[].fileName → Local filename (resolved relative to root or <id>-<slug>/)
prompt.assets[].url  → Remote URL
```

## Asset resolution

```
resolveGptImageTemplateAssetPath(libraryRoot, prompt, fileName):
  → try: path.join(libraryRoot, fileName)
  → try: path.join(libraryRoot, `${id}-${slug}`, fileName)
  → return null if neither exists
```

## Category inference

```
inferGptImageTemplateCategory(prompt):
  Text = title + description + prompt + translatedPrompt + slug + author.name
  Checks (in order):
    1. /app|ui|ux|web|website|.../i  → "App / 网页设计"
    2. /infographic|diagram|chart|.../i → "信息图 / 教育视觉图"
    3. /poster|flyer|cover|.../i → "海报 / 传单"
    4. /portrait|avatar|headshot|.../i → "个人资料 / 头像"
    5. /social|x post|twitter|.../i → "社交媒体帖子"
    6. /comic|manga|storyboard|.../i → "漫画 / 故事板"
    default → "其他"
```

## Argument placeholders

Templates can include `{argument name="param_name" default="value"}` placeholders. The software parses these and presents input fields to the user before generation.

## Legacy format (incompatible)

The old template data in `模版库/catalog/` uses:
- `template_library.sqlite3` — SQLite database
- `templates.jsonl` — JSONL export
- `templates.csv` — CSV export
- Fields: `template_id`, `display_name`, `description`, `media_combo`, `template_category`, `theme_tags`, `slot_signature`, `reference_slot_count`, `image_slot_count`, `video_slot_count`, `voice_slot_count`, `image_asset_count`, `video_asset_count`, `audio_asset_count`

This format is NOT compatible with the new manifest.json format. No automatic migration exists.
