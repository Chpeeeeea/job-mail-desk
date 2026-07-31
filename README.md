# JobMailDesk

JobMailDesk 是一个隐私优先、Markdown 原生的 Windows 求职邮件工作台。它只读扫描 IMAP 邮箱，将招聘通知整理为本地任务、周/月日历和 Obsidian 待办，并把脱敏后的公司/岗位信息放入公开研究队列。

> 当前版本：v0.2 预览版。公开仓库仅包含匿名源码；真实邮件、本地任务、凭据和私人链接始终留在本机。

## 核心边界

- IMAP 始终使用 `readonly=True` 和 `BODY.PEEK`。
- 不删除、移动、回复邮件，也不修改邮件未读状态。
- 邮件正文只在内存中参与规则解析；落盘仅保存结构化字段、脱敏摘要和本地来源链接。
- 凭据仅写入 Windows Credential Manager。
- 公开研究请求只包含公司、岗位、招聘项目、年份和阶段。
- 正式面试题库只能经人工确认更新。

## 能做什么

- 每 10 分钟检测新邮件和硬截止。
- 归并同一公司的笔试、面试、Offer、拒信和改期通知。
- 生成独立 Markdown 任务、日报和 Obsidian 总览。
- 从 Obsidian 稳定任务 ID 回读勾选状态，不覆盖手写区。
- 桌面组件提供今天、周历、月历、待确认和研究视图。
- 可创建多个独立待办纸和 Markdown 笔记纸，每张纸都是独立窗口。
- 待办支持多行粘贴、勾选、编辑、删除、手柄排序、撤销/重做和清理已完成。
- 笔记支持三档 Markdown 显示、格式快捷键、文字缩放和本地图片。
- 笔记标记可拖到待办项建立关联。
- 纸片可折叠为 `40×112` 侧边胶囊；贴边后只露出 13px，悬停滑出。
- 暖纸、墨、林、霞四套配色，支持系统深色、字体和字号调整。
- 完成或忽略任务时同步关闭尚未处理的研究请求。
- 每日 `08:00 / 13:00 / 20:00` 生成本地简报。
- 为 `vibe-web-research` 生成零敏感字段的 JSONL 队列。

## 本地目录

```text
%LOCALAPPDATA%\JobMailDesk\
├── config.toml
├── state.db
├── JobMailDesk.md
├── research-queue.jsonl
├── tasks\
├── papers\
├── paper-backups\
├── note-assets\
├── trash\
├── digests\
└── logs\
```

Markdown 是任务事实层；SQLite 只保存邮件去重、扫描状态和可重建索引。

## 开发运行

要求：Windows、`uv`、IMAP 授权码。

```powershell
uv sync --group dev
uv run jobmaildesk configure
uv run jobmaildesk doctor
uv run jobmaildesk scan --once --shadow
uv run jobmaildesk scan --once
uv run jobmaildesk ui
```

已有 `job-mail-watch` 用户可复用其 Windows Credential Manager 凭据，无需把授权码写入终端或配置文件。

## CLI

```text
jobmaildesk configure
jobmaildesk doctor [--offline]
jobmaildesk scan --once [--days N] [--shadow]
jobmaildesk run
jobmaildesk digest morning|noon|evening
jobmaildesk export [--obsidian]
jobmaildesk research-queue
jobmaildesk ui [--new todo|note]
```

`--shadow` 只输出脱敏结构化预览，不写任务、不导出 Obsidian、不写研究队列。

## 桌面交互

- `＋`：创建求职任务、独立待办纸或独立笔记纸。
- `编辑`：修改公司、岗位、阶段、轮次、时间、行动和 Markdown 手动补充。
- `▯`：折叠成侧边胶囊；悬停滑出，点击恢复纸片。
- `Obsidian`：通过 `obsidian://` 打开待办集，不受 Windows `.md` 默认编辑器影响。
- `完成 / 忽略`：关闭任务，同时关闭其未执行研究请求，后续扫描不会重新创建。

PaperTodo 的 README 被用作功能与交互验收清单；JobMailDesk 的数据模型、窗口控制、界面代码和素材均为独立实现。脚本胶囊在 v0.2 中默认禁用，避免公开版本把任意笔记静默执行为 PowerShell。

在 Windows 上，每张纸片由同一 EXE 启动一个轻量独立进程。这样纸片能真正独立拖动、折叠和恢复，同时避免动态 WebView 子窗口桥接不稳定。

快捷启动可使用 `JobMailDesk.exe ui --new todo` 或 `JobMailDesk.exe ui --new note`。第二实例控制、全局快捷键和任意 PowerShell 执行不属于 v0.2 的安全范围。

## 测试与构建

```powershell
uv run pytest
.\scripts\secret-scan.ps1
.\scripts\build.ps1
```

构建结果复制到：

```text
D:\WrokSpace\Obsidian-Workspace\Vibe\output\JobMailDesk\JobMailDesk.exe
```

PyInstaller 产物包含 Python 运行时，目标电脑无需单独安装 Python。

## 研究流程

研究队列由本地 Codex 自动化处理，顺序固定为：

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
