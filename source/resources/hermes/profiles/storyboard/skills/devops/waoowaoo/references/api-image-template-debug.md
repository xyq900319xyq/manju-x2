# 图片生成模板调试：OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND

## 错误链路

```
image_character task → worker.waoowaoo-image
→ generateImageViaOpenAICompatTemplate (template-image.ts:121)
→ fetch(createRequest.endpointUrl, ...)
→ response.ok === true (HTTP 2xx)
→ 但 readTemplateOutputUrls / readJsonPath 没找到输出
→ throw OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND
```

## 模板结构

位于 `user_preferences.customModels` JSON 中的 `compatMediaTemplate`：

```json
{
  "version": 1,
  "mediaType": "image",
  "mode": "sync",
  "create": {
    "method": "POST",
    "path": "/images/generations",
    "contentType": "application/json",
    "bodyTemplate": {
      "model": "{{model}}",
      "prompt": "{{prompt}}"
    }
  },
  "response": {
    "outputUrlPath": "$.data[0].url",
    "outputUrlsPath": "$.data",
    "errorPath": "$.error.message"
  }
}
```

- 完整 URL = `baseUrl` + `create.path`（如 `https://chuangwei.cyou/v1/images/generations`）
- 模板期望 `$.data[0].url` 或 `$.data` 数组中有 url 字段
- `readTemplateOutputUrls()` 接受 `{url: "..."}` 对象或纯 URL 字符串

## 常见不匹配模式

### 模式 1：API 返回 b64_json 而非 url
```json
// API 实际返回
{"data": [{"b64_json": "iVBORw0KGgo..."}]}

// 模板期望
{"data": [{"url": "https://..."}]}
```
**症状**：HTTP 200 但报 `OUTPUT_NOT_FOUND`

### 模式 2：API 返回的 data 结构不同
```json
// 某些 API
{"data": {"url": "..."}}          // 非数组
{"images": [{"url": "..."}]}      // 不同字段名
{"output": ["https://..."]}       // 直接 URL 数组
```

### 模式 3：chat completions 返回内嵌图片
```json
{
  "choices": [{
    "message": {
      "content": "![image](data:image/png;base64,iVBOR...)"
    }
  }]
}
```
部分 API 的图片模型实际走 chat completions，返回 markdown 格式的 data URL。

## 诊断流程

```bash
# 1. 从数据库取模板和 provider
docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 -N -B waoowaoo \
  -e "SELECT customModels, customProviders FROM user_preferences WHERE userId='<id>';"

# 2. 解密 API key（参考 api-key-decrypt.md）

# 3. 直调 API
curl -s -X POST "$BASE_URL/images/generations" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"MODEL","prompt":"test prompt"}'

# 4. 对比返回格式与模板期望
```

## 修复方案

| 方案 | 操作 | 难度 |
|------|------|------|
| A | 加 `"response_format": "url"` 到 `bodyTemplate`（API 支持时 b64_json→url） | 低 |
| B | 改模板 `outputUrlPath` 为 `$.data[0].b64_json` + 代码中处理 b64→data URL | 中 |
| C | 改走 chat completions 端点（`/v1/chat/completions`）解析 markdown 图片 | 中 |
| D | 换 API provider 为原生支持 DALL-E 格式的 | — |
| E | bodyTemplate 硬编码 `"size": "1792x1024"`（当需要改比例时，绕过编译代码常量内联限制） | 低 |

### 方案 A 详解（已验证可行）
1. 解密 API key（参考 `api-key-decrypt.md`）
2. curl 测试 API 是否支持 `response_format: url`：
   ```
   curl -X POST <baseUrl>/images/generations -H "Authorization: Bearer <key>" \
     -d '{"model":"...","prompt":"test","response_format":"url"}'
   ```
3. 若返回 `{"data":[{"url":"data:image/png;base64,..."}]}`，更新数据库模板
4. 用 Python mysql.connector 直连（避 shell 转义）更新 `customModels` JSON
5. `docker restart waoowaoo-app`

### 方案 E 详解（比例修改专用）
编译代码中 `'3:2'` 既是比例常量值又是映射表键名，不能盲目全局替换。最可靠方式：在 bodyTemplate 直接写死目标 size：
```json
{ "model": "{{model}}", "prompt": "{{prompt}}", "response_format": "url", "size": "1792x1024" }
```
