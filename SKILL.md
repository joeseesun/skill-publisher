---
name: skill-publisher
description: |
  一键发布 Claude Code Skill 到 GitHub，自动验证、补全文件、创建仓库、推送并验证可安装。当用户说"发布这个skill"、"publish skill"、"把skill发到GitHub"、"分享这个skill"、"/publish-skill"时触发。支持发布当前目录或指定路径的 skill。
---

# Skill Publisher

一键将 Claude Code Skill 发布到 GitHub，自动完成验证、补全、推送全流程。

## 前置条件

- `gh` CLI 已安装且已登录（`gh auth status`）
- Skill 目录包含有效的 `SKILL.md`（含 YAML frontmatter `name` + `description`）

## 发布流程

当用户要求发布 skill 时，运行发布脚本：

```bash
python3 ~/.claude/skills/skill-publisher/scripts/publish_skill.py <skill_dir>
```

### 确定 skill 目录

- 如果用户说"发布这个 skill"且当前在某个 skill 目录 → 用当前目录
- 如果用户指定了 skill 名称 → 在 `~/.claude/skills/` 下查找
- 如果不确定 → 问用户要发布哪个 skill

### 脚本自动完成的步骤

1. **验证** SKILL.md 的 YAML frontmatter（name + description）
2. **检查** gh CLI 就绪状态
3. **创建** LICENSE（MIT，如果缺少）
4. **生成** README.md（从 SKILL.md 提取，如果缺少）
5. **初始化** git（如果需要）
6. **创建** GitHub 公开仓库并推送
7. **验证** `npx skills add` 可发现

### 参数选项

| 参数 | 说明 |
|------|------|
| `--private` | 创建私有仓库（默认公开） |
| `--dry-run` | 仅检查，不实际发布 |
| `--skip-verify` | 跳过 npx skills 验证 |
| `--github-user USER` | 指定 GitHub 用户名（默认自动获取） |

### 更新已发布的 skill

对已有 GitHub 仓库的 skill 再次运行同一命令，脚本会检测到仓库已存在，自动 commit + push 更新。

## 使用示例

```
用户：发布 yt-search-download 这个 skill
执行：python3 ~/.claude/skills/skill-publisher/scripts/publish_skill.py ~/.claude/skills/yt-search-download

用户：把当前 skill 发到 GitHub
执行：python3 ~/.claude/skills/skill-publisher/scripts/publish_skill.py .

用户：先检查一下能不能发布
执行：python3 ~/.claude/skills/skill-publisher/scripts/publish_skill.py <dir> --dry-run
```

## README 质量检查（发布前必做）

**脚本只在 README 不存在时自动生成一个基础模板**。发布前，必须人工检查/撰写 README，确保它对陌生用户有价值。

### README 必须包含的 7 个要素

1. **价值主张（Hook）**：第一段就让用户明白"这能解决我什么问题"，用具体场景描述，避免抽象描述
2. **前置条件清单（checkbox 格式）**：用 `- [ ]` 列出所有依赖，让用户逐一确认。每条都要写清楚怎么装，不能只说"需要 xxx"
3. **完整安装步骤**：编号步骤，细到小白能跟着做。每步都提供验证命令（如 `--version`）
4. **自然语言使用示例**：展示 2-3 个用户会真实说出的句子，让人一眼看懂怎么触发
5. **致谢原作者**：如果 skill 基于第三方工具/库，必须注明原项目链接和作者
6. **必要的风险/限制说明**：写操作、账号相关、费用相关的风险需明确告知
7. **常见问题/Troubleshooting**：至少列出 3 个常见报错和解决方法，降低用户放弃率

### 双语判断原则

判断是否需要中英双语 README：

**需要双语的信号（满足任一即应写双语）：**
- Skill 的核心功能面向国际平台（Twitter、YouTube、Reddit、GitHub、HackerNews 等）
- SKILL.md 的 description 包含英文触发词
- 底层工具是英文开源项目，原作者是海外用户
- 技术命令本身是英文（如 CLI 工具）

**双语结构建议：**
```markdown
# skill-name

> One-line English description
> 中文一行描述

**[English](#english) | [中文](#中文)**

---

<a name="english"></a>
## English
[完整英文内容]

---

<a name="中文"></a>
## 中文
[完整中文内容]
```

### README 小白友好度检查

发布前逐项核对：

- [ ] 前置条件用 checkbox 格式列出，每条说明怎么安装
- [ ] 安装步骤有编号，每步有验证命令
- [ ] 使用示例是用户真实会说的话，不是技术命令
- [ ] 有 Troubleshooting 表格（问题 → 解决方法）
- [ ] 没有让用户"自行参考文档"而不给具体命令
- [ ] 跨平台差异有说明（如 macOS/Windows 路径不同）

### README 常见坏味道（避免）

- ❌ 直接把 SKILL.md 的 AI 指令（Output Formatting Rules、Rule:...）放进 README
- ❌ 第一段全是技术描述，没有用户能感受到的价值
- ❌ 前置要求写得模糊（如"需要 Chrome 扩展"但不说怎么装）
- ❌ 基于别人的项目但没有致谢
- ❌ 没有 Troubleshooting，用户遇到问题只能自己摸索
- ❌ 纯中文 README 但 skill 明显有国际用户群

### 发布工作流

```
1. 读取 SKILL.md，理解 skill 的功能和目标用户
2. 判断是否需要双语（参考双语判断原则）
3. 检查 README.md 是否存在，若存在则评估质量
4. 若 README 质量不达标（缺少上述要素），先重写 README
5. README 确认后，再运行发布脚本
```

## 发布完成后

向用户展示：
- GitHub 仓库 URL
- 安装命令：`npx skills add <user>/<skill-name>`
- 验证结果
