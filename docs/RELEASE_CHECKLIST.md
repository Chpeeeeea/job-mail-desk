# Release checklist

JobMailDesk Core 使用带版本号的 Git 标签触发 GitHub 预发布。当前版本尚未完成 Apple 签名、公证与三天真实试运行，因此只能标记为 prerelease。

## 发布前

- `CHANGELOG.md` 已记录本阶段面向用户的变化。
- `docs/RELEASE_NOTES_vX.Y.Z.md` 存在，文件名与标签一致。
- `docs/ACCEPTANCE_vX.Y.Z.md` 存在，并记录本地验收与待由 Actions 完成的远端门禁。
- 标签 `vX.Y.Z` 必须与 `pyproject.toml`、`job_mail_desk.__version__` 完全一致。
- Pull Request 的 Windows x64、macOS Apple Silicon、macOS Intel 构建全部通过。
- `pytest`、秘密扫描与 `git diff --check` 通过。
- IMAP 保持 `readonly=True` 与 `BODY.PEEK`，扫描前后的未读数和 UID 状态不变。
- 匿名回归邮件覆盖硬截止、`24:00`、跨日窗口、改期、重复邮件与待确认逻辑。

## 自动发布

1. 合并经过验收的 Pull Request 到 `main`。
2. 在合并提交上创建并推送 `vX.Y.Z` 标签。
3. GitHub Actions 构建三个平台包，校验应用 bundle，并生成 SHA-256。
4. 所有构建成功后，工作流自动创建 GitHub prerelease。

自动发布必须包含六个文件：

- Windows x64 ZIP 与 SHA-256。
- macOS Apple Silicon ZIP 与 SHA-256。
- macOS Intel ZIP 与 SHA-256。

## 发布后

- 从 GitHub Release 重新下载资产并核对文件数、名称与校验和。
- 在一台未安装 Python 的 Windows 电脑验证首次配置、缓存首屏、扫描、退出和重复启动。
- 在真实 Apple Silicon 与 Intel Mac 上验证首次打开、Keychain、系统 WebKit、窗口与退出。
- 至少完成三天本地真实邮件试运行；在此之前不提升为 stable release。
- macOS 未签名、公证期间，发布说明必须保留 Gatekeeper 提示。

## 使用者依赖

- Windows 10/11 x64，或 macOS 12+。
- Windows 需要 Edge WebView2 Runtime；Windows 11 通常已预装。
- 可连接 IMAP 的邮箱及单独生成的授权码；QQ 邮箱默认使用 `imap.qq.com:993`。
- Obsidian、进展 Markdown 与 AI Research 均为可选项。
- 最终用户不需要 Python、uv、Codex、模型 API 或境外网络。
