# Toonflow 认证中间件与静态文件服务

**项目**：[HBAI-Ltd/Toonflow-app](https://github.com/HBAI-Ltd/Toonflow-app)  
**架构**：Express.js + TypeScript，单体应用（非 Docker Compose）  
**问题场景**：认证中间件拦截静态文件请求导致 401 Unauthorized

---

## 问题表现

访问 `http://localhost:10588/web/index.html` 返回：
```json
{"message":"未提供token"}
```

预期：返回静态 HTML 文件

---

## 根本原因

**双重路径问题**：

1. **中间件执行顺序**：认证中间件在静态文件中间件之后注册，拦截了所有未豁免路径
2. **路径映射错误**：静态文件中间件挂载到根路径时，访问 `/web/index.html` 会在 `data/web/web/index.html` 查找（路径重复）

---

## 修复方案

**文件**：`src/app.ts`

### 修复 1：白名单豁免静态文件路径（第 108 行）

```typescript
// 修改前
if (req.path === "/api/login/login") return next();

// 修改后
if (req.path === "/api/login/login" || req.path.startsWith("/web/")) return next();
```

**作用**：让认证中间件跳过 `/web/*` 路径的 token 验证

### 修复 2：静态文件中间件挂载到子路径（第 95 行）

```typescript
// 修改前
app.use(express.static(webDir, { acceptRanges: false }));

// 修改后
app.use("/web", express.static(webDir, { acceptRanges: false }));
```

**作用**：
- 访问 `/web/index.html` → 在 `data/web/index.html` 查找（正确）
- 而非 `data/web/web/index.html`（错误）

---

## Express 中间件执行顺序原则

```javascript
app.use(express.static(...));        // 1. 静态文件优先
app.use((req, res, next) => {        // 2. 认证中间件在后
  if (whitelisted) return next();
  // 验证 token
});
```

**关键**：静态文件中间件应在认证中间件**之前**注册，或在认证中间件中显式豁免静态路径。

---

## 验证

```bash
# 启动服务
cd /mnt/d/Toonflow/Toonflow-app
yarn start

# 测试静态文件
curl -I http://localhost:10588/web/index.html
# 预期：200 OK, Content-Type: text/html

# 测试 API（需 token）
curl http://localhost:10588/api/some-endpoint
# 预期：{"message":"未提供token"}
```

---

## 适用场景

- Express.js 应用中认证中间件拦截静态资源
- 需要对特定路径豁免认证（登录页、公开资源、健康检查端点）
- 静态文件中间件路径映射错误（访问路径与文件系统路径不匹配）

---

## 相关模式

**路径白名单**（常见于 JWT 认证中间件）：
```typescript
const PUBLIC_PATHS = ['/api/login', '/api/register', '/health', '/web/'];

app.use((req, res, next) => {
  if (PUBLIC_PATHS.some(p => req.path.startsWith(p))) return next();
  // 验证 JWT
});
```

**静态文件子路径挂载**（避免路径冲突）：
```typescript
app.use('/static', express.static('public'));  // /static/logo.png → public/logo.png
app.use('/assets', express.static('dist'));    // /assets/app.js → dist/app.js
```
