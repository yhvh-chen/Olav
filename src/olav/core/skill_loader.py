"""Skill Loader - 从 Markdown frontmatter 加载和索引技能."""

import re
from pathlib import Path
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import yaml


@dataclass
class Skill:
    """技能数据结构."""
    id: str
    intent: str  # query | diagnose | inspect | config
    complexity: str  # simple | medium | complex
    description: str
    examples: List[str]
    file_path: str
    content: Optional[str] = None  # 延迟加载


class SkillLoader:
    """技能加载器 - 解析frontmatter、生成索引、延迟加载内容."""

    def __init__(self, skills_dir: Path):
        self.skills_dir = Path(skills_dir)
        self._index: Dict[str, Skill] = {}
        self._content_cache: Dict[str, str] = {}

    def load_all(self) -> Dict[str, Skill]:
        """扫描并加载所有技能索引."""
        if self._index:
            return self._index

        for md_file in self.skills_dir.glob("*.md"):
            # 跳过禁用文件 (_ 前缀, .draft 后缀)
            if md_file.name.startswith("_") or ".draft" in md_file.name:
                continue

            skill = self._parse_skill_header(md_file)
            if skill:
                self._index[skill.id] = skill

        return self._index

    def _parse_skill_header(self, file_path: Path) -> Optional[Skill]:
        """解析单个技能文件的 frontmatter (不加载完整内容)."""
        try:
            content = file_path.read_text(encoding="utf-8")

            # 提取 frontmatter
            fm = self._extract_frontmatter(content)
            if not fm:
                return None

            # 验证必需字段
            if not all(k in fm for k in ["id", "description"]):
                return None

            # 检查 enabled 标志
            if fm.get("enabled") == False:
                return None

            return Skill(
                id=fm["id"],
                intent=fm.get("intent", "unknown"),
                complexity=fm.get("complexity", "medium"),
                description=fm["description"],
                examples=fm.get("examples", []),
                file_path=str(file_path),
            )
        except Exception as e:
            print(f"Error parsing skill {file_path}: {e}")
            return None

    def _extract_frontmatter(self, content: str) -> Optional[Dict[str, Any]]:
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

    def get_skill(self, skill_id: str) -> Optional[Skill]:
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

    def get_skills_by_intent(self, intent: str) -> List[Skill]:
        """按意图过滤技能."""
        if not self._index:
            self.load_all()

        return [s for s in self._index.values() if s.intent == intent]

    def get_index_summary(self) -> Dict[str, Any]:
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


def get_skill_loader(skills_dir: Optional[Path] = None) -> SkillLoader:
    """获取全局 SkillLoader 实例 (单例)."""
    if not hasattr(get_skill_loader, "_instance"):
        if skills_dir is None:
            skills_dir = Path(__file__).parent.parent.parent.parent / ".olav" / "skills"
        get_skill_loader._instance = SkillLoader(skills_dir)
    return get_skill_loader._instance
