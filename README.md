# JobMailDesk

JobMailDesk 是一个隐私优先、Markdown 原生的 Windows / macOS 求职邮件工作台。它只读扫描 IMAP 邮箱，将招聘通知整理为本地任务、周/月日历和可选的 Obsidian 待办。

> 当前版本：v0.4.1 Core 预览版。公开仓库仅包含匿名源码；真实邮件、本地任务、凭据和私人链接始终留在本机。

版本演进与阶段性修复见 [CHANGELOG.md](CHANGELOG.md)。项目规定每个已验收阶段都必须先更新 Changelog，再形成独立提交并推送 GitHub。

## Core版定位

JobMailDesk Core 完全在本机运行，不使用大模型、不需要API Key，也不包含自动网络研究。邮件通过QQ IMAP只读获取，使用规则解析形成Markdown任务和桌面卡片。研究模块代码仅作为未来插件接口保留，新用户默认关闭。

### 终端用户依赖

- Windows 10/11 x64，或 macOS 12+（Apple Silicon / Intel）。
- Windows需要Microsoft Edge WebView2 Runtime；Windows 11通常已预装。macOS使用系统WebKit。
- 可访问 `imap.qq.com:993` 的网络。
- 已开启IMAP的QQ邮箱，以及单独生成的IMAP授权码；不使用QQ登录密码。
- Obsidian完全可选；未安装时任务仍保存在系统本地数据目录。

不需要Python、`uv`、Codex、OpenCLI、模型API或研究Skill。开发和重新构建源码时才需要Python 3.12与`uv`。

首次双击EXE会打开配置向导。也可以从右上角齿轮或系统托盘“设置”重新进入：

- 配置QQ邮箱与IMAP授权码。
- 调整扫描间隔和回看天数。
- 可选关联Obsidian待办Markdown。
- 可选生成求职进展文档。
- 可选创建规范的手动进展台账模板。
- 可选每天检查一次更新，并选择预览版或稳定版通道。

详细步骤见 [Core快速开始](docs/CORE_QUICKSTART.md)、[版本通知与手动更新](docs/UPDATES.md)、[依赖说明](docs/DEPENDENCIES.md)、[发布检查清单](docs/RELEASE_CHECKLIST.md) 与 [v0.4.1验收记录](docs/ACCEPTANCE_v0.4.1.md)。

## 核心边界

- IMAP 始终使用 `readonly=True` 和 `BODY.PEEK`。
- 不删除、移动、回复邮件，也不修改邮件未读状态。
- 邮件正文只在内存中参与规则解析；落盘仅保存结构化字段、脱敏摘要和本地来源链接。
- 凭据仅写入 Windows Credential Manager 或 macOS Keychain。
- 公开研究请求只包含公司、岗位、招聘项目、年份和阶段。
- 正式面试题库只能经人工确认更新。

## 能做什么

- 每 10 分钟检测新邮件和硬截止。
- 归并同一公司的笔试、面试、Offer、拒信和改期通知。
- 生成独立 Markdown 任务、日报和 Obsidian 总览。
- 从 Obsidian 稳定任务 ID 回读勾选状态，不覆盖手写区。
- 桌面组件提供今天、进展、周历、月历、待确认和待办视图。
- 进展页按企业和申请链显示当前阶段、笔试/面试轮次和历史节点，并可同步到独立 Markdown 文档。
- 主窗口由系统托盘管理，不出现在任务栏、`Alt+Tab` 或任务视图中。
- 仅标题区调用 Windows 原生移动循环；点击求职卡片打开详情编辑，避免把窗口移动误解为卡片排序。
- 主窗口可折叠为 `36×88` 侧边条，只缩进 4px；保留品牌、任务数和清晰拖动柄，不再裁切中文内容。
- 完成项保留在待办和日历中，以灰色删除线显示，再次点击可以恢复。
- 手动任务按公司、岗位、阶段和日期幂等更新，重复保存不会产生第二张活动卡片。
- 忽略状态跨扫描保留；同一邮件不会在下一次扫描时重新出现。
- 每日 `08:00 / 13:00 / 20:00` 生成本地简报。
- 设置页和Windows托盘可以检查GitHub Release、展示更新公告并打开对应下载页。
- 为 `vibe-web-research` 生成零敏感字段的 JSONL 队列。

## 本地目录

```text
%LOCALAPPDATA%\JobMailDesk\
├── config.toml
├── state.db
├── JobMailDesk.md
├── research-queue.jsonl
├── tasks\
├── digests\
├── updates\
└── logs\
```

Markdown 是任务事实层；SQLite 只保存邮件去重、扫描状态和可重建索引。

## 开发运行

以下命令仅供源码开发，要求Python 3.12、`uv`和IMAP授权码。

```powershell
uv sync --group dev
uv run jobmaildesk configure
uv run jobmaildesk doctor
uv run jobmaildesk scan --once --shadow
uv run jobmaildesk scan --once
uv run jobmaildesk ui
```

已有 `job-mail-watch` Windows用户可复用其Credential Manager凭据，无需把授权码写入终端或配置文件。

## CLI

```text
jobmaildesk configure
jobmaildesk doctor [--offline]
jobmaildesk scan --once [--days N] [--shadow]
jobmaildesk run
jobmaildesk digest morning|noon|evening
jobmaildesk export [--obsidian]
jobmaildesk research-queue
jobmaildesk task-list [--company 公司] [--role 岗位] [--stage 阶段]
jobmaildesk task-update TASK_ID [--status done|planned|needs_review|cancelled|irrelevant]
jobmaildesk ui
jobmaildesk show
```

`--shadow` 只输出脱敏结构化预览，不写任务、不导出 Obsidian、不写研究队列。

`show` 是日常入口：已有窗口时直接从托盘状态唤回；程序未运行时才启动新窗口。self-contained EXE 可使用同样的 `JobMailDesk.exe show` 参数。Windows 命名 Mutex 会在窗口创建前完成原子单实例判断，因此快速双击也不会初始化第二套托盘、调度器或数据库连接。

`task-list` 与 `task-update` 是本地 Agent 写回接口。用户在对话里说“京东群面完成了”时，Agent 先按公司/岗位/阶段查询稳定任务 ID，再按该 ID 更新；程序会在同一次事务后刷新任务 Markdown、桌面卡片、周/月日历、企业进展文档与 Obsidian 受管区。完成状态可以用 `--status planned` 恢复，手写区不会被覆盖。接口只修改本地任务，不会修改邮箱。

```powershell
JobMailDesk.exe task-list --company 京东 --stage 群面
JobMailDesk.exe task-update 1fb3083a5dab4e22aa3c1d6c --status done --manual-notes "用户在对话中确认完成"
JobMailDesk.exe task-update 1fb3083a5dab4e22aa3c1d6c --status planned
```

## 桌面交互

- `＋`：直接创建求职任务，不再显示独立待办纸/笔记纸菜单。
- `编辑`：修改公司、岗位、阶段、轮次、时间、行动和 Markdown 手动补充。
- `▯`：折叠成清晰的侧边条；下方点阵负责拖动，中间按钮负责展开。
- 标题空白区：拖动整个工作台；卡片本体只负责查看和修改详情。
- 默认纸片为 `480×740`；编辑任务时自动扩展至不小于 `680×820`，关闭编辑器后恢复原来的纸片大小。
- `进展`：默认以单行企业折叠总览展示全部公司、当前阶段和进行中数量；点击企业下拉查看岗位、轮次与历史节点，也可一键展开或收起全部。
- `待办`：显示全部活动事项，同时保留已完成事项。
- `Obsidian`：通过 `obsidian://` 打开待办集，不受 Windows `.md` 默认编辑器影响。
- `补时间`：仅在没有明确时间时显示，直接打开详情中的时间输入区；原先无实际作用的“确认”状态按钮已移除。
- `邮件链接`：仅在邮件中提取到可用链接时显示，打开通知或操作网页，不是打开邮箱原文。
- `完成 / 恢复`：保留任务并切换灰色删除线状态；`延后`：24 小时内移出提醒区但不更改活动时间；`忽略`：永久移出本地活动视图且后续扫描不会重新激活。三类操作都必须在 3 秒内点击两次才会执行，且均不修改邮箱。

## Windows 日常入口

构建后的 `JobMailDesk.exe` 已包含 Python 运行时，是可直接双击的 self-contained 单文件程序。推荐安装两个稳定快捷方式，而不是把 EXE 复制到桌面：

```powershell
.\scripts\install-shortcuts.ps1 -ExePath ".\release\JobMailDesk.exe"
```

快捷方式会出现在桌面和开始菜单，调用 `show` 命令。程序运行时也可在系统托盘找到 JobMailDesk：双击托盘图标显示，右键可显示、隐藏、扫描或退出。后续覆盖原路径的 EXE 即可升级，快捷方式无需重建。

PaperTodo 的 README 仅作为托盘和桌面收纳交互的验收参考；JobMailDesk 不再提供独立待办纸或笔记纸。旧版本产生的本地 Markdown 不会被删除，但新版本不会自动打开或继续创建它们。

## 版本通知与手动更新

从`v0.4.0`开始，程序可以提示有新版本，但不会自动下载、覆盖或重启：

1. 打开“设置 → 软件更新”或Windows托盘“检查更新”。
2. 选择预览版或稳定版通道。
3. 查看更新公告并打开对应Release。
4. 下载对应平台ZIP及`.sha256`，退出程序后手动覆盖。

手动覆盖`JobMailDesk.exe`或`JobMailDesk.app`不会修改`%LOCALAPPDATA%\JobMailDesk`、macOS Application Support、系统凭据库或Obsidian。GitHub不可访问时不会影响邮件扫描和已有任务。完整说明见[版本通知与手动更新](docs/UPDATES.md)。

## 测试与构建

```powershell
uv run pytest
.\scripts\secret-scan.ps1
.\scripts\build.ps1 -OutputRoot ".\release"
.\scripts\package-core.ps1 -ExePath ".\release\JobMailDesk.exe" -OutputDirectory ".\release"
```

Windows发布文件生成到：

```text
release\JobMailDesk-Core-v0.4.0-win-x64.zip
```

PyInstaller 产物包含 Python 运行时，目标电脑无需单独安装 Python。

## macOS 发布包

GitHub Actions在真实macOS Runner上分别生成：

```text
JobMailDesk-Core-v0.4.0-macos-arm64.zip
JobMailDesk-Core-v0.4.0-macos-x64.zip
```

Apple Silicon（M1及更新）使用`arm64`，Intel Mac使用`x64`。macOS版由py2app打包，使用系统WebKit与Keychain，不需要Python。当前预览包尚未Apple签名或公证，首次打开需在“系统设置 → 隐私与安全性”中确认。macOS版通过Dock管理应用，设置入口位于纸片右上角齿轮；Windows版继续使用系统托盘。

## 研究流程

> Core发布包默认关闭本节功能；普通用户无需配置。研究能力将在后续JobMailDesk Research插件中提供。

研究队列由一条固定的本地 Codex 心跳自动化处理；它始终复用同一对话和同一个 JSONL 队列，只领取 `pending` 请求。稳定请求 ID 与状态机共同阻止重复入队和重复检索。检索顺序固定为：

1. 企业官方
2. 牛客
3. X / 小红书 / 抖音
4. GitHub / YouTube
5. B站仅作补充

所有平台仅搜索、打开和读取；不点赞、不收藏、不评论、不下载媒体。候选与草稿写入库外研究区，人工确认后才能汇入正式题库。

## 许可证与参考

项目采用 MIT License。PaperTodo 只用于纸片式交互启发，未复制其代码或素材；参考项目及许可边界见 `THIRD_PARTY_NOTICES.md`。

## 隐私与安全

- [PRIVACY.md](PRIVACY.md)
- [SECURITY.md](SECURITY.md)
- [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
