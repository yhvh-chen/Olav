# Phase 3 Quick Start Guide

> **For**: OLAV v0.8 Phase 3
> **Updated**: 2026-01-07
> **Status**: ✅ Production Ready

---

## What's New in Phase 3?

### 🤖 Specialized Subagents
- **macro-analyzer**: Expert in network topology, paths, end-to-end connectivity
- **micro-analyzer**: Expert in TCP/IP layer-by-layer troubleshooting
- **Automatic delegation**: Agent intelligently delegates to the right subagent
- **Parallel execution**: Multiple subagents can run simultaneously

### 📚 Enhanced Deep-Analysis Skill
- Complete subagent delegation guidance
- When to use each subagent
- Example delegation code
- Two-phase analysis strategy

### 🧪 Comprehensive Testing
- 13 new E2E tests for subagent functionality
- Backward compatibility verified
- Integration tests with Phase 1 & 2 features

---

## Quick Start (5 Minutes)

### 1️⃣ Verify Phase 3 is Enabled

```bash
# Check that subagents are enabled (default: True)
uv run python -c "from olav.agent import create_olav_agent; agent = create_olav_agent(); print('Phase 3 enabled')"
```

### 2️⃣ Try Phase 3 Features

#### Example 1: Macro Analysis (Topology & Paths)
```bash
uv run python -m olav query "分析从R1到R3的网络路径,找出哪个节点有问题"

# Agent will:
# 1. Recognize path analysis requirement
# 2. Delegate to macro-analyzer subagent
# 3. Subagent executes traceroute, checks BGP/OSPF
# 4. Returns fault domain identification
# 5. Agent provides structured report
```

#### Example 2: Micro Analysis (Layer-by-Layer)
```bash
uv run python -m olav query "R1的Gi0/1接口有CRC错误,帮我排查原因"

# Agent will:
# 1. Recognize specific interface issue
# 2. Delegate to micro-analyzer subagent
# 3. Subagent performs TCP/IP layered check:
#    - Layer 1: Interface status, CRC, optical power
#    - Layer 2: VLAN, MAC table
#    - Layer 3: IP, routing, ARP
# 4. Returns root cause with layer-specific findings
```

#### Example 3: Combined Analysis (Macro → Micro)
```bash
uv run python -m olav query "R1到R3的网络很慢,完整分析"

# Agent will:
# 1. Delegate to macro-analyzer: "找出慢的节点"
#    → Returns: "R2节点延迟高"
# 2. Delegate to micro-analyzer: "对R2进行TCP/IP排查"
#    → Returns: "R2 Gi0/1接口错误率高"
# 3. Synthesize complete report with root cause
```

---

## Subagent Capabilities

### Macro-Analyzer

**Specializes in**:
- Network topology analysis (LLDP/CDP/BGP neighbors)
- Data path tracing (traceroute, routing tables)
- End-to-end connectivity checks
- Fault domain identification

**Best for**:
- "哪个节点出了问题" (Which node has issues)
- "路径上哪里丢包" (Where is packet loss)
- "影响范围有多大" (What's the impact scope)

**Example**:
```
User: "核心路由器之间的网络不通"
Agent: Delegates to macro-analyzer → Checks all core router BGP/OSPF neighbors → Identifies which link is down
```

### Micro-Analyzer

**Specializes in**:
- TCP/IP layer-by-layer troubleshooting
- Physical layer: Interfaces, CRC, optical power
- Data link layer: VLAN, MAC table, STP
- Network layer: IP, routing, ARP
- Transport layer: ACL, NAT

**Best for**:
- "为什么这个端口不通" (Why is this port down)
- "接口有错误" (Interface has errors)
- "VLAN问题" (VLAN issues)

**Example**:
```
User: "R1的Gi0/1接口down了"
Agent: Delegates to micro-analyzer → Checks all layers → Returns: "Layer 1: CRC errors caused by aging optical module"
```

---

## How It Works

### Delegation Flow

```
User Query
    ↓
Main Agent (OLAV)
    ↓
Analyze Query Complexity
    ↓
┌─────────────────┬──────────────────┐
│  Simple Query   │  Complex Task    │
│  (Direct tools) │  (Delegation)    │
└─────────────────┴──────────────────┘
                          ↓
              Select Subagent Type
              (macro or micro)
                          ↓
              task(subagent_type, task_description)
                          ↓
              ┌─────────┴─────────┐
              │                   │
        Macro-Analyzer      Micro-Analyzer
              │                   │
        • Topology          • TCP/IP Layers
        • Paths             • Physical → Application
        • BGP/OSPF          • VLAN, MAC, ARP
              │                   │
              └─────────┬─────────┘
                          ↓
              Subagent Returns Result
                          ↓
              Main Agent Synthesizes Report
                          ↓
              User Receives Structured Analysis
```

### Token Efficiency

**Traditional Approach** (all in main agent):
- Agent performs all analysis: ~2000 tokens

**Subagent Approach** (delegation):
- Main agent: ~100 tokens (delegation)
- Subagent: ~500 tokens (specialized)
- Total: ~600 tokens
- **Savings**: ~70% token reduction

---

## Usage Patterns

### Pattern 1: Path Analysis

```bash
# User wants to analyze end-to-end path
uv run python -m olav query "分析从R1到SW3的数据路径"

# Agent delegates to macro-analyzer
# Returns: Complete path with device list and interfaces
```

### Pattern 2: Fault Isolation

```bash
# User has multi-device failure
uv run python -m olav query "核心层设备都无法访问,找出问题"

# Agent delegates to macro-analyzer
# Returns: "R2设备故障,影响范围:所有经R2的流量"
```

### Pattern 3: Deep Troubleshooting

```bash
# User has specific interface issue
uv run python -m olav query "R2的Gi0/1接口为什么有大量CRC错误"

# Agent delegates to micro-analyzer
# Returns: Layer-by-layer analysis:
#   - Layer 1: CRC errors 1234, RX power -18dBm
#   - Root cause: Aging optical module
#   - Solution: Replace optical module
```

### Pattern 4: Combined Analysis

```bash
# User has complex, unclear issue
uv run python -m olav query "网络时断时续,帮我完整分析"

# Agent uses two-phase approach:
# Phase 1: macro-analyzer → "R2-R4链路不稳定"
# Phase 2: micro-analyzer → "R2 Gi0/1光模块老化"
# Final: Complete analysis report with recommendations
```

---

## Testing Phase 3

### Run E2E Tests
```bash
# Run all Phase 3 tests
uv run pytest tests/e2e/test_phase3_subagents.py -v -m phase3

# Expected: 13 tests pass
```

### Manual Test Scenarios

#### Scenario 1: Macro Analysis
```bash
uv run python -m olav query "检查R1-R3路径"

# Verify:
# - Uses macro-analyzer
# - Returns path information
# - Mentions topology/neighbors
```

#### Scenario 2: Micro Analysis
```bash
uv run python -m olav query "排查R1接口问题"

# Verify:
# - Uses micro-analyzer
# - Returns layer-by-layer findings
# - Mentions TCP/IP layers
```

#### Scenario 3: Combined
```bash
uv run python -m olav query "网络慢,分析原因"

# Verify:
# - Uses both macro and micro
# - Structured two-phase approach
# - Complete report with root cause
```

---

## Backward Compatibility

Phase 3 is **fully backward compatible** with Phase 1 & 2:

### Phase 1 Features Still Work
```bash
# Smart query (still works)
uv run python -m olav query "查看R1接口状态"

# Batch query (still works)
uv run python -m olav query "批量查询所有路由器的BGP状态"
```

### Phase 2 Features Still Work
```bash
# Structured diagnosis (still works)
uv run python -m olav query "网络不通,按TCP/IP分层排查"

# Device inspection (still works)
uv run python -m olav query "对R1进行巡检"

# Solution reference (still works)
uv run python -m olav query "CRC错误怎么办"
```

### Disable Subagents if Needed
```python
from olav.agent import create_olav_agent

# Disable Phase 3, use Phase 1/2 only
agent = create_olav_agent(enable_subagents=False)
```

---

## Configuration

### Enable/Disable Subagents

```python
# In src/olav/agent.py or your code:

# Phase 3 mode (default: enabled)
agent = create_olav_agent(
    enable_skill_routing=True,
    enable_subagents=True,  # Phase 3: Subagent delegation
)

# Phase 2 mode (subagents disabled)
agent = create_olav_agent(
    enable_skill_routing=True,
    enable_subagents=False,  # Disable Phase 3
)
```

### Add Custom Subagents

```python
from olav.core.subagent_manager import get_subagent_middleware

# Define custom subagent
custom_subagent = {
    "name": "config-analyzer",
    "description": "Configuration comparison and validation",
    "system_prompt": "You are a config analysis expert...",
    "tools": [nornir_execute, search_capabilities],
}

# Add to middleware (future enhancement)
```

---

## Troubleshooting

### Issue: Subagent delegation doesn't happen

**Symptom**: Agent performs analysis directly without delegating

**Solutions**:
1. Check if subagents are enabled:
   ```python
   agent = create_olav_agent(enable_subagents=True)
   ```
2. Verify query complexity triggers delegation
3. Check system prompt includes subagent descriptions

### Issue: Subagent returns poor results

**Symptoms**: Incomplete analysis, missing information

**Solutions**:
1. Provide more detailed task description
2. Use combined macro → micro approach
3. Check subagent has access to necessary tools

### Issue: Tests fail

**Symptom**: Phase 3 tests fail

**Solutions**:
1. Run with debug output:
   ```bash
   uv run pytest tests/e2e/test_phase3_subagents.py -v -s
   ```
2. Verify DeepAgents SubAgentMiddleware is installed
3. Check subagent_manager.py is in src/olav/core/

---

## Performance Tips

### Optimize Subagent Usage

1. **Be specific with task descriptions**
   ```
   Good: "检查R1-R3路径,找出丢包的节点"
   Bad: "检查网络"
   ```

2. **Use the right subagent**
   - Path/topology → macro-analyzer
   - Specific device/interface → micro-analyzer
   - Unknown → Start with macro, then micro

3. **Leverage parallel delegation**
   ```
   # Agent can delegate multiple subagents in parallel
   task("macro-analyzer", "检查R1")
   task("macro-analyzer", "检查R2")
   task("macro-analyzer", "检查R3")
   ```

### Token Efficiency

- Subagents have isolated contexts → Main agent stays lean
- Summarized results → Less token bloat
- Specialized prompts → More efficient than general prompts

---

## Next Steps

### Learn More
- 📖 [DESIGN_V0.8.md](DESIGN_V0.8.md) - Complete design documentation
- 📖 [PHASE_3_COMPLETION_SUMMARY.md](PHASE_3_COMPLETION_SUMMARY.md) - Detailed deliverables
- 📖 [Phase 2 Guide](PHASE_2_QUICKSTART.md) - Skills and knowledge base

### Phase 4 Preview (Coming Soon)
- Additional subagents (config-analyzer, topology-explorer)
- Subagent memory and learning
- Performance analytics
- Advanced delegation patterns

### Contribute
- Propose new subagent types
- Improve subagent system prompts
- Add more delegation patterns to skills
- Share feedback via GitHub issues

---

## Summary

Phase 3 delivers **production-ready** subagent delegation:

✅ **Two Specialized Subagents**: Macro-analyzer (topology), Micro-analyzer (layers)
✅ **Automatic Delegation**: Agent intelligently selects right subagent
✅ **Token Efficient**: ~70% reduction vs traditional approach
✅ **Comprehensive Testing**: 13 E2E tests ensuring quality
✅ **Backward Compatible**: Phase 1 & 2 features unchanged
✅ **Complete Integration**: Works with skills, knowledge, solutions

**Ready to use**: `uv run python -m olav query "YOUR COMPLEX QUERY"`

---

*Last Updated: 2026-01-07*
*Phase 3 Status: ✅ COMPLETE*
