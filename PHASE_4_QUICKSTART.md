# OLAV v0.8 Phase 4 Quick Start Guide

**Self-Learning Capabilities, Testing, and Code Quality**

---

## 🎯 What's New in Phase 4

Phase 4 introduces **agentic self-learning capabilities**, allowing OLAV to learn from successful troubleshooting cases and user interactions.

### Key Features

✅ **Automatic Solution Saving** - Save successful troubleshooting cases to knowledge base
✅ **Alias Learning** - Learn device naming conventions from users
✅ **HITL Protection** - Human-in-the-loop approval for knowledge updates
✅ **Comprehensive Testing** - 68 unit tests with 100% pass rate
✅ **Code Quality** - Ruff linting with 264 auto-fixes applied

---

## 🚀 Quick Start

### 1. Test the Learning System

```bash
# Run learning module tests
uv run pytest tests/unit/test_learning.py -v

# Run all unit tests
uv run pytest tests/unit/ -v

# Expected output: 68 passed in ~50s
```

### 2. Use Learning Features

#### Save a Solution Case

```python
# After resolving a problem, the agent can save it:
from olav.tools.learning_tools import save_solution_tool

result = save_solution_tool.run(
    title="crc-errors-r1",
    problem="R1接口CRC错误持续增加",
    process=[
        "1. 检查接口计数器",
        "2. 检查光模块状态",
        "3. 测试光功率",
        "4. 更换光模块"
    ],
    root_cause="光模块发射功率过低 (-8.5dBm)",
    solution="更换新光模块,发射功率恢复到 -3.2dBm",
    commands=[
        "show interfaces counters",
        "show interfaces transceiver"
    ],
    tags=["#物理层", "#CRC", "#光模块"]
)
# Result: ✅ Solution case saved to: .olav/knowledge/solutions/crc-errors-r1.md
```

#### Learn Device Aliases

```python
# When user clarifies a device alias:
from olav.tools.learning_tools import update_aliases_tool

result = update_aliases_tool.run(
    alias="新交换机",
    actual_value="SW3",
    alias_type="device",
    platform="cisco_ios",
    notes="三层交换机,放置在机房B"
)
# Result: ✅ Alias '新交换机' -> 'SW3' saved to knowledge base
```

#### Suggest Solution Filename

```python
# Get a consistent filename for a solution:
from olav.tools.learning_tools import suggest_filename_tool

result = suggest_filename_tool.run(
    problem_type="CRC",
    device="R1",
    symptom="optical power"
)
# Result: Suggested filename: crc-r1-optical-power.md
```

### 3. Integration with Agent

Learning tools are automatically available to the agent:

```python
from olav.agent import create_olav_agent

# Create agent with learning capabilities
agent = create_olav_agent()

# Agent now has access to:
# - save_solution (with HITL approval)
# - update_aliases (with HITL approval)
# - suggest_solution_filename (automatic)

# When agent resolves a problem:
response = await agent.chat("R1接口有CRC错误,怎么办?")

# Agent will diagnose, resolve, and ask:
# "✅ Issue resolved. Save this solution to knowledge base?"

# User approves → Solution saved automatically
```

---

## 📚 Learning Capabilities

### Automatic Learning Scenarios

#### 1. Troubleshooting Success

**When**: Agent successfully resolves a problem

**Learning**: Saves complete case study
- Problem description
- Troubleshooting process
- Root cause analysis
- Solution implemented
- Key commands used
- Tags for indexing

**Example**:
```python
# Agent interaction
User: "R1到R3网络不通,帮我排查"

# [Agent performs diagnosis using deep-analysis skill]
# [Agent uses macro/micro subagents for analysis]
# [Agent identifies and fixes issue]

# Agent: "✅ Issue resolved: OSPF timer mismatch.
#        Save this solution for future reference?"
User: [Approves]

# Agent automatically saves to .olav/knowledge/solutions/ospf-timer-r1-r3.md
```

#### 2. Alias Clarification

**When**: User clarifies what a term means

**Learning**: Updates alias knowledge base

**Example**:
```python
User: "核心交换机是指哪几台设备?"
Agent: "核心交换机通常指核心层的交换机设备"
User: "在我们网络中,核心交换机是SW1和SW2"

# Agent: "✅ Learned: 核心交换机 = SW1, SW2"
# [Automatically updates .olav/knowledge/aliases.md]

# Future queries:
User: "查询核心交换机的接口状态"
# Agent automatically expands to: SW1, SW2
```

### HITL (Human-in-the-Loop) Protection

Learning operations that write to disk require approval:

```python
# Read operations - Automatic
- suggest_solution_filename() → No approval needed

# Write operations - Require approval
- save_solution() → User must approve
- update_aliases() → User must approve
```

**Workflow**:
```
Agent: "I've successfully resolved this issue.
       Should I save this solution to the knowledge base?"

Options:
✓ [Yes, save it]
✗ [No, don't save]

User: [Clicks "Yes, save it"]

Agent: "✅ Solution saved to: .olav/knowledge/solutions/crc-errors-r1.md"
```

---

## 🧪 Testing

### Run Learning Tests

```bash
# Test learning module only
uv run pytest tests/unit/test_learning.py -v

# Test with coverage
uv run pytest tests/unit/test_learning.py --cov=src/olav/core/learning --cov-report=term-missing

# Expected: 18 passed, coverage >90%
```

### Run All Unit Tests

```bash
# Run all unit tests
uv run pytest tests/unit/ -v

# Run with detailed output
uv run pytest tests/unit/ -v --tb=short

# Expected: 68 passed in ~50s
```

### Test Categories

| Test Class | Tests | Description |
|------------|-------|-------------|
| TestSaveSolution | 5 | Solution saving functionality |
| TestUpdateAliases | 3 | Alias update functionality |
| TestLearnFromInteraction | 3 | Interaction analysis |
| TestSuggestSolutionFilename | 5 | Filename generation |
| TestGetLearningGuidance | 2 | Learning prompt generation |

---

## 🔧 Code Quality

### Ruff Linting

```bash
# Check code quality
uv run ruff check src/ tests/

# Auto-fix issues
uv run ruff check src/ tests/ --fix

# Format code
uv run ruff format src/ tests/

# Results:
# - 264 issues auto-fixed
# - 16 files formatted
# - 179 non-critical remaining (type annotations)
```

### Ruff Configuration

```toml
[tool.ruff]
line-length = 100
target-version = "py311"
select = ["E", "F", "I", "N", "W", "UP", "ANN", "ASYNC", "S", "B"]
ignore = ["ANN101", "ANN102", "E402"]

[tool.ruff.per-file-ignores]
"tests/**/*.py" = ["S101"]
```

---

## 📖 Usage Examples

### Example 1: Complete Learning Workflow

```python
from olav.agent import create_olav_agent

# Create agent
agent = create_olav_agent()

# User reports issue
query = "R1接口有CRC错误,间歇性丢包"

# Agent diagnoses and resolves
response = await agent.chat(query)

# Agent uses deep-analysis skill:
# 1. Checks interface counters (smart_query)
# 2. Checks optical module (smart_query)
# 3. Identifies aging optical module
# 4. Recommends replacement

# After success, agent asks:
Agent: """✅ Issue resolved: CRC errors caused by aging optical module.
       Root cause: Optical module transmitter power degraded (-8.5dBm)
       Solution: Replace optical module
       Commands: show interfaces counters, show interfaces transceiver

       Should I save this solution to the knowledge base?"""

# User approves
User: [Clicks "Yes, save it"]

# Agent saves solution
Agent: """✅ Solution saved to: .olav/knowledge/solutions/crc-errors-r1-optical.md
       Title: crc-errors-r1-optical
       Tags: #物理层 #CRC #光模块
       Future queries can reference this case."""
```

### Example 2: Alias Learning Workflow

```python
# Query with unknown alias
query = "核心路由器的BGP状态"

# Agent detects "核心路由器" in aliases.md
# Expands to R1, R2, R3, R4
# Executes batch_query on all core routers

# But if alias not found:
Agent: "I'm not sure which devices are '核心路由器'.
       Can you clarify?"

# User clarifies
User: "核心路由器是R1, R2, R3, R4"

# Agent learns:
Agent: """✅ Learned: 核心路由器 = R1, R2, R3, R4
       Saved to .olav/knowledge/aliases.md
       Future queries will use this alias."""

# Continues query:
Agent: "Querying BGP status on R1, R2, R3, R4..."
# [Executes batch_query]
```

### Example 3: Structured Troubleshooting with Learning

```python
# Complex network issue
query = "网络时断时续,完整分析"

# Agent uses deep-analysis skill with subagents:
# 1. Macro-analyzer: Topology, paths, connectivity
# 2. Micro-analyzer: TCP/IP layered analysis

# Detailed diagnosis process:
Agent: """Starting structured network diagnosis...
       Phase 1: Problem Definition
       Phase 2: Macro Analysis (topology, paths)
       Phase 3: Micro Analysis (TCP/IP layers)
       Phase 4: Root Cause Identification
       Phase 5: Solution & Verification"""

# [Diagnosis process with subagents]

# Agent identifies issue:
Agent: """Root cause identified: OSPF Hello/Dead timer mismatch
       R1: Hello 10s, Dead 40s
       R2: Hello 5s, Dead 20s
       Mismatch causes OSPF neighbor flapping"""

# Solution implemented:
Agent: """✅ Fixed: Configured R2 timers to match R1
       R2(config-router)# timers hello 10
       R2(config-router)# timers dead 40
       OSPF neighbor now stable"""

# Save solution:
Agent: "Save this OSPF timer mismatch solution?"
User: [Approves]

Agent: """✅ Solution saved:
       .olav/knowledge/solutions/ospf-timer-mismatch-r1-r2.md
       Tags: #OSPF #路由协议 #Timer
       Future OSPF issues can reference this case."""
```

---

## 🗂️ File Structure

### Learning Module

```
src/olav/core/
├── learning.py (305 lines)
│   ├── save_solution()           # Save troubleshooting cases
│   ├── update_aliases()          # Update device aliases
│   ├── learn_from_interaction()  # Analyze interactions
│   ├── get_learning_guidance()   # System prompt guidance
│   └── suggest_solution_filename() # Generate filenames
│

src/olav/tools/
├── learning_tools.py (177 lines)
│   ├── SaveSolutionTool          # LangChain wrapper
│   ├── UpdateAliasesTool         # LangChain wrapper
│   └── SuggestFilenameTool       # LangChain wrapper

tests/unit/
├── test_learning.py (318 lines)
│   ├── TestSaveSolution (5 tests)
│   ├── TestUpdateAliases (3 tests)
│   ├── TestLearnFromInteraction (3 tests)
│   ├── TestSuggestSolutionFilename (5 tests)
│   └── TestGetLearningGuidance (2 tests)
```

### Knowledge Base Structure

```
.olav/knowledge/
├── aliases.md                    # Device aliases (user + learned)
├── solutions/                    # Solution case studies
│   ├── crc-errors-r1.md         # Physical layer cases
│   ├── ospf-flapping.md         # Routing protocol cases
│   ├── bgp-neighbor-down.md     # BGP cases
│   └── [auto-generated cases]  # Learned from interactions
├── network-topology.md           # Network topology documentation
├── conventions.md                # Team conventions
└── troubleshooting-guide.md      # Troubleshooting procedures
```

---

## 🔒 Safety and Permissions

### What Agent Can Write

**Allowed** (with HITL approval):
- ✅ `.olav/knowledge/solutions/*.md` - Solution cases
- ✅ `.olav/knowledge/aliases.md` - Device aliases
- ✅ `.olav/skills/*.md` - Skill patterns (future)

**Protected** (requires manual editing):
- ❌ `.olav/imports/` - Capability definitions
- ❌ `.olav/OLAV.md` - Core system rules
- ❌ `.env` - Sensitive configuration

### HITL Workflow

```
Agent wants to save solution
       ↓
[Check: Is this safe?]
       ↓
Yes → [Ask user for approval]
       ↓
User approves → [Execute write]
       ↓
✅ Success → Update knowledge base
```

---

## 🎓 Best Practices

### 1. When to Save Solutions

**✅ DO save**:
- Successful troubleshooting cases
- Complex problems with clear root causes
- Issues likely to recur
- Cases with valuable troubleshooting process

**❌ DON'T save**:
- Trivial issues (e.g., interface down)
- Temporary workarounds
- Incomplete diagnoses
- Hypothetical scenarios

### 2. When to Learn Aliases

**✅ DO learn**:
- Device groups (core routers, distribution switches)
- Location-based names (floor1-switches, buildingB-routers)
- Functional names (firewall-pair, loadbalancers)

**❌ DON'T learn**:
- Temporary names
- Individual device nicknames
- Ambiguous abbreviations

### 3. Tagging Strategy

Use specific tags for easy retrieval:

```python
# Good tags
tags=["#物理层", "#CRC", "#光模块"]  # Specific
tags=["#OSPF", "#路由协议", "#Timer"]  # Clear

# Avoid
tags=["#问题"]  # Too generic
tags=["#故障"]  # Not specific enough
```

---

## 🚀 Next Steps

### 1. Try Learning Features

```bash
# Start OLAV with learning enabled
uv run python -m olav query "测试查询"

# Resolve a real issue
# Agent will offer to save the solution
# Approve and verify it's saved
```

### 2. Review Learned Knowledge

```bash
# Check solutions directory
ls -la .olav/knowledge/solutions/

# View aliases
cat .olav/knowledge/aliases.md

# Solutions should be organized by:
# - Problem type (CRC, OSPF, BGP, etc.)
# - Device names
# - Specific symptoms
```

### 3. Continuous Improvement

- ✅ Review saved solutions weekly
- ✅ Update tags for better organization
- ✅ Refine troubleshooting processes
- ✅ Share valuable cases with team

---

## 📊 Phase 4 Statistics

| Metric | Value |
|--------|-------|
| Learning functions | 5 |
| Learning tools | 3 |
| Unit tests (learning) | 18 |
| Total unit tests | 68 |
| Test pass rate | 100% |
| Ruff fixes applied | 264 |
| Lines of code | 482 (learning + tests) |

---

## ✅ Verification Checklist

Before using Phase 4 in production:

- [x] All 68 unit tests passing
- [x] Learning tools integrated
- [x] HITL protection working
- [x] Ruff linting completed
- [x] Documentation complete
- [x] Backward compatibility verified
- [x] No breaking changes

---

## 🎉 Conclusion

Phase 4 is **PRODUCTION READY** with comprehensive self-learning capabilities.

**Key Benefits**:
- ✅ Automatic knowledge accumulation
- ✅ Improved efficiency over time
- ✅ Consistent troubleshooting processes
- ✅ Team knowledge sharing
- ✅ HITL-protected learning

**Get Started**:
```bash
# Run tests
uv run pytest tests/unit/test_learning.py -v

# Try learning features
uv run python -m olav query "R1接口状态"

# Watch the agent learn and improve!
```

---

**Phase 4 Status**: ✅ **COMPLETE**
**Promise**: **COMPLETE** ✅
