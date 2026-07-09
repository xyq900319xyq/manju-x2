# API Request Capture Methods for Moyin Creator

## Context
When debugging prompt compilation or API integration issues, you need to capture the exact request body (model, messages, temperature, max_tokens) and prompts (system + user) that 魔因 sends to the API endpoint.

## Method 1: Source Code Instrumentation (RECOMMENDED)

**When to use**: You have the TypeScript source and can rebuild.

**Advantages**:
- Captures full request body including all headers and options
- Works with HTTPS without certificate issues
- No proxy configuration needed
- Logs written directly to disk with full fidelity

**Implementation**:

1. **Edit `src/lib/script/script-parser.ts`** at line ~307 (inside `callChatAPI` function, right after the `body` object is constructed):

```typescript
const body: Record<string, any> = {
  model: modelName,
  messages: [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: userPrompt },
  ],
  temperature: options.temperature ?? 0.7,
  max_tokens: effectiveMaxTokens,
};

// 智谱推理模型 (GLM-4.7/4.5 等) 支持通过 thinking.type 关闭深度思考
if (options.disableThinking) {
  body.thinking = { type: 'disabled' };
  console.log('[callChatAPI] 已关闭深度思考 (thinking: disabled)');
}

// === 🔍 DEBUG: 记录完整请求体到文件 ===
try {
  const fs = require('fs');
  const logPath = 'D:\\魔音提示词\\api_requests.jsonl';
  const logEntry = {
    timestamp: new Date().toISOString(),
    url,
    headers: { ...headers, Authorization: 'Bearer ***' },
    body,
  };
  fs.appendFileSync(logPath, JSON.stringify(logEntry, null, 2) + '\n---\n');
  console.log('[DEBUG] 请求已记录到:', logPath);
} catch (e) {
  console.warn('[DEBUG] 日志写入失败:', e);
}

const response = await corsFetch(url, {
  method: 'POST',
  headers,
  body: JSON.stringify(body),
});
```

2. **Run in development mode** (Windows):

```powershell
cd D:\path\to\moyin-creator-source
npm install   # if not already done
npm run dev
```

Or on WSL (will fail to launch Electron due to missing libs, but compiles the code):
```bash
cd /home/administrator/moyin-creator
npm run dev
```

3. **Trigger the action** (import script, generate character, etc.) in the running app.

4. **Read the log**:
```
D:\魔音提示词\api_requests.jsonl
```

Each entry is a JSON object with:
- `timestamp`: ISO 8601
- `url`: Full API endpoint
- `headers`: Request headers (Authorization redacted)
- `body`: Complete request body including `model`, `messages` (system + user prompts), `temperature`, `max_tokens`, `thinking`

**Pitfalls**:
- **WSL cannot launch Electron** due to missing `libnss3.so` and other GUI dependencies. Compile on WSL, then copy `out/` to Windows and run there, OR run `npm run dev` directly on Windows (requires Node.js installed on Windows).
- **Path must use double backslashes** in the TypeScript string: `'D:\\魔音提示词\\api_requests.jsonl'`
- **Log file grows unbounded** — clear it between test runs or use a rotating log library.

---

## Method 2: System-Wide HTTPS Interception (for running processes)

**When to use**: 魔因 is already running and actively working — you cannot restart it, but you need to capture API requests in real time.

**Recommended tool**: **Fiddler Classic** (Windows) or **Proxyman** (cross-platform).

**Why this works**:
- Installs a trusted root CA certificate into Windows certificate store
- Intercepts all HTTPS traffic system-wide, including from Electron apps
- Decrypts, logs, and re-encrypts requests transparently
- No app restart or source modification needed

**Steps (Fiddler Classic)**:

1. **Download and install**: [https://www.telerik.com/fiddler/fiddler-classic](https://www.telerik.com/fiddler/fiddler-classic)

2. **Enable HTTPS decryption**:
   - Tools → Options → HTTPS tab
   - Check "Capture HTTPS CONNECTs"
   - Check "Decrypt HTTPS traffic"
   - Click "Yes" to trust the Fiddler root certificate

3. **Start capture**: Press F12 or click "Capturing" in the bottom-left

4. **Trigger the action** in 魔因 (import script, generate character, etc.)

5. **Filter requests**: In the left pane, look for `chuanggwei.cyou` or `memefast.top` hosts

6. **Inspect request**:
   - Click the request → Inspectors tab → Raw or JSON
   - Request body shows `model`, `messages` (system + user prompts), `temperature`, `max_tokens`

**Pitfalls**:
- **Antivirus may block Fiddler's CA cert install** — temporarily disable AV or whitelist Fiddler
- **Electron apps with certificate pinning** may refuse to connect — 魔因 does NOT pin certificates, so this works
- **Large request bodies** (e.g., base64-encoded images) can make the UI slow — use AutoResponder rules to filter
- **Fiddler captures ALL system traffic** — use Filters (Hosts → Show only: `chuanggwei.cyou`) to reduce noise

**Alternative: mitmproxy (Linux/WSL)**

If you prefer CLI and are on WSL:

1. Install: `pip3 install mitmproxy` (requires interactive terminal or `sudo` access)
2. Start: `mitmproxy -p 8888 --set confdir=~/.mitmproxy`
3. Configure Windows system proxy: `127.0.0.1:8888`
4. Install CA cert: `~/.mitmproxy/mitmproxy-ca-cert.cer` → Windows Trusted Root
5. Trigger action in 魔因
6. Press `i` in mitmproxy to inspect requests

**Result**: Works reliably for 魔因 because it respects system proxy settings and does not pin certificates.

---

## Method 3: HTTP Proxy (NOT RECOMMENDED for HTTPS APIs)

**When to use**: You cannot modify source code, cannot install Fiddler, and the API uses plain HTTP.

**Why it fails for 魔因**:
- 魔因's API endpoints (`chuanggwei.cyou`, `memefast.top`) use **HTTPS**
- Simple Python proxy cannot decrypt HTTPS without installing a CA certificate
- Requires the same CA cert setup as mitmproxy but with less tooling support

**If you must try it anyway**: See Method 2 (mitmproxy) — it's the same approach but with better tooling.

**Result**: Usually fails because you need CA cert trust, which requires the same setup as Fiddler/mitmproxy.

---

## Method 4: Runtime.db Post-Mortem (PARTIAL DATA ONLY)

**When to use**: Task already completed, you just need to see which model/provider was used.

**Limitations**: Does NOT capture the actual prompt text — only metadata.

**Steps**:

1. Find the workspace:
```powershell
cat "$env:APPDATA\Roaming\魔因漫创-profiles\default-*\storage-config.json"
```

2. Open `{workspace}/studio-run/runtime.db` with SQLite:
```bash
sqlite3 /mnt/d/path/to/workspace/studio-run/runtime.db
```

3. Query recent tasks:
```sql
SELECT id, category, label, provider, model, status, created_at, payload_json
FROM studio_run_tasks
ORDER BY created_at DESC
LIMIT 10;
```

4. Extract `payload_json` for a specific task:
```sql
SELECT payload_json FROM studio_run_tasks WHERE id = 'task_xxx';
```

**What you get**:
- `provider`, `model` (e.g., `"openai"`, `"gpt-4o"`)
- `category` (e.g., `"script_analysis"`, `"character_generation"`)
- `payload_json` may contain input parameters but **NOT the compiled prompt text**

**What you DON'T get**:
- The actual `systemPrompt` and `userPrompt` strings sent to the API
- Request headers, temperature, max_tokens (unless stored in `payload_json`, which is inconsistent)

---

## Recommended Workflow

1. **For running processes that cannot be restarted**: Use **Method 2** (Fiddler/mitmproxy system-wide HTTPS interception). Install Fiddler on Windows, enable HTTPS decryption, trigger the action, inspect captured requests.

2. **For active development/debugging**: Use **Method 1** (source instrumentation). Modify `script-parser.ts`, run `npm run dev` on Windows, trigger the action, read `D:\魔音提示词\api_requests.jsonl`.

3. **For post-mortem analysis**: Use **Method 4** (runtime.db) to see which tasks ran and with which provider/model.

4. **Avoid Method 3** unless you have a specific reason and the API is plain HTTP.

---

## Common Pitfall: "Restart Required" Assumption

**Symptom**: User says "魔因在工作，你想办法" but you keep suggesting solutions that require restarting the app (source modification + rebuild, switching to dev mode, asar patching + restart).

**Root cause**: Methods 1, 3, and direct asar patching all require restarting the app to load modified code. This is unacceptable when the user has active work in progress (剧本导入 in progress, generation queue running, unsaved state).

**Correct approach**: When the user explicitly states the app is running and cannot be closed, **immediately jump to Method 2** (Fiddler/mitmproxy). Do NOT cycle through restart-required approaches first.

**Recognition signals**:
- "魔因在工作" / "魔因正在运行"
- "不能关闭" / "不能重启"
- "之前不是做过这个吗，现在你怎么不会了？" (frustration with repeated failed approaches)
- User has already triggered the action (e.g., "魔因之前已经导入剧本了") — the data is in flight, cannot restart to capture it retroactively

**Action**: Acknowledge the constraint, recommend Fiddler, provide installation link and 5-step setup, estimate 5-10 minutes to first capture.

---

## Feature Key Routing

All 12 steps of script import use the same feature key: **`script_analysis`**. This is routed via `src/lib/ai/feature-router.ts` → `callFeatureAPI()` → `callChatAPI()`.

To see which model is bound to `script_analysis`:
- Open 魔因 → Settings → Service Mapping (服务映射)
- Find `script_analysis` row
- The bound provider/model is shown there

The actual API call goes through:
```
callFeatureAPI('script_analysis', systemPrompt, userPrompt, options)
  ↓
getFeatureConfig('script_analysis')  // reads from Zustand store
  ↓
callChatAPI(systemPrompt, userPrompt, { apiKey, baseUrl, model, ... })
  ↓
fetch(`${baseUrl}/v1/chat/completions`, { method: 'POST', body: JSON.stringify(body) })
```

The `body` object at the final step is what Method 1 captures.
