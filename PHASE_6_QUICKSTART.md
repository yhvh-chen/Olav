# Phase 6 Quickstart Guide - Enhanced CLI

## Quick Start

### 1. Start Interactive Mode

```bash
olav interactive
```

You'll see the OLAV banner and welcome message with feature overview.

### 2. Try Slash Commands

```bash
# Show all available commands
olav> /help

# List all devices
olav> /devices

# List core devices only
olav> /devices role:core

# Show available skills
olav> /skills

# Show skill details
olav> /skills quick-query

# View session statistics
olav> /history

# Clear session memory
olav> /clear

# Exit
olav> /quit
```

### 3. Use File References

```bash
# Create a test file
echo "interface GigabitEthernet0/1
 ip address 192.168.1.1 255.255.255.0" > /tmp/router_config.txt

# Reference it in your query
olav> @/tmp/router_config.txt analyze this configuration
```

### 4. Execute Shell Commands

```bash
# Network diagnostics
olav> !ping 8.8.8.8

# File operations
olav> !ls -la

# System information
olav> !uptime
```

### 5. Normal Queries with Memory

```bash
# Query with context
olav> Check R1 interface status
# OLAV responds with interface information

olav> Is it up?
# OLAV remembers you're asking about R1 interface

olav> What about R2?
# OLAV maintains context
```

## Configuration

### Change Banner Type

Edit `.olav/settings.json`:
```json
{
  "cli_banner": "snowman"
}
```

Available options: `olav`, `snowman`, `deepagents`, `minimal`, `none`

### View Memory File

```bash
cat .olav/.agent_memory.json
```

### Clear Memory

```bash
olav> /clear
```

Or delete the file directly:
```bash
rm .olav/.agent_memory.json
```

## Tips & Tricks

### Multi-line Input

Press Enter twice to submit multi-line input:

```bash
olav> Check the following devices:
R1
R2
R5
<press Enter again>
```

### Code Blocks

Paste code directly with ``` wrappers:

```bash
olav> ```python
def check_interface(name):
    return f"Checking {name}"
```
Analyze this function
```
```

### Command History

- **Up/Down arrows**: Navigate history
- **Ctrl+R**: Search history
- **Tab**: Auto-complete

### Multiple File References

```bash
olav> Compare @config1.txt and @config2.txt
```

## Common Workflows

### Network Troubleshooting

```bash
olav> /devices role:core
olav> !ping 192.168.1.1
olav> @router_config.txt check OSPF configuration
olav> /history  # Review your session
```

### Configuration Analysis

```bash
olav> @production_router.conf verify BGP setup
olav> @backup_router.conf compare with previous
olav> /skills network-diagnosis
```

### System Inspection

```bash
olav> /inspect all core routers
olav> !df -h
olav> /skills device-inspection
```

## Testing Your Setup

### Verify Phase 6 Features

```bash
# 1. Test slash commands
olav> /help
# Should show command list

# 2. Test file references
echo "test" > /tmp/test.txt
olav> @/tmp/test.txt
# Should include file content

# 3. Test shell commands
olav> !echo hello
# Should print "hello"

# 4. Test memory
olav> Remember: test123
olav> /history
# Should show increased message count

# 5. Test banner
# Edit .olav/settings.json, change "cli_banner" to "snowman"
# Restart: olav interactive
# Should see snowman banner
```

### Run Unit Tests

```bash
# All CLI tests
pytest tests/unit/test_cli_simple.py tests/unit/test_cli_input_parser.py -v

# Expected: 31 passed
```

## Troubleshooting

### "Command requires async context"

Some slash commands are async but have sync fallbacks. This is expected behavior.

### File not found

Use absolute paths or ensure files are in current directory:
```bash
# Good
olav> @/tmp/config.txt

# Bad (unless file is in current directory)
olav> @config.txt
```

### Shell command timeout

Commands timeout after 30 seconds. For long-running tasks, run them outside OLAV:
```bash
# Instead of
olav> !backup.sh  # May timeout

# Use
$ backup.sh
olav> Check backup status
```

## Keyboard Shortcuts

- **Ctrl+C**: Interrupt current query
- **Ctrl+D**: Exit (same as `/quit`)
- **Up/Down**: Navigate history
- **Ctrl+R**: Reverse search
- **Tab**: Auto-complete
- **Enter** (twice): Submit multi-line input

## Next Steps

1. **Explore Skills**: Try `/skills` to see available skills
2. **Customize Banner**: Edit `.olav/settings.json`
3. **Check Memory**: Review `.olav/.agent_memory.json`
4. **Read Full Docs**: See `PHASE_6_COMPLETION_SUMMARY.md`

## Getting Help

```bash
olav> /help          # General help
olav> /help devices  # Command-specific help
olav> /skills        # List available skills
```

---

**Enjoy the enhanced OLAV CLI experience!** 🚀
