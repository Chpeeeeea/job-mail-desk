# Contributing

感谢参与 JobMailDesk。开始前请阅读 [项目规则](PROJECT_RULES.md) 与[维护、更新和发布规则](docs/MAINTENANCE.md)。

## 基本约束

1. 只使用匿名测试样例。
2. 保持 IMAP `readonly=True` 与 `BODY.PEEK`，不得修改邮件状态。
3. 修改解析、任务链、去重或同步逻辑时增加回归测试。
4. 保持公开 Research 数据与私人邮件数据分离。
5. 不直接向 `main` 开发；使用单一目标的短期分支和 Pull Request。
6. 用户可见变化必须更新 `CHANGELOG.md` 和对应使用文档。

## 提交前

```powershell
uv run pytest
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\secret-scan.ps1
git diff --check
```

Pull Request 应说明变化、原因、用户影响、验证结果、隐私/兼容性影响和回滚方法。三平台 GitHub Actions 全部通过后才能合并。
