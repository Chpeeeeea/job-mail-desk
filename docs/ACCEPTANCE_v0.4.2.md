# v0.4.2 验收记录

## 本地验收

- [x] 66 项 pytest 通过。
- [x] 秘密扫描未发现邮箱、个人路径、授权码、私人 URL 或长数字标识。
- [x] `git diff --check` 通过。
- [x] 最近 30 天只读回看读取 43 封邮件，重复执行时 43 封全部跳过、0 条重复更新。
- [x] 百度两条无时间申请进展重复同步后仍保持 `confirmed`。
- [x] 已忽略营销任务重复扫描后仍保持 `irrelevant`。
- [x] 旧 `research.enabled=true` 被 Core 忽略，扫描器写入研究队列的路径已移除。
- [x] 首次扫描使用 30 天窗口，成功后恢复配置的 3 天窗口。
- [x] expired 任务从桌面/Obsidian 待办消失，并保留在企业进展中。
- [x] needs_review 且无明确时间的简历池记录不进入待办，只保留在待确认和企业进展。
- [x] 相对 24/48/72 小时截止按收件时间换算，超过 7 天的无时间旧测评退出注意区。
- [x] “邀请于 A，于 B 失效”解析为有效窗口，结束后只保留在企业进展历史。
- [x] `在线`、`AI`、`27届校招` 不再作为企业名，多益网络与小鹏汽车匿名回归样例通过。
- [x] 网易雷火与网易互娱归入同一母企业总览，但生成不同申请链；流程清单与官网操作句不再污染阶段和岗位。
- [x] Obsidian、独立求职进展和本地总览完成统一导出。
- [x] Windows self-contained EXE 构建成功，离线 doctor 可读取现有配置与凭据状态。
- [x] Windows ZIP 包含快速开始、依赖、隐私、Changelog、MIT License 与中文许可说明，同名 SHA-256 校验一致。

## 远端与发布验收

- [ ] Pull Request 的 Windows x64 构建通过。
- [ ] Pull Request 的 macOS Apple Silicon 构建通过。
- [ ] Pull Request 的 macOS Intel 构建通过。
- [ ] `v0.4.2` 标签生成三个平台 ZIP 和三个 SHA-256 文件。
- [ ] 从 Release 重新下载并核对六个资产。

当前未完成代码签名、Apple 公证和三天真实环境试运行，因此必须保持 prerelease。
