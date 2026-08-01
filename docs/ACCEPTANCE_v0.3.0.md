# JobMailDesk Core v0.3.0 验收记录

验收日期：2026-08-01  
验收平台：Windows 11 x64

## 已验证

| 领域 | 验收证据 | 结果 |
| --- | --- | --- |
| IMAP只读 | 在线诊断显示`readonly=True + BODY.PEEK`，扫描前后`UNSEEN / UIDVALIDITY / UIDNEXT`不变 | 通过 |
| 重复扫描 | 连续正式扫描`8 fetched / 8 skipped / 0 tasks_updated`；任务数保持10，研究待处理保持0 | 通过 |
| 时间解析 | 匿名回归覆盖百度`19:00–21:00`、海信跨日窗口、科大讯飞有效期、慧策旺店通`24:00`截止 | 通过 |
| 误判保护 | “取消订阅”“作弊将取消资格”、条件性拒绝和模板中的Offer词不改变流程状态 | 通过 |
| 状态持久化 | 完成、恢复、忽略、改期、解析器重放和重复Message-ID均有回归测试 | 通过 |
| 实时同步 | UI和`task-update`共用写回服务；任务Markdown、本地总览、进展与Obsidian在一次更新中刷新 | 通过 |
| Obsidian往返 | 稳定`jobmaildesk:<id>`复选框支持完成与恢复，手写区保留 | 通过 |
| 缓存启动 | 胶囊启动即时显示缓存任务数，展开后直接呈现周历，无空白任务列表 | 通过 |
| 单实例 | 连续启动前后均为同一组PyInstaller父/子进程，没有第二套窗口或调度器 | 通过 |
| 正常退出 | 标准窗口关闭消息被接受，4秒后进程数为0；日志无`SchedulerNotRunningError`或未处理异常 | 通过 |
| 高DPI | Windows进程在WebView导入前启用Per-Monitor DPI v2；正式界面完成视觉检查 | 通过 |
| Core边界 | 默认`research_enabled=false`，不需要模型、API、Codex或OpenCLI | 通过 |
| 隐私扫描 | 发布扫描未发现邮箱、个人路径、授权码、私人Token URL或长数字标识 | 通过 |
| Windows产物 | 生成EXE、版本ZIP、SHA-256文件，并检查ZIP内含快速开始、依赖、隐私、许可和Changelog | 通过 |
| 旧纸片清理 | 独立待办纸/笔记纸源码资源与数据目录初始化已从Core移除 | 通过 |
| 自动测试 | 45项Core测试全部通过 | 通过 |

## 需要远端或真实设备完成

| 项目 | 原因 | 完成方式 |
| --- | --- | --- |
| macOS arm64 / Intel安装包 | Windows不能交叉生成或运行原生`.app` | 推送后由GitHub Actions真实macOS Runner构建并下载验证 |
| 未安装Python的全新Windows | 当前验收机存在开发环境 | 在朋友电脑或Windows Sandbox中双击发布ZIP内EXE完成首次配置 |
| 三天稳定性试运行 | 必须经过真实时间 | 保持每10分钟扫描，检查无重复卡片、漏提醒和异常退出 |

## 发布规则

- 每个可验证阶段先更新`CHANGELOG.md`，再运行测试、秘密扫描和`git diff --check`。
- 阶段通过后形成独立提交并推送GitHub，核对远端提交SHA与Actions状态。
- v0.3.0是Core版；Research不作为本次安装包验收范围。

