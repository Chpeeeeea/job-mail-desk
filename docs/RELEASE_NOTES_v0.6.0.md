# JobMailDesk Core v0.6.0

> 发布类型：Pre-release。Core 可完全本地运行，不依赖模型或 API；Windows 尚未代码签名，macOS 尚未完成 Apple 签名与公证。

## 本次更新

- 新增 QQ、网易 163、网易 126、Yeah、Gmail、Outlook 与自定义 IMAP 服务商选项。
- 选择邮箱预设后自动填写 IMAP 主机、端口和 SSL/TLS，同时保留手动编辑能力。
- “测试只读邮箱连接”会使用当前尚未保存的表单参数，验证通过后再保存配置。
- 旧版只记录 IMAP 主机和端口的配置会自动推断服务商；未知主机归入自定义配置。
- 邮箱字段改为通用的“邮箱账号”和“客户端授权码”，不再限定 QQ 邮箱。
- SSL/TLS 开关现在会真实决定使用 `IMAP4_SSL` 或 `IMAP4`；两种连接都保持只读文件夹与 `BODY.PEEK`。
- 将 `cryptography` 升级并约束为 `>=50,<51`，修复 GitHub Dependabot 标记的 49.x 高危安全版本范围。

## 支持边界

- QQ 与网易邮箱通常需要在网页版开启 IMAP 并生成客户端授权码。
- Gmail 通常需要启用两步验证并创建应用专用密码。
- 部分 Outlook/Microsoft 365 账户强制 OAuth，当前 Core 尚未实现 OAuth，因此不能保证所有 Outlook 账户都能连接。
- 自定义邮箱必须提供标准 IMAP 地址、端口、SSL/TLS要求，以及可用于客户端登录的凭据。

## 隐私与兼容

- 凭据仍只进入 Windows Credential Manager 或 macOS Keychain，不写入配置文件、Markdown或日志。
- 邮件扫描仍使用只读模式，不删除、移动、回复或主动改变未读状态。
- 升级安装不会迁移或覆盖现有任务、数据库、Markdown 与 Obsidian 路径。
- 已有 QQ 配置无需重新填写；程序会根据 `imap.qq.com` 自动识别服务商。

## 已知限制

- Windows 与 macOS 发布包尚未完成代码签名或 Apple 公证。
- 当前不支持 OAuth 邮箱登录。
- 服务商可能调整 IMAP 开启方式、授权码规则或登录限制，请以邮箱官方说明为准。

推送 `v0.6.0` 标签后，GitHub Actions 将分别构建 Windows x64、macOS Apple Silicon 与 macOS Intel 包；三个平台全部通过并核对 SHA-256 后才创建 Pre-release。
