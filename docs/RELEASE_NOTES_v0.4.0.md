# JobMailDesk Core v0.4.0

首个提供新版本通知能力的Core预览版。

## 新增

- 设置页“软件更新”和Windows托盘“检查更新”。
- 预览版、稳定版两个更新通道。
- 每24小时最多一次自动检查及本地结果缓存。
- Release Notes、对应平台资产名和手动Release入口。
- 只在对应平台ZIP和同名`.sha256`都存在时提示版本可用。
- 发布工作流从项目版本动态生成资产名，减少版本号遗漏。

## 重要迁移说明

程序只负责提示和展示公告，不会自动下载或安装。退出JobMailDesk后手动覆盖EXE或`.app`；本地任务、配置、凭据和Obsidian不会被覆盖。

## 隐私

自动检查只访问本项目公开GitHub Releases API，不包含邮箱、邮件、任务、凭据、本地路径或Obsidian内容。GitHub不可访问时不影响Core功能。

## 已知限制

- 当前Windows和macOS包尚未完成代码签名或Apple公证。
- 三天真实环境稳定性试运行仍在进行，因此保持prerelease。
