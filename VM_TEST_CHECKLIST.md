# 漫剧助手X-2 干净 VM 测试清单

> **目标**: 在干净 Win10/11 VM(无 Python / 无 manju / 无 hermes)上测完整装/用/卸流程,确保用户拿 Setup.exe 装能用。
> **环境要求**: Win10 1809+ 或 Win11 22H2+,x64,4GB+ RAM,能联网。
> **预计耗时**: 45-90 分钟。
> **测试对象**: `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe` (91.18 MB)

---

## 测试前准备

### 准备 VM
- 用 VirtualBox / VMware / Hyper-V / Parallels(任选)建一个 VM
- 系统:Win10 22H2 或 Win11 23H2(干净 ISO)
- RAM: 4GB+ / 磁盘: 20GB+
- 装好后 **不要**装任何 dev 工具(Python / VSCode / Git)
- 截图保存(出问题用)

### 准备文件
1. 把 `漫剧助手X-2_v1.0.0_Setup.exe` 拷到 VM 桌面
2. 准备记事本(记录日志)

### 准备报告模板
- 复制下面的"测试报告模板"段,粘贴到记事本
- 每完成一项填一次,贴 issue 时用

---

## C5: 无 UAC 装(默认路径)

**目的**: 验证 Inno Setup `PrivilegesRequired=lowest` 起效,不弹 UAC。

### 步骤
1. 关闭所有杀毒软件实时防护(360 / Defender / 火绒,VM 里通常 Defender 默认开)
2. 双击 `漫剧助手X-2_v1.0.0_Setup.exe`
3. **观察**: UAC 是否弹窗?
4. 选默认安装目录 `C:\漫剧助手X-2\`(不修改)
5. 点 "下一步" → "安装"
6. 等待 30-60 秒
7. 看到 "安装完成" 弹窗
8. 勾选 "启动漫剧助手X-2"(先**不**点"完成",继续下面 C14)

### 验收
- ✅ UAC **没有**弹窗
- ✅ 装好文件 `C:\漫剧助手X-2\漫剧助手X-2.exe` 存在(约 0.x MB)
- ✅ 看到 "安装完成" 弹窗
- ✅ 桌面 / 开始菜单有 "漫剧助手X-2" 快捷方式

### 失败排查
- UAC 弹窗: 检查 `installer\漫剧助手X-2.iss` `PrivilegesRequired=lowest` 是否被覆盖
- 装不上: 看 `C:\Users\<user>\AppData\Local\Temp\Setup Log*.txt`

---

## C14: EXE 双击启动 + 弹 wizard

**目的**: 验证首次启动走 wizard 流程,DPAPI 加密 API key。

### 步骤
1. 接着 C5,点 "完成" 启动软件(或双击桌面图标)
2. **观察**: 看到 "漫剧助手X-2" 主窗口 + **API key 配置向导**(QWizard 6 步)
3. wizard 第 1 步: 欢迎页 - 看到 DPAPI 说明 + 4 字段提示
4. wizard 第 2 步: LLM API key - 填一个测试 key(随便,例如 `sk-test123`)
5. wizard 第 3 步: 图像 API key - 跳过(留空)
6. wizard 第 4 步: 视频 API key - 跳过
7. wizard 第 5 步: imgbb key - 跳过
8. wizard 第 6 步: 完成 - 看到摘要
9. 点 "完成"
10. 软件进主界面

### 验收
- ✅ wizard 6 步正常切换
- ✅ 第 1 步有 DPAPI 说明
- ✅ 第 2 步 LLM 必填校验起作用(留空不让下一步)
- ✅ wizard 关闭后 `C:\漫剧助手X-2\config\secrets.bin` 存在
- ✅ secrets.bin 是二进制非明文(`select-string` 找不到 `sk-test123` 字符串)
- ✅ 主界面没崩溃

### 验证 secrets.bin
```powershell
# PowerShell 验证加密生效
Test-Path "C:\漫剧助手X-2\config\secrets.bin"  # True
# 用 Get-Content 看不到明文 key
Get-Content "C:\漫剧助手X-2\config\secrets.bin" -Encoding Byte | Select-Object -First 4 | ForEach-Object { "{0:X2}" -f $_ }
# 输出应是 DPAPI 密文(随机字节),不是明文 "sk-test"
```

### 失败排查
- wizard 没弹: 检查 `secrets.bin` 是否已存在(存在就不弹了)
- 崩溃: 看 `C:\漫剧助手X-2\logs\manju-最新.log`
- DPAPI 失败: 看 logs 搜 "DPAPI"

---

## 额外: 创建项目 + 生成分镜(可选,3-5 分钟)

**目的**: 端到端跑一次核心功能(用测试 API key 可能失败,但能看到完整流程)

### 步骤
1. 主界面 → 点 "新建项目" → 名字 `VM 测试项目` → 选 `storyboard` profile
2. 选 "剧本" tab → 填 "测试剧情大纲" 几行
3. 点 "生成分镜" → 等 30-60 秒
4. **观察**: 报错? 出结果? 卡住?

### 验收
- ✅ 不崩溃(失败弹错误 OK)
- ❌ 用测试 key 失败 → 正常,只验证流程不崩
- ⏸ 用真 key 才出分镜

### 失败排查
- 报错 `未配置 API key` → wizard 没填好,重填
- 卡住不响应 → 看 logs 搜 "ERROR"
- DPAPI 错 → 删 secrets.bin 重填

---

## C12: 卸载(控制面板)

**目的**: 验证 Inno Setup `[UninstallDelete]` + `[UninstallRun]` 段正常,卸载干净。

### 步骤
1. 关闭漫剧助手X-2
2. 打开 **设置** → **应用** → 找 "漫剧助手X-2"
3. 点 "卸载" → 确认
4. 等 10-30 秒
5. 看弹窗 "卸载完成" → 点 "完成"

### 验收
- ✅ `C:\漫剧助手X-2\` 目录 **不存在**(被卸载器删)
- ✅ 开始菜单的 "漫剧助手X-2" 文件夹不存在
- ✅ 桌面快捷方式不存在
- ✅ 控制面板/应用列表里没有 "漫剧助手X-2"

### 失败排查
- 目录残留: 看 Inno 卸载日志,正常 [UninstallDelete] 会清 `logs\`, `cache\`, `*.tmp`
- **保留**项(预期): `config\secrets.bin` / `data\*.db` / `outputs\` / `logs\` 在卸载时**保留**(Inno 默认行为,user 手动决定要不要删)

---

## C13: 覆盖升级

**目的**: 验证 v1.0.0 → v1.0.0(同版本) / v1.0.0 → v1.0.1(新版本)能装,数据保留。

### 前置
- 需要有 v1.0.0 已装好的 VM(可重新跑 C5 步骤)
- 第一次跑这个 VM 时已经创建项目 + 写过数据

### 步骤
1. VM 装着 v1.0.0 + 已创建 "VM 测试项目" + 有 outputs 文件
2. **不**卸载
3. 重新双击 `漫剧助手X-2_v1.0.0_Setup.exe`(同版本覆盖)
4. 选 **相同**安装目录 `C:\漫剧助手X-2\`
5. 选 "安装" → 弹窗问"已存在是否覆盖" → 选 "是"
6. 等 30-60 秒
7. 点 "完成"(不勾选启动)

### 验收
- ✅ 装好没报错
- ✅ `C:\漫剧助手X-2\config\secrets.bin` **保留**(API key 还在)
- ✅ `C:\漫剧助手X-2\data\` **保留**(数据库在)
- ✅ `C:\漫剧助手X-2\outputs\VM 测试项目\` **保留**
- ✅ 启动软件,旧项目还在,不需要重填 API key

### 失败排查
- 数据丢失: 卸载器把 config/ 也删了 → 看 Inno .iss [UninstallDelete] 配置
- 启动报错: 加密 / DB 损坏 → 看 logs

---

## C15: 真 GitHub release 自动检查(发版后)

**目的**: 验证 Phase 5 `UpdateChecker` 真能拉 GitHub Releases + 弹红点 + 跳下载页。

### 前置
- user 已按 `GITHUB_RELEASE.md` 7 步发 v1.0.0
- GitHub 上有 `v1.0.0` release + 3 个附件(Setup.exe + md5 + sha256)
- `xyq900319xyq` 占位符已替换成 user 实际 GitHub org

### 步骤
1. 装好的 v1.0.0 启动
2. 等 3-5 秒(后台检查)
3. 看到 "帮助" 菜单的 "🔔 检查更新" + (若有新版)"🔴" 红点
4. 点 "🔔 检查更新"
5. **观察**: 弹 "已是最新版本" 或 "发现新版本 vX.Y.Z" + "去下载" 按钮
6. (若有新版)点 "去下载" → 浏览器打开 GitHub release 页
7. 看浏览器是否真打开 v1.0.0(同版本)或 v1.0.1(新版)的 release 页

### 验收
- ✅ 启动后无延迟(后台异步)
- ✅ "🔔 检查更新" 可点
- ✅ 同版本:弹 "已是最新"
- ✅ (需推 v1.0.1)新版:弹 "发现 v1.0.1" + 点"去下载" 跳 release 页
- ✅ 24h 缓存生效(再次启动 24h 内不拉)

### 验证 cache 文件
```powershell
Test-Path "C:\漫剧助手X-2\config\.update_check_cache.json"  # True
Get-Content "C:\漫剧助手X-2\config\.update_check_cache.json"  # 看里面 JSON
```

### 失败排查
- 没拉: 防火墙拦 GitHub API
- 红点不显示: 看 `C:\漫剧助手X-2\logs\manju-最新.log` 搜 "update"
- 跳错页: `build_x2.py` line 177 URL 写错(`xyq900319xyq` 没替换)

---

## VM 测试总览

| 编号 | 名称 | 状态 | 备注 |
|---|---|---|---|
| C5 | 无 UAC 装 | ⏸ 待测 | 默认路径 `C:\漫剧助手X-2\` |
| C14 | EXE 双击启动 | ⏸ 待测 | 必走 wizard 6 步 |
| 额外 | 创建项目 | ⏸ 待测 | 可选,验证核心流程不崩 |
| C12 | 卸载 | ⏸ 待测 | 控制面板 |
| C13 | 覆盖升级 | ⏸ 待测 | 同版本 + (有 v1.0.1 时)升级 |
| C15 | 真 release 自动检查 | ⏸ 待测 | Phase 7 发版后 |

---

## 测试报告模板

```markdown
# 漫剧助手X-2 VM 测试报告

**测试日期**: 2026-07-XX
**测试 VM**: (VirtualBox 7.0 / VMware 17 / 其它)
**VM 系统**: Win10 22H2 / Win11 23H2 / 其它
**VM RAM**: X GB
**网络环境**: (国内直连 / 走代理 / 翻墙)

## C5: 无 UAC 装
- [ ] UAC 弹窗: 有 / 无
- [ ] 装好文件存在: 是 / 否
- [ ] 桌面快捷方式: 有 / 无
- 备注: ...

## C14: EXE 启动 + wizard
- [ ] wizard 6 步正常: 是 / 否
- [ ] LLM 必填校验: 起作用 / 不起作用
- [ ] secrets.bin 存在: 是 / 否
- [ ] 加密生效(非明文): 是 / 否
- 备注: ...

## 额外: 创建项目
- [ ] 创建项目: 成功 / 失败
- [ ] 生成分镜: 成功 / 失败 / 卡住
- 备注: ...

## C12: 卸载
- [ ] 程序目录删除: 是 / 否
- [ ] 桌面快捷删除: 是 / 否
- [ ] 应用列表清除: 是 / 否
- 备注: ...

## C13: 覆盖升级
- [ ] secrets.bin 保留: 是 / 否
- [ ] data/ 保留: 是 / 否
- [ ] outputs/ 保留: 是 / 否
- [ ] 启动后无需重填 key: 是 / 否
- 备注: ...

## C15: 真 release 检查
- [ ] 红点显示(若有新版): 是 / 否
- [ ] 检查更新弹框: 是 / 否
- [ ] 跳 GitHub release 页: 成功 / 失败
- 备注: ...

## 总体评价
- [ ] 全过,可以发 v1.0.0 正式版
- [ ] 部分通过,需修 bug 后续
- [ ] 大问题,需重做

## 截图
(粘贴关键截图)
```

---

## 故障时收集的日志

出问题时报 issue,必带:

1. `C:\漫剧助手X-2\logs\manju-最新.log` (整个文件,出错前最后 200 行重点看)
2. `C:\Users\<user>\AppData\Local\Temp\Setup Log*.txt` (安装/卸载报错时)
3. VM 系统版本(Win10 22H2 19045.xxxx / Win11 23H2 22631.xxxx)
4. 复现步骤(精确到鼠标点击)

发到: https://github.com/&lt;your-org&gt;/manju-x2/issues
