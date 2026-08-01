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

## 发布

- Windows包使用PyInstaller，启用Per-Monitor DPI v2。
- macOS包使用py2app，在真实macOS Runner分别生成arm64与Intel产物。
- 只有 Pull Request 的 Windows x64、macOS Apple Silicon、macOS Intel 检查全部通过后才能合并并创建版本标签；标签必须对应 `docs/RELEASE_NOTES_vX.Y.Z.md`。
- 标签构建必须自动发布三个平台 ZIP 及各自 SHA-256，共六个资产；当前未签名、公证或未完成三天试运行的版本必须标记为 prerelease。
- 发布前必须通过测试、秘密扫描、正常启动、缓存启动、正常退出、Obsidian往返同步和解析回归。
- 每个可验证的阶段性进展都必须更新`CHANGELOG.md`；禁止只有代码提交而没有面向用户的变更记录。
- 阶段验收通过后应形成独立、可回滚的Git提交并推送到GitHub，不把多个完成阶段长期积压在本地工作树。
- 推送前再次执行`pytest`、秘密扫描和`git diff --check`；远端推送成功后核对提交SHA与GitHub Actions状态。
