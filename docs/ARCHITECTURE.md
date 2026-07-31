# 架构

```text
QQ / generic IMAP (read only)
          |
          v
in-memory parser + redaction
          |
          +--> tasks/<id>.md ----------> desktop list / week / month
          |                                  |
          |                                  +--> status / snooze
          |
          +--> state.db (dedupe, health)
          |
          +--> Obsidian managed block <---- checkbox import
          |
          +--> sanitized ResearchRequest --> Codex + vibe-web-research
```

## 分层

- `mail_reader.py`：只读 IMAP 适配层，不暴露写操作。
- `parser.py`：规则分类、时间窗解析、招聘字段提取。
- `task_service.py`：应用链、ghost application、改期合并和优先级。
- `markdown_store.py`：任务事实层与原子写入。
- `state.py`：去重、扫描健康状态。
- `exporter.py`：Obsidian 受管区和勾选回读。
- `research.py`：公开研究请求的最小化与脱敏闸门。
- `scheduler.py`：10 分钟扫描、整点刷新、早中晚简报。
- `ui_app.py`：受限 JavaScript 桥、桌面窗口、独立纸片进程和系统托盘。
- `paper_store.py`：独立纸片的 Markdown 事实层与可恢复备份。
- `image_store.py`：哈希寻址的本地笔记图片存储。
- `preferences.py`：主题、字体、字号、Markdown 档位和胶囊偏好。

## 桌面桥

只暴露：

```text
get_dashboard()
update_status(task_id, status)
snooze(task_id, until)
trigger_scan()
open_source(task_id)
open_obsidian(task_id)
get_health()
create_task(payload)
edit_task(task_id, payload)
set_capsule(compact)
peek_capsule(reveal)
create_paper(kind)
list_papers()
```

每张独立纸片使用单独的 `PaperApi`，仅能读写自己的 Markdown、打开关联纸片、保存本地图片、切换胶囊和更新非敏感偏好。纸片删除实际移动到本地 `trash/`，不会直接擦除。

Windows 上的每张纸片由一个轻量独立进程承载，API 在 WebView 启动前绑定。这样避开 WebView2 对运行时动态子窗口桥接的不稳定行为，也让单张纸片的窗口状态和故障彼此隔离。

不存在删除邮件、发送邮件、读取正文或返回授权码的接口。

## 数据恢复

Markdown 任务是事实层。删除 `state.db` 后可重建扫描状态和索引，但重新扫描前应先备份本地任务目录，避免历史消息窗口不足。配置和凭据彼此独立；凭据只存在 Windows Credential Manager。
