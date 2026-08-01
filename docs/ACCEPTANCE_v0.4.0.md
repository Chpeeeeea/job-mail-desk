# v0.4.0 验收记录

## 自动化覆盖

- 语义版本比较和Windows/macOS架构选择。
- 预览版与稳定版通道隔离。
- Release资产必须来自本项目GitHub地址。
- 只有同时包含当前平台ZIP和同名`.sha256`的Release才会提示。
- 每日检查缓存可以在重启后恢复“发现更新”状态。
- 程序桥不提供下载、解包、执行或安装更新的接口。
- 原有邮箱、解析、Markdown、Obsidian、进展、UI与单实例回归继续通过。

## 发布前远端验证

- [ ] Windows x64构建、测试、秘密扫描和ZIP上传。
- [ ] macOS Apple Silicon构建、bundle验证和ZIP上传。
- [ ] macOS Intel构建、bundle验证和ZIP上传。
- [ ] v0.4.0标签自动生成六个Release资产。
- [ ] 从GitHub重新下载三套ZIP并核对SHA-256。

## 真实运行验证

- [ ] 在v0.4.0测试包中模拟发现更高版本，确认公告、平台文件名和Release跳转。
- [ ] Windows手动覆盖后确认快捷方式、配置、凭据和任务保留。
- [ ] macOS手动替换`.app`后确认配置、Keychain和任务保留。
- [ ] GitHub不可访问时Core仍可离线查看、修改和导出已有任务。
- [ ] 三天真实邮件稳定性试运行。
