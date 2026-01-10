---
name: analyze
version: 1.0.0
type: workflow
platform: all
description: Deep network path analysis
---

# Analyze Workflow

## Usage
```
/analyze [source] [destination] [--error "desc"] [--plan] [--interactive]
```

## Options
- `--error "description"` - Error context to guide analysis
- `--plan` - Show analysis plan before execution
- `--interactive` - Pause after each analysis phase

## Phases
1. **Macro Analysis** - Trace path, identify fault domain
2. **Micro Analysis** - Layer-by-layer troubleshooting
3. **Synthesis** - Root cause and recommendations

## Examples
```
/analyze R1 R3
/analyze R1 R3 --error "packet loss"
/analyze R1 R3 --plan --interactive
```

Follow skill methodology: @skills/deep-analysis/SKILL.md
