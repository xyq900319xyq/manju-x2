# 漫剧助手X-2 v1.1.1 — 校验放宽 + 更新源限速绕过

## 安装包

- 文件名: `漫剧助手X-2_v1.1.1_Setup.exe`
- 大小: ~91 MB

## 重点修复

### 1. 保存设置不再卡 api_key 缺失
v1.1.0 校验 active config 必填字段时,LLM + 视频 API 都强制要求 api_key 等字段都填齐才能保存。用户反馈「**没有 API 也能保存**」— v1.1.1 把校验完全下放到调用时:

- 保存时**不**再因缺字段拒绝
- 真的去调 LLM/生图/视频 API 时,如果发现缺字段再报错
- 用户可以分批填,先保存一部分先跑流程

### 2. 「检查更新」不再因 GitHub rate limit 失败
v1.1.0 的更新检查走 `api.github.com`,60 次/小时/IP 限速。少量用户测试时就把 IP 桶打满,弹 `HTTP 403 rate limit exceeded`。

v1.1.1 改双源:
1. **优先** `raw.githubusercontent.com/.../release/update.json`(静态文件,**无限速**)
2. 失败再降级到 GitHub API
3. 两个都失败才报错

build 时自动把当前 release 写进 `release/update.json`,推到 main 分支即可,GitHub 自动服务。

## 改动

- `ui/settings_dialog.py` `_on_save`:移除 active config 字段必填校验(只校验 active id 在 configs 里能找得到)
- `core/updater.py`:
  - 新增 `fetch_update_json()` 函数(拉静态 update.json)
  - `fetch_latest_release()` 改成双源:update.json → GitHub API 兜底
  - 新增 `UPDATE_JSON_URL` 常量(`https://raw.githubusercontent.com/xyq900319xyq/manju-x2/main/release/update.json`)
- `release/update.json`:每次 build 自动重写
- 版本号 1.1.0 → 1.1.1 (main.py 2 处 + .iss 1 处)

## 升级

覆盖安装。设置、数据、模型配置不丢。
