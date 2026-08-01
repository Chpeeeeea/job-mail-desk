# 版本通知与手动更新

JobMailDesk从v0.4.0开始提供可选的版本通知，不会自动下载、覆盖或重启应用。

## 工作方式

- “预览版”通道显示包括prerelease在内的新版本。
- “稳定版”通道忽略prerelease，只显示正式Release。
- 自动检查默认开启，每24小时最多请求一次公开GitHub Releases API。
- 检查结果缓存在本地`updates/state.json`，重复启动不会重复请求。
- 设置页展示版本号、更新公告、对应平台文件名和Release入口。

可以关闭“每天自动检查一次”，继续保留手动检查入口。更新检查失败不会影响邮件扫描、日历、任务或Obsidian。

## 手动更新

1. 打开“设置 → 软件更新”或Windows托盘“检查更新”。
2. 阅读更新公告并打开对应GitHub Release。
3. 下载程序提示的平台ZIP及同名`.sha256`文件。
4. 核对SHA-256后，从托盘退出JobMailDesk。
5. Windows用新版`JobMailDesk.exe`覆盖旧文件；macOS用新版`JobMailDesk.app`替换旧应用。
6. 重新启动。桌面和开始菜单快捷方式无需重建。

更新只涉及应用文件。Windows数据仍位于`%LOCALAPPDATA%\JobMailDesk`，macOS数据仍位于`~/Library/Application Support/JobMailDesk`；系统凭据库和Obsidian文件不会被覆盖。

## 网络与隐私

版本检查使用匿名HTTPS请求读取本项目公开GitHub Release，不需要GitHub账号或Token。请求不包含邮箱、邮件、任务、凭据、本地路径或Obsidian内容。GitHub仍可观察请求IP和User-Agent中的JobMailDesk版本。

在GitHub连接不稳定的网络中，可以关闭自动检查，或者使用浏览器、其他设备和可信镜像手动下载。Core业务功能不依赖GitHub。
