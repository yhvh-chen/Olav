# OLAV CLI - User Guide

## Overview

OLAV v0.8 provides a modern command-line interface built with **Typer** and **Rich** for interactive network operations queries.

## Installation

The CLI is automatically available when you install OLAV:

```bash
uv sync
```

## Usage

### Start the CLI

#### Option 1: Using Python Module (Recommended)
```bash
uv run python -m olav [COMMAND] [OPTIONS]
```

#### Option 2: Direct Command (After Installation)
```bash
uv run olav [COMMAND] [OPTIONS]
```

## Commands

### 1. Query (`query`)
Execute network operations queries in natural language.

**Syntax:**
```bash
uv run python -m olav query "<query_text>" [--debug]
```

**Examples:**
```bash
# Check interface status on R1 (Chinese)
uv run python -m olav query "查看 R1 接口状态"

# Check BGP neighbors
uv run python -m olav query "R1 的 BGP 邻居"

# With debug output
uv run python -m olav query "核心交换机的 CPU" --debug

# English queries
uv run python -m olav query "Show all device interfaces"
```

**Options:**
- `--debug, -d` - Enable debug logging (shows LLM thinking, tool calls, etc.)

### 2. List Devices (`devices`)
Display all managed network devices from your inventory.

**Syntax:**
```bash
uv run python -m olav devices
```

**Example:**
```bash
uv run python -m olav devices
```

**Output:**
Shows a table with device information (requires proper Nornir configuration).

### 3. Show Configuration (`config`)
Display current OLAV configuration settings.

**Syntax:**
```bash
uv run python -m olav config
```

**Example:**
```bash
uv run python -m olav config
```

**Displays:**
- LLM Provider (openai, ollama, etc.)
- Model Name
- LLM API Endpoint
- Environment Type
- Log Level
- Device Credentials
- Database Paths

### 4. Show Version (`version`)
Display OLAV version and framework information.

**Syntax:**
```bash
uv run python -m olav version
```

**Example:**
```bash
uv run python -m olav version
```

### 5. Interactive Mode (`interactive`)
Start an interactive chat session with OLAV.

**Syntax:**
```bash
uv run python -m olav interactive
```

**Usage:**
```
OLAV Interactive Mode
Type queries to start. 'help' for commands, 'quit' to exit.

You: show R1 interfaces
OLAV: [response from agent]

You: devices
OLAV: [displays network devices]

You: config
OLAV: [shows configuration]

You: help
OLAV: [shows available commands]

You: quit
Goodbye!
```

**Commands within Interactive Mode:**
- Type any network query - OLAV will respond
- `help` - Show help message
- `config` - Display configuration
- `devices` - List network devices
- `quit` or `exit` - Exit the session

## Examples

### Chinese Language Examples

```bash
# Infrastructure inspection
uv run python -m olav query "巡检核心设备"

# Specific device status
uv run python -m olav query "查看所有设备的 CPU 使用率"

# Troubleshooting
uv run python -m olav query "上海到北京网络不通"

# BGP status
uv run python -m olav query "检查所有 BGP 邻接"
```

### English Language Examples

```bash
# General inquiry
uv run python -m olav query "List all core routers"

# Debug mode
uv run python -m olav query "Check OSPF status" --debug

# Configuration check
uv run python -m olav query "Show BGP configuration on all border routers"
```

## Output Formatting

### Query Response
Responses are formatted with Rich panels showing:
- Query input (cyan panel)
- Agent responses (green panels)
- Error messages (red panels)

### Debug Output
When using `--debug` flag, you see:
- LLM API calls
- Tool invocations
- Token usage
- Intermediate reasoning

## Environment Configuration

OLAV uses environment variables from `.env`:

```bash
# LLM Configuration
LLM_PROVIDER=openai
LLM_API_KEY=sk-...
LLM_MODEL_NAME=x-ai/grok-4.1-fast
LLM_BASE_URL=https://openrouter.ai/api/v1

# Device Credentials
DEVICE_USERNAME=admin
DEVICE_PASSWORD=secure_password

# Logging
LOG_LEVEL=INFO
```

See `.env.example` for full configuration template.

## Troubleshooting

### Command Not Found
```
ERROR: Invalid syntax
```

**Solution:** Make sure to use `uv run python -m olav` instead of just `olav`:

```bash
# ✅ CORRECT
uv run python -m olav query "test"

# ❌ WRONG
olav query "test"
```

### No Response from Agent
Check if:
1. LLM API key is set in `.env`
2. Network connectivity is available
3. Use `--debug` flag to see what tools are being called

```bash
uv run python -m olav query "test" --debug
```

### Device Inventory Issues
```
Error listing devices: Config.from_dict() got an unexpected keyword argument 'config'
```

**Solution:** Verify Nornir configuration:
- Check `config/nornir_config.yml` syntax
- Verify `.olav/config/nornir/hosts.yaml` exists and is valid YAML

## Performance Tips

1. **First query is slower** - LLM loads the model and caches prompts
2. **Use debug sparingly** - Debug output adds latency
3. **Batch queries** - Use interactive mode for multiple queries in sequence
4. **Check configuration** - Run `config` to verify settings before running queries

## Keyboard Shortcuts

- `Ctrl+C` - Cancel current operation (will show "Use 'quit' to exit" in interactive mode)
- `Up/Down arrows` - Command history in interactive mode (if supported by terminal)

## Advanced Usage

### Running Queries in Scripts

You can script OLAV queries:

```bash
#!/bin/bash
# script.sh

echo "Checking device status..."
uv run python -m olav query "列出所有设备"

echo -e "\nChecking configuration..."
uv run python -m olav query "显示网络配置"

echo -e "\nDone!"
```

```bash
chmod +x script.sh
./script.sh
```

### JSON Output (Future)

Current implementation uses Rich formatted output. For programmatic use, consider:
1. Parse the Rich-formatted text output
2. Use `--debug` to capture raw LLM responses
3. Future versions may support `--json` flag

## Next Steps

- **Phase 2:** Deep analysis skills for complex diagnostics
- **Phase 3:** Subagents for parallel operations
- **Phase 4:** Self-learning capabilities
- **Phase 5:** External system integration

See `DESIGN_V0.8.md` for complete roadmap.

