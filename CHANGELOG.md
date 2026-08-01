# Changelog

JobMailDesk 使用语义化版本号。每个可验证阶段必须先更新本文件，再提交并推送到 GitHub。

## [Unreleased]

- GitHub Actions在指向`main`的Pull Request中自动运行Windows与macOS双架构构建，确保首次引入工作流时也能完成远端验收。
- 将py2app配置隔离到`packaging/macos/`，避免根目录PEP 621依赖被映射为py2app已禁止的`install_requires`。

## [0.3.0] - 2026-08-01

### Added

- 首次运行配置向导和常驻设置页面，支持 QQ IMAP、扫描周期、Obsidian 输出与求职进展路径。
- `task-list` / `task-update` 本地 Agent 接口：按稳定任务 ID 写回完成、恢复、改期、忽略和详情字段。
- 周历、月历、企业进展、待确认和待办视图；完成项保留并可恢复。
- 侧边胶囊、跨屏边缘吸附、托盘入口、单实例 `show` 唤回和缓存首屏。
- Windows x64 self-contained 构建；GitHub Actions 中的 macOS Apple Silicon / Intel 构建链。
- 求职进展模板、独立进展文档及 Obsidian 稳定 ID 双向勾选同步。
- 匿名解析回归：百度考试窗口、海信跨日窗口、科大讯飞测评有效期、慧策旺店通 `24:00` 简历截止。

### Changed

- Core 默认完全本地、无需模型/API/境外网络；Research 改为显式启用的可选边界。
- 桌面卡片和 Agent 更新统一调用同一个同步服务，实时刷新任务 Markdown、日历、进展和 Obsidian。
- 解析器升级采用版本化回放与消息哈希修正，忽略项和已完成项不会被重复扫描复活。
- 启用 Per-Monitor DPI v2；窗口默认尺寸与编辑尺寸调整为更适合详情维护。
- 从 Core 安装包移除已经取消的独立待办纸、笔记纸及其前端资源；旧版本本地 Markdown 数据不会被删除。

### Fixed

- 修复 pywebview 暴露原生窗口对象导致的启动白屏、卡顿和递归辅助功能错误。
- 修复重复启动生成多套托盘、调度器和数据库连接的问题。
- 修复退出时 `Scheduler is not running` 未处理异常。
- 修复 QQ 招聘邮件中的 `24:00`、有效期、条件拒绝词和模板噪声误判。
- 修复完成、忽略或改期后重新扫描产生重复卡片和重复研究请求的问题。

### Security

- IMAP 保持 `readonly=True` 和 `BODY.PEEK`，不修改未读状态。
- 凭据只进入 Windows Credential Manager 或 macOS Keychain。
- 发布秘密扫描覆盖邮箱、个人路径、授权码、私人 URL 和长数字标识。
