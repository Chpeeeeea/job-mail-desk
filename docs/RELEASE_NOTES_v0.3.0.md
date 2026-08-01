# JobMailDesk Core v0.3.0

首个适合邀请朋友试用的Core预览版。

## 主要功能

- QQ邮箱IMAP只读扫描，不修改邮件状态。
- 本地规则识别公司、岗位、阶段、轮次和时间。
- Markdown任务、今天/周历/月历/待确认/待办视图。
- 按企业折叠的求职进展总览。
- 首次运行配置向导和托盘“设置”入口。
- 原生选择Obsidian、进展输出和手动台账路径。
- 一键生成规范进展台账模板。
- Windows凭据管理器或macOS Keychain保存IMAP授权码。
- 系统级单实例锁，快速重复点击不会启动第二套扫描器。
- Windows高DPI Per-Monitor v2与macOS Retina渲染。
- GitHub Actions生成Windows x64、macOS arm64与macOS Intel包。

## Core边界

- 不使用大模型，不需要API Key。
- 默认关闭公开研究队列。
- 不需要Python、uv、Codex或OpenCLI。
- Obsidian可选。

## 已知限制

- 当前提供Windows x64与macOS双架构预览包。
- 尚未进行Windows代码签名或Apple公证，系统可能显示来源提醒。
- 规则解析无法保证覆盖所有招聘邮件模板；不确定内容进入待确认。
- 当前只配置一个IMAP邮箱账号。
