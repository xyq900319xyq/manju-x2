# Pull Request 模板

## 改动类型

- [ ] Bug fix(non-breaking,改 bug)
- [ ] New feature(non-breaking,加功能)
- [ ] Breaking change(改架构 / API,可能影响现有用法)
- [ ] Docs only(只改文档)
- [ ] Refactor(只重构,不改功能)

## 描述

一句话说清楚改了什么 + 为什么

## 关联 Issue

(可选)Fixes #123 / Closes #456

## 测试

- [ ] 我在干净 Win10/11 VM 装过这个版本
- [ ] 我跑过本地测试 `python -m pytest tests/`(如有)
- [ ] 我手动测过主要场景(创建项目 → 生成分镜 → 提示词)

## 截图 / 录屏

(可选,UI 改动必填)

## Checklist

- [ ] 我的代码遵循项目代码风格
- [ ] 我加了必要的注释
- [ ] 我更新了 `docs/更新日志.md`(如果是非 docs-only 改动)
- [ ] 我没动 `release/`、`dist/`、`build/` 目录(那是 PyInstaller 产物,改了也不生效)
- [ ] 我没把 `secrets.bin` / `outputs/` / `data/*.db` 等用户数据提交进来
