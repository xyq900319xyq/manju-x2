# Chuangwei.cyou API Proxy: Endpoint & Auth Overrides

Discovered during debugging of 魔因漫创 (moyin-creator) S-class nine-grid board generation.

## Detection
```javascript
const isChuangweiProxy = /chuangwei\.cyou/i.test(normalizedBase);
```

## Endpoint Overrides

| Aspect | Standard OpenAI Path | Chuangwei Proxy |
|--------|---------------------|-----------------|
| Image submit | `{base}/v1/images/generations` | `{base}/api/ai/image` |
| Task poll | `{base}/v1/tasks/{id}` | `{base}/api/ai/task/{id}?provider=memefast&type=image&apiKey={key}` |
| Auth | `Authorization: Bearer {key}` header | `apiKey` field in JSON body |
| Content-Type | `application/json` (or multipart) | `application/json` |

## Request Body (Chuangwei)
```json
{
  "prompt": "...",
  "negativePrompt": "...",
  "aspectRatio": "16:9",
  "apiKey": "sk-...",
  "provider": "memefast",
  "referenceImages": ["data:image/png;base64,..."]
}
```

Key differences from standard:
- `negative_prompt` → `negativePrompt` (camelCase)
- `aspect_ratio` → `aspectRatio`
- `image_urls` → `referenceImages`
- No `model` field (provider handles model routing)

## Response Handling
- **Direct**: `{imageUrl: "...", status: "completed"}` — rare, when generation is instant
- **Async**: `{taskId: "uuid", status: "processing"}` — common, triggers polling

## Polling Loop
```javascript
for (let attempt = 0; attempt < 90; attempt++) {
  const pollResp = await fetch(
    `${normalizedBase}/api/ai/task/${data.taskId}?provider=memefast&type=image&apiKey=${encodeURIComponent(apiKey)}`
  );
  if (!pollResp.ok) continue;
  const pollData = await pollResp.json();
  if (pollData.status === "completed" && pollData.result?.url) {
    return { imageUrl: pollData.result.url, taskId: data.taskId };
  }
  if (pollData.status === "failed") throw new Error(pollData.error || "Task failed");
  await new Promise(r => setTimeout(r, 2000));
}
```

## Timeout
```javascript
const submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 18e4;
// 120s for memefast models, 180s default fallback
const submitTimeoutMessage = `拼图生成请求超时（${Math.round(submitTimeoutMs / 1e3)}秒），请检查网络后重试`;
```

## local-image:// → data: URL Conversion

The proxy cannot access `local-image://` file references. Inject conversion before the fetch:

```javascript
if (isChuangweiProxy && requestBody.image_urls && requestBody.image_urls.length > 0) {
  const converted = await Promise.all(requestBody.image_urls.map(async (url) => {
    if (url && (url.startsWith("local-image://") || url.startsWith("local-video://"))) {
      try {
        const dataUrl = await materializeImageSourceToDataUrl(url);
        console.log("[GridImageAPI] Converted local ref:", url.substring(0, 40), "-> dataUrl length:", dataUrl?.length || 0);
        return dataUrl || url;
      } catch(e) {
        console.warn("[GridImageAPI] Failed to convert local ref:", url.substring(0, 40), e.message);
        return url;
      }
    }
    return url;
  }));
  requestBody.image_urls = converted;
}
```

## Reference Image Transport Policy (Silent Drop Pitfall)

The `processReferenceImagesForModel` function filters references BEFORE they reach `submitGridImageRequest`:

| Policy ID | Transport | Trigger | Behavior |
|-----------|-----------|---------|----------|
| `gemini_image_inline` | `inline` | Gemini image models | Converts to base64 data URL |
| `default_hosted` | `hosted` | All other models | Uploads to image host, uses hosted URL |

For `hosted` policy with `local-image://` URLs:
1. `local-image://` is not `http://` → skips the hosted upload branch
2. Falls through to `readReferenceAsDataUrl(rawRef)` → calls `readImageAsBase64`
3. If file doesn't exist on disk → returns `null`
4. `processReferenceImagesForModel` does `if (!base64Ref) continue` → **silently skipped**
5. Result: `referenceImages=[]` sent to API

**This means**: Even if character 定妆照 exist as records in the app's database, if the underlying PNG files are missing from the `media/` directory, all character references will be silently dropped and the generated images won't match character designs.
