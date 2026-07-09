# API Request Interception (Runtime Capture)

To see exactly what prompts and images the software sends to APIs, inject `fetch` interception into the bundled JS and capture via a local HTTP server.

## Setup

1. Start a capture server on WSL:
```bash
python3 -c "
from http.server import HTTPServer, BaseHTTPRequestHandler
import json, time

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        ts = str(int(time.time()*1000))
        path = f'/mnt/d/moyinxiangmu/_api_{ts}.json'
        data = json.loads(body)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        if 'content' in data:
            for c in data['content']:
                if c.get('type') == 'text':
                    with open(f'{path}_text.txt', 'w', encoding='utf-8') as f:
                        f.write(c['text'])
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'ok')
    def log_message(self, *args): pass

HTTPServer(('0.0.0.0', 19999), H).serve_forever()
" &
```

2. Inject fetch interceptor into the asar bundled JS. Target pattern:
```javascript
body: JSON.stringify(requestBody)
```
Replace with:
```javascript
body: (()=>{try{fetch('http://127.0.0.1:19999',{method:'POST',body:JSON.stringify(requestBody)}).catch(function(){})}catch(e){}})() || JSON.stringify(requestBody)
```

3. The full extract-patch-repack flow (DO NOT use binary byte patching — it will corrupt the asar):
```bash
npx --yes @electron/asar extract app.asar /tmp/asar_extract/
# Edit /tmp/asar_extract/out/renderer/assets/index-*.js
npx --yes @electron/asar pack /tmp/asar_extract/ /tmp/app_patched.asar
cp /tmp/app_patched.asar "D:/path/to/app.asar"
```

## Pitfalls

- **DO NOT binary-patch the asar** (byte-level `data[pos:pos+N] = new_bytes`). Slight length mismatches or encoding issues silently corrupt the archive.
- **Always extract-patch-repack** — this is the only reliable method.
- **`require("fs")` won't work** in Electron renderer processes (context isolation). Use `fetch()` to a local server instead.
- The `ai-worker-*.js` may not contain the `body: JSON.stringify(requestBody)` pattern — focus on the main `index-*.js` renderer file.
- **Image generation (九宫格) uses multipart FormData**, not JSON — the `body: JSON.stringify` injection won't capture it. Use the generation log instead (`moyinxiangmu/logs/generation-requests-*.jsonl`).
- **Requests overwrite each other** if using a fixed filename — use timestamps or append mode.
- Kill the running process before replacing the asar (`taskkill.exe /F /IM moyin-creator.exe`).

## Alternative: Generation Log

The software has its own structured logging at `{workspace}/logs/generation-requests-YYYY-MM-DD.jsonl`. Entries include:
- `grid_image_submit_start`: model, operation (t2i/i2i), referenceImageCount, promptPreview (first 80 chars)
- `video_submit_start`: model, duration, endpointPath
- `video_submit_http_error`: status, errorTextPreview

The log includes `promptHash` but NOT the full prompt text. Use `promptPreview` for identification.
