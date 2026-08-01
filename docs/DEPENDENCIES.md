# JobMailDesk Core 依赖说明

## 运行依赖

| 依赖 | 必需 | 用途 |
|---|---:|---|
| Windows 10/11 x64 或 macOS 12+ | 是 | Windows、Apple Silicon和Intel Mac |
| Edge WebView2 / macOS WebKit | 是 | 承载桌面HTML/CSS界面，均使用系统组件 |
| QQ邮箱IMAP授权码 | 是 | 通过TLS只读获取邮件 |
| 网络访问 `imap.qq.com:993` | 是 | QQ邮件扫描 |
| Obsidian | 否 | 将任务同步到用户选择的Markdown |
| Python/uv | 否 | 已包含在self-contained EXE中 |
| 大模型/API Key | 否 | Core使用本地规则解析 |
| Codex/OpenCLI | 否 | 仅未来Research插件需要 |

## 内置运行时与Python依赖

- Python 3.12运行时由Windows PyInstaller包或macOS py2app包封装。
- `pywebview`提供Windows WebView2或macOS Cocoa/WebKit窗口。
- `APScheduler`负责10分钟扫描、整点处理和早中晚简报。
- `keyring`把邮箱地址和授权码保存到Windows凭据管理器或macOS Keychain。
- `PyYAML`处理Markdown frontmatter。
- `pystray`提供Windows系统托盘；macOS使用Dock和应用菜单。
- SQLite来自Python标准库，仅用于去重和扫描状态。

## 网络边界

Core只需要连接用户配置的IMAP服务器。它不会调用OpenAI、模型API、小红书、牛客、X或YouTube。QQ邮箱和本地Markdown功能在中国大陆网络环境下不依赖境外模型服务。

## 可选Research插件边界

未来Research插件将单独声明模型提供商、平台登录态、网络条件和数据发送范围。Core不会因为未安装Research插件而缺失邮件、任务、日历或进展功能。
