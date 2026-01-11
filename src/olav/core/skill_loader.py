"""Skill Loader - 从 Markdown frontmatter 加载和索引技能."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Skill:
    """技能数据结构.

    支持两种格式:
    - OLAV 格式: id 字段
    - Claude Code 格式: name 字段 (自动转换为 id)
    """

    id: str
    intent: str  # query | diagnose | inspect | config
    complexity: str  # simple | medium | complex
    description: str
    examples: list[str]
    file_path: str
    content: str | None = None  # 延迟加载
    frontmatter: dict[str, Any] | None = None  # Frontmatter 数据 (延迟加载)


class SkillLoader:
    """技能加载器 - 解析frontmatter、生成索引、延迟加载内容."""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = Path(skills_dir)
        self._index: dict[str, Skill] = {}
        self._content_cache: dict[str, str] = {}

    def load_all(self) -> dict[str, Skill]:
        """扫描并加载所有技能索引 - 支持两种格式.

        支持格式:
        1. Claude Code 标准: skills/*/SKILL.md
        2. OLAV 传统格式: skills/*.md
        """
        if self._index:
            return self._index

        # Format 1: Claude Code 标准 (skills/*/SKILL.md)
        for skill_dir in self.skills_dir.iterdir():
            if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
                skill_file = skill_dir / "SKILL.md"
                if skill_file.exists():
                    skill = self._parse_skill_header(skill_file)
                    if skill:
                        self._index[skill.id] = skill

        # Format 2: OLAV 传统 (skills/*.md)
        for md_file in self.skills_dir.glob("*.md"):
            # 跳过已处理的 SKILL.md 和禁用文件
            if md_file.name == "SKILL.md":
                continue
            if md_file.name.startswith("_") or ".draft" in md_file.name:
                continue

            skill = self._parse_skill_header(md_file)
            if skill:
                # 避免覆盖已加载的 Claude Code 格式技能
                if skill.id not in self._index:
                    self._index[skill.id] = skill

        return self._index

    def _parse_skill_header(self, file_path: Path) -> Skill | None:
        """解析单个技能文件的 frontmatter (不加载完整内容).

        支持两种格式:
        - OLAV 格式: id 字段
        - Claude Code 格式: name 字段 (自动转换为 id)
        """
        try:
            content = file_path.read_text(encoding="utf-8")

            # 提取 frontmatter
            fm = self._extract_frontmatter(content)
            if not fm:
                return None

            # 兼容 id 和 name 字段
            skill_id = fm.get("id") or fm.get("name")
            if not skill_id:
                # 如果都没有，从文件名生成
                skill_id = (
                    file_path.stem.replace("-", " ").replace("_", " ").lower().replace(" ", "-")
                )

            # 验证必需字段
            if "description" not in fm:
                return None

            # 检查 enabled 标志 - 默认启用（除非显式禁用）
            if fm.get("enabled", True) is False:
                return None

            # Normalize skill_id: lowercase with hyphens
            skill_id = skill_id.lower().replace(" ", "-").replace("_", "-")

            return Skill(
                id=skill_id,
                intent=fm.get("intent", "unknown"),
                complexity=fm.get("complexity", "medium"),
                description=fm["description"],
                examples=fm.get("examples", fm.get("triggers", [])),
                file_path=str(file_path),
                frontmatter=fm,  # Store frontmatter for output config access
            )
        except Exception as e:
            print(f"Error parsing skill {file_path}: {e}")
            return None

    def _extract_frontmatter(self, content: str) -> dict[str, Any] | None:
        """从 Markdown 内容中提取 YAML frontmatter."""
        if not content.startswith("---"):
            return None

        # 找到第二个 ---
        end_idx = content.find("---", 3)
        if end_idx == -1:
            return None

        fm_str = content[3:end_idx].strip()
        try:
            return yaml.safe_load(fm_str) or {}
        except yaml.YAMLError:
            return None

    def get_skill(self, skill_id: str) -> Skill | None:
        """获取单个技能 (延迟加载内容)."""
        if not self._index:
            self.load_all()

        if skill_id not in self._index:
            return None

        skill = self._index[skill_id]

        # 延迟加载完整内容
        if not skill.content:
            try:
                skill.content = Path(skill.file_path).read_text(encoding="utf-8")
            except Exception as e:
                print(f"Error loading skill content {skill_id}: {e}")

        return skill

    def get_skills_by_intent(self, intent: str) -> list[Skill]:
        """按意图过滤技能."""
        if not self._index:
            self.load_all()

        return [s for s in self._index.values() if s.intent == intent]

    def get_index_summary(self) -> dict[str, Any]:
        """生成索引摘要 (用于LLM路由)."""
        if not self._index:
            self.load_all()

        return {
            "total": len(self._index),
            "generated_at": None,  # TODO: 添加时间戳
            "skills": {
                skill_id: {
                    "complexity": skill.complexity,
                    "description": skill.description,
                    "examples": skill.examples[:3],  # 只保留前3个示例
                }
                for skill_id, skill in self._index.items()
            },
        }


def get_skill_loader(skills_dir: Path | None = None) -> SkillLoader:
    """获取全局 SkillLoader 实例 (单例)."""
    if not hasattr(get_skill_loader, "_instance"):
        if skills_dir is None:
            skills_dir = Path(__file__).parent.parent.parent.parent / ".olav" / "skills"
        get_skill_loader._instance = SkillLoader(skills_dir)
    return get_skill_loader._instance
