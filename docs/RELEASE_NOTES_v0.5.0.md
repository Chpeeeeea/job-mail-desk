# JobMailDesk Core v0.5.0

> 发布类型：Pre-release。Core 可完全本地运行，不依赖模型或 API；Windows 尚未代码签名，macOS 尚未完成 Apple 签名与公证。

## 本次更新

- 更新检查现已支持 `dev`、`alpha`、`beta` 和 `rc` 预览版本号，不再把本地候选版识别为非法版本。
- Obsidian 台账被其他程序短暂占用时，邮箱扫描不再整体失败；程序会重试并在下轮补同步。
- 设置页在当前纸片内直接打开，不再先放大原生窗口。
- 内置 520 家企业、129 个招聘项目和 2825 个岗位名称，国内离线环境无需模型 API。
- 设置页新增企业与岗位词典管理，可选择个人 XLSX 秋招表、指定工作表并在本机编译启用。
- 正式启用 Application Registry：邮件先整批解析，再按企业、项目、岗位、职位编号和批次上下文归属。
- 通用网申回执不再独立创建申请；无法唯一判断的邮件进入隐私安全的待归属缓冲区。
- 新增待归属 CLI 闭环：`unresolved-list`、`unresolved-resolve`、`unresolved-ignore`。
- 任务新增 canonical `application_key`，旧 `application_id`、已有任务和 Obsidian 标记继续兼容。
- 词典查找使用预构建索引和 NFKC 标准化，减少大型词典的重复扫描开销。

## 个人词典优先级

```text
内置基础词典 → imported 表格导入 → 旧版根目录覆盖 → manual 人工覆盖
```

手工维护规则始终拥有最高优先级。导入过程不会保存源表路径，也不会复制整张工作簿。

## 安全与兼容

- 邮箱保持 IMAP 只读，不删除、移动、回复或标记已读。
- 待归属记录不保存邮件正文、发件人地址、私人链接或认证参数。
- 多个旧申请 ID、职位编号冲突或跨项目冲突都会停止自动归属，等待人工处理。
- XLSX 编译限制为 50 MB 文件、200 MB 解压体积和 100000 行。
- `CHANGELOG.md` 仅用于仓库和 Release 展示，不再复制进用户安装包。

## 升级说明

安装新版本后无需迁移现有 Markdown。扫描器会在唯一映射成立时为旧任务补充 canonical application key；映射不唯一时保持原数据不变。

本版本已完成 Windows 本地人工验收。推送 `v0.5.0` 标签后，由 GitHub Actions 分别构建 Windows x64、macOS Apple Silicon 与 macOS Intel 包；三个平台全部通过后才创建 Pre-release。
