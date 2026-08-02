# JobMailDesk Core 快速开始

## 安装

1. Windows下载 `JobMailDesk-Core-v0.4.2-win-x64.zip`；Apple Silicon Mac下载`macos-arm64`，Intel Mac下载`macos-x64`。
2. 解压后启动 `JobMailDesk.exe` 或把 `JobMailDesk.app` 拖入“应用程序”再打开。
3. 先核对文件来自本项目GitHub Release及SHA256校验值。未签名的Mac预览包首次打开时需在“系统设置 → 隐私与安全性”确认。

程序是self-contained单文件，无需安装Python。

## 首次设置

首次启动会自动打开设置：

1. 填写完整QQ邮箱地址。
2. 填写QQ邮箱为IMAP生成的授权码，不是QQ密码。
3. 保持默认10分钟扫描，或选择5至120分钟。
4. 不使用Obsidian时关闭“同步到Obsidian”。
5. 使用Obsidian时选择一个 `.md` 文件作为待办总览。
6. 如需手动维护企业进展，开启“生成求职进展文档”，并点击“生成规范台账模板”。
7. 点击“保存并应用”。

默认每天最多检查一次预览版更新。若不希望连接GitHub，可关闭“每天自动检查一次”；邮件扫描和本地任务不受影响。

授权码只进入Windows凭据管理器或macOS Keychain，不写入配置文件、Markdown或日志。

## 进展台账格式

程序只读取模板中的“已投递或已进入流程”区域，每个岗位一行：

```markdown
- [x] 公司｜岗位｜**当前进展**｜下一步动作
```

例如：

```markdown
- [x] 示例科技｜产品经理｜**一面已确认**｜8月6日14:00参加面试
```

同一岗位进展变化时修改原行，不要重复追加。程序不会覆盖台账中的手写内容。

## 日常打开

- 双击 `JobMailDesk.exe`。
- 运行后可以从系统托盘显示、隐藏、扫描或打开设置。
- 快速重复点击不会启动第二套扫描器。

## 版本通知与更新

- `v0.4.0`及以后会在设置页提示新版本，也可以从Windows托盘手动检查。
- 程序不会自动下载或覆盖；阅读公告后打开Release，下载对应ZIP和`.sha256`。
- 从托盘退出程序，手动覆盖EXE或`.app`后重新启动。
- 本地数据目录和系统凭据库不会参与覆盖。

## 数据位置

```text
%LOCALAPPDATA%\JobMailDesk
```

macOS数据位于：

```text
~/Library/Application Support/JobMailDesk
```

卸载程序不会自动删除这里的任务和配置。备份时复制此目录，但不要公开其中的任务、日志或私人链接。
