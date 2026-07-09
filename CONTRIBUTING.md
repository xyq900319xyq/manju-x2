# 贡献指南

> **注**: manju-x2 主要是 user 自己的产品,欢迎 issue 提 bug 和功能建议,但**不**接受大改 PR(架构 / API)。小修小补(typo / 文档 / 小 bug)欢迎。

## 报告问题

用 [GitHub Issues](https://github.com/&lt;your-org&gt;/manju-x2/issues) 报告,选对应模板:
- **Bug 报告** - 软件出问题
- **功能建议** - 想要新功能
- **提问 / 讨论** - 用法 / 配置求助

**提供 logs\manju-最新.log** 能极大加快定位。

## 提 PR 流程

1. Fork 仓库
2. 创建分支(`git checkout -b fix/xxx` 或 `feat/xxx`)
3. 改代码 + 改 docs/更新日志.md
4. 本地测试(至少跑一次完整流程:创建项目 → 生成分镜 → 提示词)
5. `git commit -m "fix: 简短描述"`(用 [Conventional Commits](https://www.conventionalcommits.org/) 风格)
6. `git push origin fix/xxx`
7. 开 PR,填 .github/PULL_REQUEST_TEMPLATE.md

## 代码风格

- **Python**: 跟现有代码一致(4 空格缩进,PEP 8,type hint 可选)
- **导入**: 标准库 → 第三方 → 本地,各组间空一行
- **字符串**: 默认双引号 `"`,SQL/JSON 用单引号可以
- **注释**: 中文 OK,关键逻辑必须解释"为什么"不是"做什么"
- **不要**写无意义 fallback / 兜底(只实现需求,异常清楚报错)

## 不接受的改动

- ❌ 大改架构(模块拆合 / 跨模块依赖)
- ❌ 加新功能(超出现有需求范围)
- ❌ 加新依赖(> 50 MB 那种,如 TensorFlow)
- ❌ 改 API 协议(LLM / 图像 / 视频请求格式)
- ❌ 改 hermes.exe 的 hermes 端行为
- ❌ 把 dev 端 `D:\hermes\` / `D:\漫剧助手\` 的代码混进来

## 接受的改动

- ✅ 修 bug(配合 issue)
- ✅ 性能优化(有基准数据)
- ✅ 文档改进(typo / 翻译 / 例子)
- ✅ UI 微调(配色 / 布局 / 字号)
- ✅ 新模型支持(只加 base_url / model 模板,不破坏现有)
- ✅ 小工具(导入导出 / 批量操作)

## 开发环境

```bash
# 1. 装 Python 3.11(用 hermes venv 或独立 venv)
python --version  # >= 3.11

# 2. 装依赖(参考 source/requirements.txt)
pip install -r source/requirements.txt

# 3. 跑源码(不打包,直接 python 启动)
cd D:\漫剧助手\manju-x2\source
python src\main.py

# 4. 打包测试
cd D:\漫剧助手\manju-x2
python build_x2.py
# → release\漫剧助手X-2_vX.Y.Z_Setup.exe
```

## License

贡献的代码遵循 [LICENSE](LICENSE.txt) (MIT)。
