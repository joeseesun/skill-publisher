#!/usr/bin/env python3
"""
Skill Publisher — 检查并发布 Claude Code Skill 到 GitHub

用法:
  python3 publish_skill.py <skill_dir> [--github-user USER] [--public/--private] [--dry-run]

流程:
  1. 验证 SKILL.md (YAML frontmatter)
  2. 检查/创建 LICENSE
  3. 生成 README.md
  4. 初始化 git (如需)
  5. 创建 GitHub repo + push
  6. 验证 npx skills 可发现
"""

import os
import sys
import re
import subprocess
import argparse
import json
import datetime


def run(cmd, capture=True, check=True, cwd=None):
    """Run a shell command and return stdout."""
    if isinstance(cmd, list):
        r = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd)
    else:
        r = subprocess.run(cmd, shell=True, capture_output=capture, text=True, cwd=cwd)
    if check and r.returncode != 0:
        return None
    return r.stdout.strip() if capture else ""


def check_prerequisites():
    """Check gh CLI is available and authenticated."""
    if not run("which gh"):
        print("[错误] 未找到 gh CLI。安装方式: brew install gh", file=sys.stderr)
        return False
    auth = run("gh auth status 2>&1", check=False)
    if auth is None or "not logged" in (auth or ""):
        print("[错误] gh 未登录。运行: gh auth login", file=sys.stderr)
        return False
    return True


def parse_yaml_frontmatter(skill_md_path):
    """Extract name and description from SKILL.md YAML frontmatter.

    Returns (name, desc, yaml_error). yaml_error is None if parsing succeeded.
    Uses pyyaml for strict validation (same parser family as npx skills CLI).
    Falls back to regex if pyyaml is unavailable.
    """
    with open(skill_md_path, "r") as f:
        content = f.read()
    m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if not m:
        return None, None, "找不到 YAML frontmatter（需要 --- ... --- 包裹）"
    yaml_block = m.group(1)

    try:
        import yaml
        try:
            data = yaml.safe_load(yaml_block)
        except yaml.YAMLError as e:
            err_line = str(e).split("\n")[0]
            return None, None, (
                f"YAML 语法错误: {err_line}\n"
                "   常见原因: description 含未转义的引号或特殊字符\n"
                "   修复方法: 改用 | 块标量格式:\n"
                "     description: |\n"
                "       描述文字，可随意包含 \"引号\"、'单引号'、冒号: 等"
            )
        if not isinstance(data, dict):
            return None, None, "frontmatter 解析结果不是 dict"
        name = data.get("name")
        desc = data.get("description")
        if isinstance(desc, str):
            desc = " ".join(desc.split())  # normalize whitespace
        return name, desc, None

    except ImportError:
        pass  # pyyaml not installed, fall back to regex

    # Regex fallback (less strict, may miss YAML errors)
    name_m = re.search(r"^name:\s*(.+)$", yaml_block, re.MULTILINE)
    name = name_m.group(1).strip().strip("'\"") if name_m else None
    desc = None
    desc_m = re.search(r"^description:\s*[|>]\s*\n((?:[ \t]+.+\n?)+)", yaml_block, re.MULTILINE)
    if desc_m:
        lines = desc_m.group(1).split("\n")
        desc = " ".join(line.strip() for line in lines if line.strip())
    else:
        desc_m = re.search(r"^description:\s*(.+)$", yaml_block, re.MULTILINE)
        if desc_m:
            desc = desc_m.group(1).strip().strip("'\"")
    return name, desc, None


def get_github_user():
    """Get current GitHub username."""
    return run("gh api user --jq '.login'")


def validate_skill(skill_dir):
    """Validate skill directory structure."""
    errors = []
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        errors.append("缺少 SKILL.md")
        return errors, None, None

    name, desc, yaml_error = parse_yaml_frontmatter(skill_md)
    if yaml_error:
        errors.append(yaml_error)
        return errors, None, None
    if not name:
        errors.append("SKILL.md 缺少 YAML frontmatter 中的 name 字段")
    if not desc:
        errors.append("SKILL.md 缺少 YAML frontmatter 中的 description 字段")
    if desc and len(desc) < 20:
        errors.append(f"description 太短 ({len(desc)} 字符)，建议至少 50 字符")

    return errors, name, desc


def ensure_license(skill_dir, github_user):
    """Create MIT LICENSE if missing."""
    license_path = os.path.join(skill_dir, "LICENSE")
    if os.path.exists(license_path):
        return False
    year = datetime.datetime.now().year
    # Try to get full name from git config
    full_name = run("git config user.name") or github_user
    content = f"""MIT License

Copyright (c) {year} {full_name}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
    with open(license_path, "w") as f:
        f.write(content)
    return True


def extract_user_facing_sections(body):
    """
    Extract user-facing sections from SKILL.md body.
    Skips AI-only sections like output formatting rules, internal rules, etc.

    AI-only sections to skip (case-insensitive patterns):
    - "Output Formatting Rules"
    - Lines starting with "Rule:" or "**Rule:"
    - Sections about internal AI behavior

    User-facing sections to keep:
    - Quick Examples / 快速示例 / 示例
    - Commands / 命令
    - Usage / 使用方法
    - Features / 功能
    - 支持的平台 / Supported sites
    """
    AI_SECTION_PATTERNS = [
        r"output formatting rules",
        r"requirements",  # usually "Chrome open with..." which IS user-facing, keep it
    ]
    # Actually let's keep requirements — it's important for users.
    # Only skip pure AI-instruction sections:
    SKIP_SECTION_TITLES = {
        "output formatting rules",
        "output formatting",
        "formatting rules",
    }

    lines = body.split("\n")
    result_lines = []
    skip_section = False
    current_h2 = ""

    for line in lines:
        # Detect h2/h3 headings
        h2_match = re.match(r"^##\s+(.+)$", line)
        if h2_match:
            current_h2 = h2_match.group(1).strip().lower()
            skip_section = current_h2 in SKIP_SECTION_TITLES
            if skip_section:
                continue

        # Skip lines starting with "Rule:" (AI-facing rules)
        if re.match(r"^\*?\*?Rule:", line):
            continue

        if skip_section:
            continue

        result_lines.append(line)

    return "\n".join(result_lines).strip()


def generate_readme(skill_dir, name, desc, github_user):
    """Generate README.md from SKILL.md content."""
    readme_path = os.path.join(skill_dir, "README.md")
    if os.path.exists(readme_path):
        return False

    # Read SKILL.md body (after frontmatter)
    skill_md = os.path.join(skill_dir, "SKILL.md")
    with open(skill_md, "r") as f:
        content = f.read()
    raw_body = re.sub(r"^---\s*\n.*?\n---\s*\n", "", content, flags=re.DOTALL).strip()

    # Extract user-facing content (strip AI-only sections)
    user_body = extract_user_facing_sections(raw_body)

    # Build tagline from description (first sentence)
    if "。" in desc:
        tagline = desc.split("。")[0] + "。"
    elif ". " in desc:
        tagline = desc.split(". ")[0] + "."
    else:
        tagline = desc[:120]

    readme = f"""# {name}

> {tagline}

## 安装

```bash
npx skills add {github_user}/{name}
```

## 前置要求

<!-- TODO: 填写该 Skill 所需的前置条件（工具、账号、配置等） -->
- Claude Code 已安装
- （在此补充其他依赖）

## 使用方式

安装后，在 Claude Code 中用自然语言描述你的需求即可，例如：

<!-- TODO: 填写 2-3 个典型的自然语言触发示例 -->
```
"..."
"..."
```

{user_body}

## License

MIT

## 📱 关注作者

如果这个项目对你有帮助，欢迎关注我获取更多 AI 工具分享：

- **X (Twitter)**: [@vista8](https://x.com/vista8)
- **微信公众号「向阳乔木推荐看」**:

<p align="center">
  <img src="https://github.com/joeseesun/terminal-boost/raw/main/assets/wechat-qr.jpg?raw=true" alt="向阳乔木推荐看公众号二维码" width="300">
</p>
"""
    with open(readme_path, "w") as f:
        f.write(readme)
    return True


def init_git(skill_dir):
    """Initialize git repo if needed."""
    git_dir = os.path.join(skill_dir, ".git")
    if os.path.isdir(git_dir):
        return False
    run(f"git init", cwd=skill_dir)
    return True


def create_and_push(skill_dir, name, desc, github_user, public=True):
    """Create GitHub repo and push."""
    visibility = "--public" if public else "--private"

    # Check if repo already exists
    existing = run(f"gh repo view {github_user}/{name} --json url --jq '.url' 2>/dev/null", check=False)
    if existing and "github.com" in existing:
        print(f"[信息] 仓库已存在: {existing}")
        # Just push updates
        run("git add -A", cwd=skill_dir)
        status = run("git status --porcelain", cwd=skill_dir)
        if status:
            run('git commit -m "Update skill"', cwd=skill_dir)
        # Check if remote exists
        remote = run("git remote get-url origin 2>/dev/null", cwd=skill_dir, check=False)
        if not remote:
            run(f"git remote add origin https://github.com/{github_user}/{name}.git", cwd=skill_dir)
        run("git push -u origin main 2>&1", cwd=skill_dir, check=False)
        run("git push -u origin HEAD:main 2>&1", cwd=skill_dir, check=False)
        return existing

    # Short description for GitHub (max 350 chars)
    gh_desc = desc[:150] if len(desc) > 150 else desc

    # Commit all files
    run("git add -A", cwd=skill_dir)
    run(f'git commit -m "Initial release: {name}"', cwd=skill_dir)

    # Create repo and push
    result = run(
        ["gh", "repo", "create", f"{github_user}/{name}", visibility,
         "--description", gh_desc, "--source", ".", "--push"],
        cwd=skill_dir, check=False
    )
    if result and "github.com" in result:
        url = result.strip().split("\n")[0]
        return url
    print(f"[错误] 创建仓库失败: {result}", file=sys.stderr)
    return None


def verify_skill(github_user, name):
    """Verify skill is installable via npx skills.

    Note: --list only checks repo reachability, not YAML validity.
    We parse the actual output to confirm the skill name was found AND parsed.
    """
    result = run(f"npx skills add {github_user}/{name} --list 2>&1", check=False)
    if not result:
        return False, "npx skills 命令执行失败或超时"
    # Must see both "Found N skill" and the skill name — confirms YAML was parsed OK
    if "Found" in result and name in result:
        return True, None
    if "No valid skills found" in result:
        return False, "YAML 解析失败（npx skills 找不到有效 skill）— 检查 SKILL.md frontmatter"
    if name in result:
        return True, None
    return False, f"skill 名称 '{name}' 未出现在输出中"


def main():
    parser = argparse.ArgumentParser(description="发布 Claude Code Skill 到 GitHub")
    parser.add_argument("skill_dir", help="Skill 目录路径")
    parser.add_argument("--github-user", help="GitHub 用户名 (默认自动获取)")
    parser.add_argument("--private", action="store_true", help="创建私有仓库 (默认公开)")
    parser.add_argument("--dry-run", action="store_true", help="仅检查，不实际发布")
    parser.add_argument("--skip-verify", action="store_true", help="跳过 npx skills 验证")
    args = parser.parse_args()

    skill_dir = os.path.abspath(args.skill_dir)
    if not os.path.isdir(skill_dir):
        print(f"[错误] 目录不存在: {skill_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n🔍 检查 Skill: {skill_dir}\n")

    # Step 1: Validate
    errors, name, desc = validate_skill(skill_dir)
    if errors:
        print("❌ 验证失败:")
        for e in errors:
            print(f"   - {e}")
        sys.exit(1)
    print(f"✅ SKILL.md 验证通过 (name: {name})")

    # Step 2: Prerequisites
    if not check_prerequisites():
        sys.exit(1)
    print("✅ gh CLI 已就绪")

    github_user = args.github_user or get_github_user()
    if not github_user:
        print("[错误] 无法获取 GitHub 用户名", file=sys.stderr)
        sys.exit(1)
    print(f"✅ GitHub 用户: {github_user}")

    # Step 3: Ensure LICENSE
    if ensure_license(skill_dir, github_user):
        print("📄 已创建 LICENSE (MIT)")
    else:
        print("✅ LICENSE 已存在")

    # Step 4: Generate README
    if generate_readme(skill_dir, name, desc, github_user):
        print("📄 已生成 README.md")
    else:
        print("✅ README.md 已存在")

    if args.dry_run:
        print(f"\n🏁 Dry run 完成。实际发布命令:")
        print(f"   python3 {__file__} {skill_dir}")
        return

    # Step 5: Git init
    if init_git(skill_dir):
        print("📦 已初始化 git 仓库")
    else:
        print("✅ git 仓库已存在")

    # Step 6: Create repo and push
    public = not args.private
    print(f"\n🚀 发布到 GitHub ({'公开' if public else '私有'})...")
    url = create_and_push(skill_dir, name, desc, github_user, public=public)
    if not url:
        print("❌ 发布失败", file=sys.stderr)
        sys.exit(1)
    print(f"✅ GitHub: {url}")

    # Step 7: Verify
    if not args.skip_verify:
        print("\n🔎 验证 npx skills 可安装...")
        ok, verify_err = verify_skill(github_user, name)
        if ok:
            print("✅ 验证通过（YAML 解析正常，可安装）")
        else:
            print(f"❌ 验证失败: {verify_err}", file=sys.stderr)
            print("   请检查 SKILL.md frontmatter，修复后重新运行脚本更新", file=sys.stderr)

    # Summary
    print(f"\n{'='*60}")
    print(f"🎉 发布成功！")
    print(f"   仓库: {url}")
    print(f"   安装: npx skills add {github_user}/{name}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
