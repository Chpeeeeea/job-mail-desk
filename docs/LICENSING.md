# JobMailDesk 许可说明

本文帮助用户和贡献者理解 JobMailDesk 的授权范围。正式授权始终以仓库根目录的
[`LICENSE.md`](../LICENSE.md) 为准；本文不替代许可证正文，也不构成法律意见。

## 许可结论

JobMailDesk 使用 **MIT License** 发布：

| 行为 | 是否允许 | 条件 |
| --- | --- | --- |
| 个人使用 | 允许 | 保留许可证即可 |
| 公司内部使用 | 允许 | 保留许可证即可 |
| 修改源码 | 允许 | 分发时保留版权与许可声明 |
| 复制与再分发 | 允许 | 保留版权与许可声明 |
| 发布修改版 | 允许 | 不得移除原版权与许可声明 |
| 商业销售或集成 | 允许 | 保留版权与许可声明 |
| 提供担保或追责原作者 | 不属于授权内容 | 软件按“原样”提供 |

## 你可以做什么

- 自己安装并处理个人求职邮件；
- 帮朋友配置或分发原始安装包；
- Fork 仓库并修改邮箱适配、解析规则或界面；
- 将 JobMailDesk 集成到内部工具或商业产品；
- 以免费或收费方式分发修改版；
- 使用源码进行教学、研究、测试或二次开发。

## 你必须保留什么

当你复制、分发或发布 JobMailDesk 的全部或主要部分时，应同时保留：

```text
MIT License
Copyright (c) 2026 JY
```

以及 [`LICENSE.md`](../LICENSE.md) 中完整的 MIT 授权文本。

这不要求你的整个产品都改成 MIT；但 JobMailDesk 的原始或衍生部分仍应携带上述声明。

## 发布修改版前的检查清单

- [ ] 没有删除 `Copyright (c) 2026 JY`；
- [ ] 发布包包含完整 `LICENSE.md`；
- [ ] 修改版没有暗示得到原作者官方认证；
- [ ] 没有把真实邮箱、授权码、私人 URL 或求职记录提交到公开仓库；
- [ ] 第三方依赖和素材仍分别满足其自身许可证；
- [ ] 如果更换项目名称或图标，README 和安装包中的标识已经同步更新。

## MIT 不等于放弃版权

MIT 是作者基于版权授予的宽松许可。版权仍属于相应作者；许可证只是允许接收者在满足保留声明这一条件后使用、修改、分发和商业化软件。

`Copyright (c) 2026 JY` 是 JobMailDesk 当前的项目版权声明。贡献者提交的原创代码仍可能包含其依法享有的权利，除非另有贡献协议约定。

## 不在 MIT 授权范围内的内容

JobMailDesk 的 MIT License 只覆盖本仓库中由项目作者有权授权的代码和文档，不会自动授予：

- 第三方项目的名称、商标、Logo、截图或宣传素材；
- 用户自己的邮件、简历、求职记录和 Obsidian 内容；
- 邮件发送方提供的测评题、面试材料、私人通知链接或附件；
- 通过可选 Research 扩展访问到的网页、帖子、视频或付费题库内容；
- 操作系统、WebView2、WebKit 或其他外部运行环境的再许可权。

第三方依赖与设计参考见 [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。

## PaperTodo 参考边界

[PaperTodo](https://github.com/snownico0722/PaperTodo) 使用 PolyForm Noncommercial 1.0.0 与其个人职业使用附加许可，并明确声明为 source-available，而不是 OSI 批准的开源许可证。

JobMailDesk 只研究了纸片式桌面交互和 README 信息架构等高层思路，没有复制 PaperTodo 的代码、文案、截图、图标、动画、配色资产或其他受保护表达。因此，JobMailDesk 可以继续独立采用 MIT License。

如果未来需要直接复用 PaperTodo 代码，必须先重新评估其非商业限制；不能把该代码仅以 JobMailDesk 的 MIT License 重新发布。

## 常见问题

### 可以发给朋友使用吗？

可以。原始安装包或你制作的修改版都可以分发，但发布包应包含 `LICENSE.md`。

### 可以在公司内部使用吗？

可以。MIT 不限制商业场景或组织部署。

### 可以收费吗？

可以。可以销售副本、提供集成或服务，但仍需保留原版权和许可证声明。

### 修改后必须公开源码吗？

MIT 本身不要求公开修改后的源码。是否公开由分发者自行决定，但原 MIT 声明仍需保留。

### 可以使用 JobMailDesk 名称和现有界面截图吗？

仓库中的自有文档和匿名演示截图随项目按 MIT 发布，但不得暗示修改版是 JY 官方发布。第三方商标和素材仍服从各自权利边界。

### 邮箱内容也属于 MIT 吗？

不属于。用户邮件、简历、招聘通知和私人链接不是本项目授权的作品，也不应因为被软件处理而进入公开仓库。

## English summary

JobMailDesk is licensed under the MIT License. You may use, copy, modify,
merge, publish, distribute, sublicense, and sell copies of the software,
provided that the original copyright and permission notice are retained in
copies or substantial portions of the software.

The license covers only material that the JobMailDesk copyright holder is able
to license. It does not grant rights to user email, private recruiting content,
third-party trademarks, external websites, or referenced projects. The
complete and controlling terms are in [`LICENSE.md`](../LICENSE.md).
