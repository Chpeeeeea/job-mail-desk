# JobMailDesk Core 项目规则

## 事实层

- `%LOCALAPPDATA%/JobMailDesk/tasks/<id>.md`（macOS 为 `~/Library/Application Support/JobMailDesk/tasks/<id>.md`）是任务事实层。
- SQLite只保存邮件去重、扫描状态和可重建索引，不作为任务正文来源。
- 同一邮件使用`source_message_hash`合并；同一公司、岗位、项目与阶段使用稳定申请链，禁止重复建卡。

## 对话进展写回

用户明确说明某项求职进展时，可以直接更新本地任务，不要求用户再去卡片或Obsidian重复操作：

- “完成了”设为`done`；保留灰色勾选，并允许恢复。
- “恢复/尚未完成”在有时间时设为`planned`，否则设为`needs_review`。
- “改到某时”更新原任务时间并设`change_type: update`。
- “忽略/不用了”设为`irrelevant`，邮件重放不得复活。
- 只有官方活动取消才设为`cancelled`。

更新后必须检查：桌面卡片、周/月日历、企业进展、Obsidian受管区。Obsidian依靠`<!-- jobmaildesk:<id> -->`稳定标记同步复选框；手写区不得覆盖。

程序内置的唯一写回入口是：

```text
jobmaildesk task-list --company <公司> --role <岗位> --stage <阶段>
jobmaildesk task-update <稳定任务ID> [字段参数]
```

`task-list`只读取结构化任务，不读取邮件正文；`task-update`必须使用完整稳定ID，禁止按模糊名称批量修改。一次更新会统一写回任务事实层、本地总览、周/月日历数据、企业进展输出与可选Obsidian输出。桌面卡片也调用同一个写回服务，避免CLI和UI产生两套状态逻辑。

## 邮件与解析

- IMAP只允许`readonly=True`与`BODY.PEEK`，不得删除、移动、回复或标记已读。
- 正文只在内存解析；任务仅保存结构化字段和脱敏证据。
- 明确时间自动进入`planned`；没有明确时间才进入`needs_review`。
- 解析器升级使用版本化重放，只重放回看窗口，并按消息哈希修正原任务。

## Core与Research边界

- Core默认不需要模型、API、Codex、OpenCLI或境外网络。
- Research是可选插件；Core不得自动创建研究任务。
- 公开研究只携带公司、岗位、项目、年份、阶段；禁止邮件正文、邮箱、手机号、通行证和私人URL。

## 更新边界

- Core业务功能不依赖GitHub；自动版本检查是可关闭的辅助网络请求，失败不得阻塞邮件扫描、日历、任务或Obsidian。
- 每24小时最多自动检查一次；手动检查由用户明确触发，不携带邮件、任务、凭据、本地路径或Obsidian内容。
- 只在本项目Release同时存在当前平台ZIP和同名`.sha256`时提示新版本，并展示公告与Release入口。
- Core不得自动下载、解包、执行、覆盖或重启安装；用户退出程序后手动覆盖应用文件。
- 更新说明必须明确本地数据目录、系统凭据库和Obsidian不参与覆盖，不得声称具备自动安装能力。

## 发布

- 完整维护流程以`docs/MAINTENANCE.md`为准；本节是不可跳过的发布闸门。
- `main`是唯一正式主线，不直接在`main`开发；所有阶段修改必须通过短期分支和Pull Request进入主线。
- 必须区分“推送分支”“合并主线”和“发布安装包”：阶段提交需要推送，验收完成需要合并，只有可交付的程序变化才创建新Release。
- 本地验收未全部结束时进入 **Release Freeze**：只允许本地 RC 包、功能分支、Draft/Ready PR 和 Actions 构建产物，禁止创建版本标签或 Release。
- 同一轮集中反馈默认合并为一个版本发布；不得因为每次小修复、文档调整或尚待个人真实数据验证的中间状态反复增加 PATCH Release。
- 只有本地验收清单全部关闭、真实数据回归完成、版本范围冻结并明确判定“release-ready”后，才允许一次性创建版本标签；发布后新增问题进入下一轮版本，不静默替换资产。
- Windows包使用PyInstaller，启用Per-Monitor DPI v2。
- macOS包使用py2app，在真实macOS Runner分别生成arm64与Intel产物。
- 只有 Pull Request 的 Windows x64、macOS Apple Silicon、macOS Intel 检查全部通过后才能合并并创建版本标签；标签必须对应 `docs/RELEASE_NOTES_vX.Y.Z.md`。
- 标签构建必须自动发布三个平台 ZIP 及各自 SHA-256，共六个资产；当前未签名、公证或未完成三天试运行的版本必须标记为 prerelease。
- 发布前必须通过测试、秘密扫描、正常启动、缓存启动、正常退出、Obsidian往返同步和解析回归。
- 每个可验证的阶段性进展都必须更新`CHANGELOG.md`；禁止只有代码提交而没有面向用户的变更记录。
- 阶段验收通过后应形成独立、可回滚的Git提交并推送到GitHub，不把多个完成阶段长期积压在本地工作树。
- 推送前再次执行`pytest`、秘密扫描和`git diff --check`；远端推送成功后核对提交SHA与GitHub Actions状态。
- 已发布标签和资产不得覆盖、删除或重新指向；发现问题时发布更高PATCH版本。
- 合并或发布后必须验证README入口、更新公告和下载链接，确保用户知道如何使用与升级。
