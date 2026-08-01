# Changelog

JobMailDesk 使用语义化版本号。每个可验证阶段必须先更新本文件，再提交并推送到 GitHub。

## [Unreleased]

### Changed

- 重构README为面向终端用户的产品首页：优先展示三平台下载、首次配置、核心能力、隐私边界与更新方式，并将CLI和构建说明收纳到开发者折叠区。
- 增加系统下载表、工作流图、功能矩阵、Core/Research边界和签名路线，减少首次使用者在安装依赖与数据去向上的判断成本。
- README首屏升级为居中的产品标题、动态版本、跨平台、运行时、UI、构建和许可证徽章。
- README按产品预览、设计原则、核心能力、操作手册、设置、数据隐私、下载安装和开发文档重组，并加入三组可复现的匿名高清界面预览。
- 将独立许可证升级为可被GitHub识别的标准`LICENSE.md`，并新增中英文`docs/LICENSING.md`说明许可场景、再分发清单和第三方权利边界；发布包同步携带两份文件。

## [0.4.1] - 2026-08-01

### Fixed

- 统一版本通知区两个操作按钮的字号、高度、边框和禁用态，修复“打开下载页”误用系统原生大字号样式的问题。
- 将面向用户的“打开 Release 下载”改为更简洁的“打开下载页”，避免中英文混排造成视觉跳脱。

## [0.4.0] - 2026-08-01

### Added

- 设置页与Windows托盘增加版本通知入口，支持预览版/稳定版通道、每天一次后台检查和Release Notes。
- 只在本项目Release同时存在当前平台ZIP与同名`.sha256`时提示可用版本，并提供对应下载页。
- 新增版本检查结果缓存、手动更新入口和完整网络/隐私说明；程序不自动下载、解包或安装。

### Changed

- 发布工作流和Windows打包脚本从项目元数据读取版本，避免多处手工修改资产名。
- GitHub Actions升级到Node.js 24运行时的官方主版本，消除Node.js 20弃用警告；Release下载同时启用新版本默认的artifact digest强校验。
- Core仍不依赖GitHub运行；更新请求可关闭，网络失败不会阻塞邮件、任务、日历或Obsidian。

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

- 版本标签构建在三个平台全部成功后自动创建 GitHub prerelease，并上传 Windows x64、macOS Apple Silicon、macOS Intel 的 ZIP 与 SHA-256；缺少对应版本 Release Notes 时拒绝发布。
- GitHub Actions在指向`main`的Pull Request中自动运行Windows与macOS双架构构建，确保首次引入工作流时也能完成远端验收。
- 将py2app配置隔离到`packaging/macos/`，避免根目录PEP 621依赖被映射为py2app已禁止的`install_requires`。
- 将PyInstaller限定为Windows开发依赖，并从macOS包显式排除，避免py2app误收集Windows构建工具及其可选Qt hooks。
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
