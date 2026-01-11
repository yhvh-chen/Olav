#!/usr/bin/env python3
"""
OLAV to Agent Platform Skill Migration Tool
将OLAV系统迁移到Claude Code或其他Agent平台的Skill格式

使用方式:
    python scripts/migrate_olav_to_agent.py --platform claude --dry-run
    python scripts/migrate_olav_to_agent.py --platform claude
    python scripts/migrate_olav_to_agent.py --platform all
"""

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)-8s: %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class MigrationConfig:
    """迁移配置"""
    platform: str  # 'claude', 'cursor', 'all'
    agent_dir: str = ".olav"
    dry_run: bool = False
    verbose: bool = False
    backup: bool = True


class OlavMigrator:
    """OLAV迁移工具"""

    def __init__(self, workspace: Path, config: MigrationConfig):
        self.workspace = Path(workspace)
        self.config = config
        self.agent_dir = self.workspace / config.agent_dir
        self.migration_log: list[dict[str, str]] = []
        self.errors: list[str] = []

    def run_migration(self) -> bool:
        """执行完整迁移流程"""
        logger.info(f"🚀 开始迁移: {self.config.platform}")
        logger.info(f"   工作目录: {self.workspace}")
        logger.info(f"   Agent目录: {self.agent_dir}")
        logger.info(f"   干运行模式: {self.config.dry_run}\n")

        steps = [
            ("备份现有文件", self.backup_files),
            ("迁移Skill目录结构", self.migrate_skills),
            ("迁移Commands格式", self.migrate_commands),
            ("迁移系统指令", self.migrate_system_instruction),
            ("更新硬编码路径", self.update_hardcoded_paths),
            ("创建配置文件", self.create_config_files),
            ("生成报告", self.generate_report),
        ]

        for step_name, step_func in steps:
            logger.info(f"[{steps.index((step_name, step_func)) + 1}/{len(steps)}] {step_name}...")
            try:
                if not step_func():
                    logger.error(f"   ❌ {step_name} 失败")
                    return False
                logger.info(f"   ✅ {step_name} 完成\n")
            except Exception as e:
                logger.error(f"   ❌ {step_name} 异常: {e}")
                self.errors.append(f"{step_name}: {str(e)}")
                return False

        return True

    def backup_files(self) -> bool:
        """备份现有文件"""
        if not self.config.backup:
            logger.info("   跳过备份 (--no-backup)")
            return True

        if self.config.dry_run:
            logger.info("   [DRY-RUN] 将备份到: .backup/")
            return True

        backup_dir = self.workspace / f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 备份.olav目录
        if self.agent_dir.exists():
            logger.info(f"   备份 {self.agent_dir} → {backup_dir.name}")
            shutil.copytree(self.agent_dir, backup_dir / self.config.agent_dir)
            self._log_action("backup", str(self.agent_dir), str(backup_dir))

        return True

    def migrate_skills(self) -> bool:
        """迁移Skill目录结构: skills/*.md → skills/*/SKILL.md"""
        skills_dir = self.agent_dir / "skills"

        if not skills_dir.exists():
            logger.info("   跳过: skills目录不存在")
            return True

        # 扫描现有的.md文件
        md_files = list(skills_dir.glob("*.md"))

        for md_file in md_files:
            skill_name = md_file.stem
            skill_dir = skills_dir / skill_name
            target_file = skill_dir / "SKILL.md"

            if target_file.exists():
                logger.info(f"   跳过: {skill_name} 已在新格式")
                continue

            if self.config.dry_run:
                logger.info(f"   [DRY-RUN] 将创建: {target_file.relative_to(self.workspace)}")
                continue

            # 创建目录并移动文件
            skill_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(md_file, target_file)
            logger.info(f"   ✓ {skill_name}/SKILL.md")
            self._log_action("migrate_skill", str(md_file), str(target_file))

        return True

    def migrate_commands(self) -> bool:
        """迁移Commands格式: .py → .md"""
        commands_dir = self.agent_dir / "commands"

        if not commands_dir.exists():
            logger.info("   跳过: commands目录不存在")
            return True

        py_files = list(commands_dir.glob("*.py"))

        for py_file in py_files:
            md_file = py_file.with_suffix(".md")

            if md_file.exists():
                logger.info(f"   跳过: {py_file.name} 的.md版本已存在")
                continue

            if self.config.dry_run:
                logger.info(f"   [DRY-RUN] 将创建: {md_file.relative_to(self.workspace)}")
                continue

            # 生成Markdown版本
            md_content = self._convert_py_to_md(py_file)

            if md_content:
                md_file.write_text(md_content)
                logger.info(f"   ✓ {md_file.name}")
                self._log_action("migrate_command", str(py_file), str(md_file))

        return True

    def migrate_system_instruction(self) -> bool:
        """迁移系统指令: OLAV.md → CLAUDE.md"""
        old_file = self.agent_dir / "OLAV.md"
        new_file = self.workspace / "CLAUDE.md"

        if not old_file.exists():
            logger.info("   跳过: OLAV.md不存在")
            return True

        if new_file.exists():
            logger.info("   跳过: CLAUDE.md已存在")
            return True

        if self.config.dry_run:
            logger.info("   [DRY-RUN] 将创建: CLAUDE.md")
            return True

        # 复制并更新内容
        content = old_file.read_text()
        # 更新内容中的硬编码路径
        content = content.replace(f"{self.config.agent_dir}/", "agent_dir/")
        content = content.replace(f".{self.config.agent_dir}/", "agent_dir/")

        new_file.write_text(content)
        logger.info("   ✓ CLAUDE.md 创建")
        self._log_action("migrate_system_instruction", str(old_file), str(new_file))

        return True

    def update_hardcoded_paths(self) -> bool:
        """更新硬编码路径为settings.agent_dir"""
        if self.config.dry_run:
            logger.info("   [DRY-RUN] 将扫描并更新硬编码路径")
            return True

        python_files = list((self.workspace / "src").rglob("*.py"))
        agent_dir_str = f'"{self.config.agent_dir}"'

        updated_count = 0
        for py_file in python_files:
            content = py_file.read_text()
            original = content

            # 替换硬编码路径
            content = content.replace(
                f'Path("{self.config.agent_dir}/")',
                'Path(settings.agent_dir) /'
            )
            content = content.replace(
                f"Path('{self.config.agent_dir}/')",
                "Path(settings.agent_dir) /"
            )

            if content != original:
                py_file.write_text(content)
                logger.info(f"   ✓ {py_file.relative_to(self.workspace)}")
                updated_count += 1
                self._log_action("update_path", str(py_file), "settings.agent_dir")

        if updated_count == 0:
            logger.info("   (无需更新)")

        return True

    def create_config_files(self) -> bool:
        """创建平台特定的配置文件"""
        if self.config.dry_run:
            logger.info(f"   [DRY-RUN] 将创建{self.config.platform}配置文件")
            return True

        configs = {
            "claude": self._create_claude_config,
            "cursor": self._create_cursor_config,
        }

        if self.config.platform == "all":
            for platform, creator in configs.items():
                creator()
        elif self.config.platform in configs:
            configs[self.config.platform]()

        return True

    def _create_claude_config(self):
        """创建Claude Code配置文件"""
        config = {
            "platform": "Claude Code",
            "agent_dir": self.config.agent_dir,
            "features": {
                "skills": "nested_directory",
                "commands": "markdown",
                "system_instruction": "CLAUDE.md",
                "embeddings": "ollama",
            },
            "integration": {
                "load_system_instruction": "Load CLAUDE.md as system prompt",
                "access_skills": "Use /skill_name notation",
                "access_commands": "Use /command_name notation",
            }
        }

        config_file = self.workspace / ".claude-code-config.json"
        config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        logger.info("   ✓ .claude-code-config.json 创建")

    def _create_cursor_config(self):
        """创建Cursor IDE配置文件"""
        config = {
            "platform": "Cursor IDE",
            "agent_dir": self.config.agent_dir,
            "settings": {
                "enableSkills": True,
                "skillDirectory": f"{self.config.agent_dir}/skills",
                "systemPromptFile": "CLAUDE.md",
            }
        }

        config_file = self.workspace / ".cursor-config.json"
        config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False))
        logger.info("   ✓ .cursor-config.json 创建")

    def generate_report(self) -> bool:
        """生成迁移报告"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "platform": self.config.platform,
            "dry_run": self.config.dry_run,
            "workspace": str(self.workspace),
            "agent_dir": self.config.agent_dir,
            "actions": self.migration_log,
            "errors": self.errors,
            "summary": {
                "total_actions": len(self.migration_log),
                "total_errors": len(self.errors),
                "status": "success" if not self.errors else "failed",
            }
        }

        # 保存为JSON
        report_file = self.workspace / f"migration_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        if not self.config.dry_run:
            report_file.write_text(json.dumps(report, indent=2, ensure_ascii=False))
            logger.info(f"   ✓ 报告已保存: {report_file.name}")

        return True

    def _convert_py_to_md(self, py_file: Path) -> str:
        """将Python命令转换为Markdown格式"""
        content = py_file.read_text()
        cmd_name = py_file.stem

        # 提取docstring作为描述
        description = "Command description"
        if '"""' in content:
            start = content.find('"""') + 3
            end = content.find('"""', start)
            if start > 2 and end > start:
                description = content[start:end].strip()

        md_content = f"""---
name: {cmd_name}
version: 1.0
type: command
platform: all
description: {description}
---

# {cmd_name.replace('-', ' ').title()}

{description}

## Implementation

```python
{content}
```
"""
        return md_content

    def _log_action(self, action: str, source: str, target: str):
        """记录迁移动作"""
        self.migration_log.append({
            "action": action,
            "source": source,
            "target": target,
            "timestamp": datetime.now().isoformat(),
        })


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="OLAV to Agent Platform Skill 迁移工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 测试迁移 (不实际修改文件)
  python scripts/migrate_olav_to_agent.py --platform claude --dry-run
  
  # 执行Claude Code迁移
  python scripts/migrate_olav_to_agent.py --platform claude
  
  # 迁移到所有平台
  python scripts/migrate_olav_to_agent.py --platform all
  
  # 不备份地迁移
  python scripts/migrate_olav_to_agent.py --platform claude --no-backup
        """
    )

    parser.add_argument(
        "--platform",
        choices=["claude", "cursor", "all"],
        default="claude",
        help="目标Agent平台 (默认: claude)"
    )

    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="OLAV工作目录 (默认: 当前目录)"
    )

    parser.add_argument(
        "--agent-dir",
        default=".olav",
        help="Agent目录名称 (默认: .olav)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="干运行模式 - 显示会执行的操作但不实际修改"
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="跳过备份现有文件"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="详细输出"
    )

    args = parser.parse_args()

    # 创建配置
    config = MigrationConfig(
        platform=args.platform,
        agent_dir=args.agent_dir,
        dry_run=args.dry_run,
        verbose=args.verbose,
        backup=not args.no_backup,
    )

    # 执行迁移
    migrator = OlavMigrator(args.workspace, config)
    success = migrator.run_migration()

    # 输出最终状态
    print("\n" + "="*60)
    if success:
        print("✅ 迁移完成!")
        print(f"   已执行 {len(migrator.migration_log)} 个操作")
    else:
        print("❌ 迁移失败!")
        for error in migrator.errors:
            print(f"   - {error}")

    print("="*60)

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
