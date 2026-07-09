# waoowaoo Docker Deployment (2026-05-21 Session)

Full deployment reference for waoowaoo (AI short-drama/comic tool) on Windows via Docker Desktop.

## Architecture

| Service | Image | Container | Port |
|---------|-------|-----------|------|
| MySQL 8.0 | `mysql:8.0` | `waoowaoo-mysql` | `13306:3306` |
| Redis 7 | `redis:7-alpine` | `waoowaoo-redis` | `16379:6379` |
| MinIO | `minio/minio` | `waoowaoo-minio` | `19000:9000` / `19001:9001` |
| App (Next.js) | `ghcr.io/saturndec/waoowaoo:latest` | `waoowaoo-app` | `13000:3000` / `13010:3010` |

**Access:** `http://localhost:13000` (app), `http://localhost:13010` (Bull Board)

## Deploy Steps

### 1. Create docker-compose.yml

Project dir: `D:\waoowaoo\docker-compose.yml`

Key config:
- MySQL: password `waoowaoo123`, database `waoowaoo`, `mysql_native_password`
- MinIO: `minioadmin / minioadmin`
- App depends on MySQL/Redis/MinIO healthy, runs `prisma db push` on startup
- App listens on 3000 internally, mapped to 13000 externally

### 2. GHCR Proxy (China)

```powershell
docker pull ghcr.dockerproxy.com/saturndec/waoowaoo:latest
docker tag ghcr.dockerproxy.com/saturndec/waoowaoo:latest ghcr.io/saturndec/waoowaoo:latest
docker pull mysql:8.0
docker pull redis:7-alpine
docker pull minio/minio:RELEASE.2025-02-28T09-55-16Z
```

### 3. Start

```powershell
cd D:\waoowaoo
docker compose up -d
```

Wait for Prisma init (~30s), then verify: `Invoke-WebRequest http://localhost:13000` → 200 OK.

## Common Issues

### TEXT column overflow

**Symptom:** Long scripts get truncated on save.
**Fix:** Expand `novelText` to MEDIUMTEXT:

```powershell
docker exec waoowaoo-mysql mysql -uroot -pwaoowaoo123 waoowaoo -e "ALTER TABLE novel_promotion_episodes MODIFY novelText MEDIUMTEXT;"
```

### Image generation: OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND

**Symptom:** Character image generation fails after ~56 seconds.
**Location:** `template-image.ts:121` — `generateImageViaOpenAICompatTemplate`
**Root cause:** The API model (`gpt-image-2-reverse` via OpenAI Compat) returns output that doesn't contain the expected template format. waoowaoo's template approach expects the LLM to return text with embedded image URLs.
**The API request/response logging for image generation is NOT captured in standard `llm.raw.input/output` logs** — the template code path bypasses normal logging. The text-processing pipeline (character analysis, script conversion) IS logged and shows correct API function.

**How to debug:**
```powershell
# Search logs for the error chain
docker logs waoowaoo-app 2>&1 | Select-String -Pattern 'TEMPLATE|generateImage|image source|OPENAI_COMPAT' -Context 0,2
```

### First boot logs

On first run, expect Prisma errors about missing tables (`P2021: The table 'tasks' does not exist`). These are transient — `prisma db push` runs after startup and creates all tables. The errors resolve on the next worker tick.

## Service Health Check

```powershell
docker compose ps
# All 4 containers should show (healthy)

docker logs waoowaoo-app --tail 20
# Should show: "✓ Ready", "Your database is now in sync", workers ready
```
