# OLAV Claude Code Migration - Quick Start Guide

## Overview

OLAV has been successfully migrated to Claude Code Skill Standard format. This guide helps you get started with the new system.

## Installation & Setup

### 1. Prerequisites
- Python 3.8+
- `uv` package manager (as per project standards)
- DuckDB (installed via pip/uv)
- LangChain (for embeddings)

### 2. Configure Environment

```bash
# Set the agent directory (default: .olav)
export AGENT_DIR=.olav

# Or use alternative directories
export AGENT_DIR=.claude  # For Claude Code
export AGENT_DIR=.cursor  # For Cursor IDE
```

### 3. Initialize Knowledge Base

```bash
# Reload/index all knowledge documents
python .olav/commands/reload-knowledge.py --verbose

# Verify database integrity
python .olav/commands/sync-knowledge.py --report
```

## Using Skills

### Available Skills

1. **quick-query** - Fast network queries
   ```markdown
   /quick-query "device status"
   ```

2. **device-inspection** - Device analysis
   ```markdown
   /device-inspection "interface troubleshooting"
   ```

3. **deep-analysis** - Network troubleshooting
   ```markdown
   /deep-analysis "BGP configuration issues"
   ```

4. **config-backup** - Configuration management
   ```markdown
   /config-backup "backup and archive"
   ```

### Skill Format

All skills follow the structure:
```
.olav/skills/<name>/SKILL.md
```

With YAML frontmatter:
```yaml
---
name: skill_name
version: 1.0
type: skill
description: What this skill does
---
```

## Using Commands

### Available Commands

1. **search-knowledge** - Search the knowledge base
   ```bash
   python .olav/commands/search-knowledge.py "BGP configuration" --type hybrid --limit 10
   ```

2. **reload-knowledge** - Reindex knowledge documents
   ```bash
   python .olav/commands/reload-knowledge.py --incremental
   ```

3. **sync-knowledge** - Sync database with filesystem
   ```bash
   python .olav/commands/sync-knowledge.py --cleanup
   ```

### Command Format

Commands are in Markdown with embedded Python:
```
.olav/commands/<name>.md

Format:
---
name: command_name
type: command
version: 1.0
description: ...
---

# Documentation

\`\`\`python
# Implementation
\`\`\`
```

## Search Knowledge

### Quick Search

```bash
python .olav/commands/search-knowledge.py "your query"
```

### Advanced Search

```bash
# Full-text search
python .olav/commands/search-knowledge.py "BGP" --type full_text

# Vector similarity search
python .olav/commands/search-knowledge.py "network configuration" --type vector

# Hybrid search (combined)
python .olav/commands/search-knowledge.py "interface down" --type hybrid --limit 20
```

### Search Modes Explained

- **Full-Text**: Keyword and phrase matching. Fast, exact matches.
- **Vector**: Semantic similarity using embeddings. Finds conceptually similar content.
- **Hybrid**: Combines both for best results. Recommended for discovery.

## Managing Knowledge

### Add New Knowledge

1. Create Markdown file in `.olav/knowledge/` or `.olav/knowledge/solutions/`
2. Add YAML frontmatter with metadata:
   ```markdown
   ---
   tags: bgp, routing
   severity: high
   ---
   
   # BGP Configuration
   ...
   ```
3. Reload knowledge:
   ```bash
   python .olav/commands/reload-knowledge.py --incremental
   ```

### Update Existing Knowledge

1. Edit the Markdown file
2. Reload (incremental picks up changes):
   ```bash
   python .olav/commands/reload-knowledge.py --incremental
   ```

### Remove Knowledge

1. Delete the Markdown file
2. Sync database to remove vectors:
   ```bash
   python .olav/commands/sync-knowledge.py --cleanup
   ```

## Testing

### Run Unit Tests

```bash
# All unit tests
pytest tests/ -v

# Specific test file
pytest tests/test_search_tool.py -v

# With coverage
pytest tests/ --cov=olav --cov-report=html
```

### Run E2E Tests

```bash
pytest tests/e2e/ -v
```

### Run Specific Test

```bash
pytest tests/test_search_tool.py::TestSearchKnowledge::test_search_knowledge_hybrid -v
```

## Verification

### Verify Compatibility

Quick check:
```bash
python scripts/verify_claude_compatibility.py .
```

Complete verification:
```bash
python scripts/verify_migration_complete.py .
```

View report:
```bash
cat MIGRATION_VERIFICATION_REPORT.json
```

## Configuration

### Settings File

Location: `config/settings.py`

Key settings:
```python
# Directory for all agent files
agent_dir = Path(".olav")

# Embedding model
embedding_model = "all-MiniLM-L6-v2"

# Database path
database_path = agent_dir / "data" / "knowledge.db"
```

### Environment Variables

```bash
# Override agent directory
AGENT_DIR=.claude

# Custom embedding model
EMBEDDING_MODEL=text-embedding-3-small

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434
```

## System Instruction

The CLAUDE.md file contains the system instruction for Claude Code:

**Location:** `CLAUDE.md` (root of workspace)

**Contains:**
- Agent description
- Available tools documentation
- Output format (Markdown only)
- Skill descriptions
- Tool parameters and options

**Output Requirement:**
> All responses must be in Markdown format. Do not use HTML, Jinja2 templates, or other formats.

## Troubleshooting

### Knowledge Search Returns No Results

1. Check if knowledge is indexed:
   ```bash
   python .olav/commands/reload-knowledge.py --verbose
   ```

2. Verify database:
   ```bash
   python .olav/commands/sync-knowledge.py --report
   ```

3. Check knowledge files exist:
   ```bash
   ls -la .olav/knowledge/
   ls -la .olav/knowledge/solutions/
   ```

### Skill Not Found

1. Check skill directory exists:
   ```bash
   ls -la .olav/skills/
   ```

2. Verify SKILL.md exists:
   ```bash
   ls -la .olav/skills/<skill_name>/SKILL.md
   ```

3. Check YAML format:
   ```bash
   head -5 .olav/skills/<skill_name>/SKILL.md
   ```

### Database Locked Error

1. Close all database connections
2. Reset database (removes all data):
   ```bash
   python .olav/commands/reload-knowledge.py --reset
   ```

3. Reload knowledge:
   ```bash
   python .olav/commands/reload-knowledge.py
   ```

### Path Configuration Issues

1. Check settings:
   ```bash
   python -c "from config.settings import settings; print(settings.agent_dir)"
   ```

2. Override if needed:
   ```bash
   export AGENT_DIR=/path/to/custom/dir
   ```

3. Verify paths in code:
   ```bash
   grep -r "Path(settings.agent_dir" src/
   ```

## Development Workflow

### Adding a New Skill

1. Create directory:
   ```bash
   mkdir -p .olav/skills/my_skill
   ```

2. Create SKILL.md:
   ```bash
   cat > .olav/skills/my_skill/SKILL.md << 'EOF'
   ---
   name: my_skill
   version: 1.0
   type: skill
   description: What this skill does
   ---
   
   # My Skill
   
   Documentation here.
   EOF
   ```

3. Add implementation in code block
4. Test with unit tests

### Adding a New Command

1. Create command file:
   ```bash
   cat > .olav/commands/my_command.md << 'EOF'
   ---
   name: my_command
   version: 1.0
   type: command
   description: What this command does
   ---
   
   # My Command
   
   ## Implementation
   
   \`\`\`python
   def main():
       pass
   \`\`\`
   EOF
   ```

2. Create corresponding Python file
3. Add tests

### Adding Knowledge

1. Create file in knowledge directory
2. Add YAML frontmatter with metadata
3. Write Markdown documentation
4. Reload knowledge base

## Integration with Claude Code

The system is optimized for Claude Code integration:

1. **System Instruction**: CLAUDE.md is loaded as system prompt
2. **Skill Access**: Skills available via `/skill_name` notation
3. **Tool Descriptions**: All tools documented for Claude
4. **Output Format**: Markdown-only, no special markup
5. **File Organization**: Standard Claude Code structure

### Using in Claude Code

1. Load CLAUDE.md as system instruction
2. Load workspace with skills and commands
3. Use `/skill_name` or `/command_name` notation
4. All tools documented and accessible

## Performance Tips

### Optimize Search

1. Use more specific queries:
   ```bash
   # Good - specific and targeted
   python .olav/commands/search-knowledge.py "BGP neighbor configuration"
   
   # Less effective - too broad
   python .olav/commands/search-knowledge.py "network"
   ```

2. Use appropriate search type:
   - FTS for exact matches
   - Vector for semantic search
   - Hybrid for best of both

3. Limit results to what you need:
   ```bash
   python .olav/commands/search-knowledge.py "query" --limit 5
   ```

### Optimize Indexing

1. Use incremental mode for frequent updates:
   ```bash
   python .olav/commands/reload-knowledge.py --incremental
   ```

2. Reset only when necessary:
   ```bash
   python .olav/commands/reload-knowledge.py --reset  # Full rebuild
   ```

## Support

For detailed information, see:
- `MIGRATION_COMPLETION_REPORT.md` - Complete migration details
- `CLAUDE.md` - System instruction with tool documentation
- `.olav/skills/*/SKILL.md` - Individual skill documentation
- `tests/` - Test examples and patterns

---

**Quick Command Reference:**

```bash
# Search knowledge
python .olav/commands/search-knowledge.py "<query>"

# Reload knowledge (incremental)
python .olav/commands/reload-knowledge.py --incremental

# Sync knowledge database
python .olav/commands/sync-knowledge.py --cleanup

# Run tests
pytest tests/ -v

# Verify compatibility
python scripts/verify_claude_compatibility.py .

# Full verification
python scripts/verify_migration_complete.py .
```

---

**Migration Status:** ✅ Complete  
**Claude Code Compatibility:** ✅ Verified  
**Ready for Production:** ✅ Yes
