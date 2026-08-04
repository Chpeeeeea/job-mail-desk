# JobMailDesk Core v0.6.0 验收记录

## 本地验收

- [x] QQ、163、126、Yeah、Gmail、Outlook 与 Custom 七个选项进入设置页。
- [x] 选择预设会更新主机、端口和 SSL/TLS；Custom 不覆盖手动输入。
- [x] 旧版仅含 host/port 的 QQ 与常用邮箱配置可自动推断服务商。
- [x] 自定义 host、port、SSL/TLS 可写入配置并重新读取。
- [x] 连接测试使用尚未保存的表单值。
- [x] SSL/TLS 关闭时使用 `IMAP4`，开启时使用 `IMAP4_SSL`；两者都保持只读与 `BODY.PEEK`。
- [x] 凭据继续通过系统凭据库保存，不进入 TOML。
- [x] `cryptography` 解析为 50.0.0，Windows `WinVaultKeyring` 可正常导入。

## 自动化验证

- [x] `uv sync --group dev`：通过。
- [x] `uv run pytest -q`：137 项通过。
- [x] `node --check src/job_mail_desk/ui/app.js`：通过。
- [x] `scripts/secret-scan.ps1`：通过。
- [x] `git diff --check`：通过。
- [x] Windows x64 self-contained EXE：本地构建成功。
- [x] v0.6.0 本地 RC ZIP 与 `.sha256`：已生成并核验一致。
- [ ] GitHub Actions Windows x64 构建：待标签触发。
- [ ] GitHub Actions macOS Apple Silicon 构建：待标签触发。
- [ ] GitHub Actions macOS Intel 构建：待标签触发。
- [ ] GitHub Release 包含 3 个 ZIP 与 3 个 SHA-256 文件：待 Actions 完成。

## 发布边界

- v0.6.0 标记为 Pre-release。
- Windows 包尚未代码签名；macOS 包尚未 Apple 签名和公证。
- 当前只支持 IMAP 客户端授权码、应用专用密码或服务商允许的传统凭据，不支持 OAuth。
- 邮件正文、邮箱地址、授权码、私人链接、真实 Message-ID 与本地任务不进入公开仓库或发布包。
