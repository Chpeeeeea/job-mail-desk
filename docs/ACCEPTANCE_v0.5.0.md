# JobMailDesk Core v0.5.0 验收记录

## 本地人工验收

- [x] 使用真实本地配置升级安装，原 `config.toml` 与 `state.db` 保持不变。
- [x] 设置页在当前纸片尺寸内打开，不再先放大原生窗口。
- [x] `0.5.0.dev1` 等预览版本号可被更新检查器正确解析；正式包使用 `0.5.0`。
- [x] Obsidian 临时占用人工台账时不会阻断整批邮箱扫描，下轮可继续补同步。
- [x] 内置词典加载结果为 520 家企业、129 个招聘项目、2825 个岗位和 4 个邮件模板。
- [x] Application Registry、批次归属、通用回执限制与 `unresolved` 缓冲区已接入扫描流程。
- [x] `CHANGELOG.md` 不进入终端用户 ZIP。

## 自动化验证

- [x] `uv run pytest`：132 项通过。
- [x] `scripts/secret-scan.ps1`：通过。
- [x] `git diff --check`：通过，仅有 Windows 行尾提示。
- [x] Windows x64 self-contained EXE：本地构建成功。
- [x] 本地 RC ZIP 与 `.sha256`：生成并核对成功。
- [x] Pull Request 的 GitHub Actions Windows x64 构建通过。
- [x] Pull Request 的 GitHub Actions macOS Apple Silicon 构建通过。
- [x] Pull Request 的 GitHub Actions macOS Intel 构建通过。
- [ ] GitHub Release 包含 3 个 ZIP 与 3 个 SHA-256 文件。

## 发布边界

- v0.5.0 继续标记为 Pre-release。
- Windows 包尚未进行代码签名；macOS 包尚未进行 Apple 签名和公证。
- Core 不依赖模型或 API；AI Research 仍不属于本次发布的必要能力。
- 邮箱正文、邮箱地址、授权码、私人通知链接和真实 Message-ID 不进入仓库或发布包。
