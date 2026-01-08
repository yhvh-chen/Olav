"""Storage Backend Configuration for OLAV.

This module configures the CompositeBackend for DeepAgents, defining
which paths the agent can read/write vs read-only vs temporary.

Based on DESIGN_V0.8.md Section 7.4:
- skills/ → Agent可写
- knowledge/ → Agent可写
- tools/commands/ → Agent可写 (只读命令)
- tools/apis/ → Agent只读 (API定义由人类维护)
- OLAV.md → Agent只读 (核心规则由人类维护)
- .env → 不可访问 (敏感配置)
"""

from pathlib import Path

try:
    from deepagents.storage import CompositeBackend, StateBackend, StoreBackend
    DEEPAGENTS_HAS_STORAGE = True
except ImportError:
    # DeepAgents may not have these exact classes
    # Fallback to basic filesystem access
    DEEPAGENTS_HAS_STORAGE = False
    StoreBackend = None
    StateBackend = None
    CompositeBackend = None


def get_storage_backend(project_root: Path | None = None):
    """Get the configured storage backend for OLAV.

    Args:
        project_root: Project root directory (defaults to current directory)

    Returns:
        CompositeBackend or None if not available

    Storage Strategy:
        /skills/*              → Read + Write (Agent can learn new strategies)
        /knowledge/*           → Read + Write (Agent can accumulate knowledge)
        /tools/commands/*      → Read + Write (Agent can add read-only commands)
        /tools/apis/*          → Read Only (API definitions maintained by humans)
        /OLAV.md               → Read Only (Core rules maintained by humans)
        /.env                  → No Access (Sensitive configuration)
        /scratch/*             → Temporary (Session-only)
    """
    if not DEEPAGENTS_HAS_STORAGE:
        return None

    if project_root is None:
        project_root = Path.cwd()

    olav_dir = project_root / ".olav"

    # Configure persistent storage paths (Agent can write)
    persistent_paths = [
        olav_dir / "skills",
        olav_dir / "knowledge",
        olav_dir / "imports" / "commands",
    ]

    # Configure read-only paths
    read_only_paths = [
        olav_dir / "imports" / "apis",
        olav_dir / "OLAV.md",
    ]

    # Configure temporary paths (session-only)
    temp_paths = [
        olav_dir / "scratch",
    ]

    # Create persistent backend
    persistent_backend = StoreBackend(
        root_dir=project_root,
        allowed_paths=persistent_paths,
        read_only_paths=read_only_paths,
    )

    # Create temporary backend for scratch space
    temp_backend = StateBackend()

    # Create composite backend
    # Priority: specific paths first, then temporary
    composite = CompositeBackend(
        backends={
            **{str(path): persistent_backend for path in persistent_paths},
            **{str(path): persistent_backend for path in read_only_paths},
            **{str(path): temp_backend for path in temp_paths},
            "/": persistent_backend,  # Default
        }
    )

    return composite


def get_storage_permissions() -> str:
    """Get storage permission documentation for system prompt.

    Returns:
        Formatted permission matrix
    """
    return """## 文件系统权限

你可以访问以下路径:

### ✅ 可读写 (用于自学习)
- `.olav/skills/*.md` - 技能策略 (可以学习新模式)
- `.olav/knowledge/*` - 知识库 (可以积累新知识)
  - `.olav/knowledge/aliases.md` - 设备别名
  - `.olav/knowledge/solutions/*.md` - 成功案例
- `.olav/imports/commands/*.txt` - 命令白名单 (可以添加只读命令)

### ⚠️ 只读 (人类维护)
- `.olav/imports/apis/*.yaml` - API定义
- `.olav/OLAV.md` - 核心规则

### ❌ 不可访问
- `.env` - 敏感配置
- `config/` - 运行配置

### 🔒 临时存储 (会话内有效)
- `.olav/scratch/*` - 临时文件 (会话结束后删除)

### 学习原则
1. 只在确认成功后保存解决方案
2. 只在用户明确澄清时更新别名
3. 添加命令时只添加已验证的只读命令
4. 任何写入操作前仍需用户确认
"""


def check_write_permission(filepath: Path | str, project_root: Path | None = None) -> bool:
    """Check if agent has write permission for a file.

    Args:
        filepath: File path to check
        project_root: Project root directory

    Returns:
        True if agent can write to this file, False otherwise
    """
    if project_root is None:
        project_root = Path.cwd()

    filepath = Path(filepath)
    olav_dir = project_root / ".olav"

    # Normalize path
    try:
        rel_path = filepath.resolve().relative_to(olav_dir.resolve())
    except ValueError:
        # Not under .olav directory
        return False

    # Check allowed write paths
    allowed_write_patterns = [
        Path("skills"),
        Path("knowledge"),
        Path("knowledge") / "solutions",
        Path("imports") / "commands",
    ]

    for pattern in allowed_write_patterns:
        if rel_path.is_relative_to(pattern):
            return True

    # Read-only paths
    read_only_patterns = [
        Path("imports") / "apis",
    ]

    for pattern in read_only_patterns:
        if rel_path.is_relative_to(pattern):
            return False

    # Default: no write permission
    return False


__all__ = [
    "get_storage_backend",
    "get_storage_permissions",
    "check_write_permission",
]
