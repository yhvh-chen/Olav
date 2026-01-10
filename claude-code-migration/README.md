# Claude Code Skill Compatible Structure

This directory contains a Claude Code Skill-compatible agent configuration.

## Directory Structure

```
./
├── CLAUDE.md              # System prompt
├── .claude/                   # Agent settings
│   └── settings.json
├── commands/                    # Slash commands
│   ├── query.md                # /query command
│   ├── inspect.md              # /inspect command
│   └── diagnose.md             # /diagnose command
├── skills/                      # Agent skills
│   ├── quick-query/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── device-inspection/
│   │   ├── SKILL.md
│   │   └── references/
│   └── deep-analysis/
│       ├── SKILL.md
│       └── references/
│           └── user-runbooks/   # 📚 User documentation
├── knowledge/                   # Shared knowledge
│   ├── aliases.md
│   ├── conventions.md
│   └── user-docs/              # 📚 User documentation
└── config/                      # Runtime config
    └── nornir/
```

## Usage

### With Claude Code
```bash
# Rename .claude/ to .claude/
mv .claude/ .claude/
mv CLAUDE.md CLAUDE.md
```

### With Cursor
```bash
# Rename .claude/ to .cursor/
mv .claude/ .cursor/
mv CLAUDE.md CURSOR.md
```

### With Custom Agent
```bash
# Rename to your agent name
mv .claude/ .myagent/
mv CLAUDE.md MYAGENT.md
```

## Slash Commands

| Command | Description |
|---------|-------------|
| `/query [device] [query]` | Quick device status query |
| `/inspect [scope]` | Comprehensive L1-L4 inspection |
| `/diagnose [src] [dst]` | Network connectivity diagnosis |

## Skills

| Skill | When to Use |
|-------|-------------|
| Quick Query | Simple status checks (1-2 commands) |
| Device Inspection | Full health check (L1-L4) |
| Deep Analysis | Complex troubleshooting |

## 📚 Adding Your Own Documentation

### Global Documentation
Place company-wide documentation in `knowledge/user-docs/`:
```bash
cp my-network-guide.md knowledge/user-docs/
```

### Skill-Specific Documentation
Place skill-specific runbooks in `skills/*/references/user-runbooks/`:
```bash
cp bgp-troubleshooting.md skills/deep-analysis/references/user-runbooks/
```

Documents will be automatically available to the agent.
