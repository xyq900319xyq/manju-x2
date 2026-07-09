# Express Authentication Middleware Pitfalls

## Static File Routes Blocked by Auth Middleware

**Symptom:** Frontend returns `{"message":"未提供token"}` or similar auth error when loading static assets (HTML/JS/CSS).

**Root cause pattern:** Authentication middleware intercepts requests even when placed AFTER `express.static()` in the middleware chain, because route matching happens before middleware execution order matters for non-matched routes.

### Investigation Steps (Phase 1)

1. **Check middleware order in app setup:**
   ```typescript
   app.use(express.static(path.join(__dirname, "../web")));
   app.use(authMiddleware); // ← Placed after static, but still intercepts
   ```

2. **Read the auth middleware whitelist logic:**
   ```typescript
   // Example from Toonflow src/app.ts
   app.use((req, res, next) => {
     if (req.path === "/api/login/login") return next(); // ← Incomplete whitelist
     const token = req.headers.authorization?.split(" ")[1];
     if (!token) return res.status(401).json({ message: "未提供token" });
     // ... JWT verification
   });
   ```

3. **Verify static file route pattern:**
   - Check what path prefix the static files use (e.g., `/web/`, `/public/`, `/assets/`)
   - Confirm the auth middleware does NOT whitelist that prefix

### Root Cause

Express middleware with `app.use()` (no path argument) runs for ALL requests, regardless of placement relative to `express.static()`. The whitelist check must explicitly allow static file paths.

### Fix Pattern

Add static file path prefix to the whitelist condition:

```typescript
app.use((req, res, next) => {
  // Whitelist: login endpoint + static file routes
  if (req.path === "/api/login/login" || req.path.startsWith("/web/")) {
    return next();
  }
  
  const token = req.headers.authorization?.split(" ")[1];
  if (!token) return res.status(401).json({ message: "未提供token" });
  // ... rest of auth logic
});
```

### Verification

1. Rebuild the application (`yarn build` / `npm run build`)
2. Restart the server (kill old process, start new one)
3. Access static files directly (e.g., `http://localhost:PORT/web/index.html`)
4. Confirm no auth error, page loads correctly

### Related Patterns

- **API-only auth:** If static files should always be public, whitelist by checking `req.path.startsWith("/api/")` and only authenticate API routes
- **Separate routers:** Use `express.Router()` with path-specific middleware instead of global `app.use()`
- **Middleware ordering:** For route-specific middleware, use `app.use("/api", authMiddleware, apiRouter)` instead of global middleware

### Real-World Example

**Toonflow-app** (https://github.com/HBAI-Ltd/Toonflow-app):
- Static files served from `/web/` via `express.static(path.join(__dirname, "../web"))`
- Auth middleware at line 108 of `src/app.ts` only whitelisted `/api/login/login`
- Fix: Added `|| req.path.startsWith("/web/")` to whitelist condition
- Result: Login page loads correctly, auth still enforced for API routes
