# OLAV v0.8 Quick Start Guide

## 🚀 5-Minute Setup

### 1. Initial Setup (First Time Only)
```bash
# Copy environment template
cp .env.example .env

# Edit .env with your values
# CRITICAL: Set these minimum values
# - LLM_API_KEY=sk-... (your OpenAI key)
# - DEVICE_USERNAME=your_username
# - DEVICE_PASSWORD=your_password
# - NETBOX_URL=http://your-netbox:8000
# - NETBOX_TOKEN=your_token
```

### 2. Verify Installation
```bash
# Test configuration loading
uv run python -c "from config.settings import settings; print('✅ OK')"

# Test LLM factory
uv run python -c "from src.olav.core.llm import LLMFactory; print('✅ LLM Factory Ready')"

# Test guard
uv run python -c "from src.olav.tools.guard import NetworkRelevanceGuard; print('✅ Guard Ready')"
```

### 3. Use in Your Code

#### Example 1: Access Settings
```python
from config.settings import settings

print(f"Using LLM: {settings.llm_model_name}")
print(f"Device: {settings.device_username}@{settings.netbox_url}")
```

#### Example 2: Create LLM Model
```python
from src.olav.core.llm import LLMFactory

chat = LLMFactory.get_chat_model()
response = chat.invoke([{"role": "user", "content": "Hello"}])
print(response.content)
```

#### Example 3: Check Query Relevance
```python
import asyncio
from src.olav.tools.guard import NetworkRelevanceGuard

async def check_query(query):
    guard = NetworkRelevanceGuard()
    result = await guard.check(query)
    print(f"Is network relevant: {result.is_network_relevant}")
    print(f"Confidence: {result.confidence}")
    print(f"Reason: {result.reason}")

# Run async check
asyncio.run(check_query("What is the BGP status?"))
```

## 📋 Common Tasks

### Run Tests
```bash
# Run all tests
uv run pytest

# Run specific test
uv run pytest tests/test_config.py -v

# Run with coverage
uv run pytest --cov=src/olav --cov-report=html
```

### Check Code Quality
```bash
# Lint with ruff
uv run ruff check src/ --fix

# Format code
uv run ruff format src/

# Type checking
uv run mypy src/
```

### Update Dependencies
```bash
# Add a package
uv add langchain-openai

# Add dev dependency
uv add --dev pytest-asyncio

# Update all dependencies
uv lock
uv sync
```

## 🔧 Troubleshooting

### "Settings validation error" on import
```bash
# Solution 1: Ensure .env exists
cp .env.example .env

# Solution 2: Check environment variables
$env:LLM_PROVIDER  # Should be empty or "openai"

# Solution 3: Rebuild virtual environment
Remove-Item .venv -Recurse -Force
uv sync
```

### "Module not found" errors
```bash
# Ensure all packages are installed
uv sync --dev

# Verify deepagents is installed
uv run python -c "from deepagents import create_deep_agent; print('✓')"
```

### Port already in use
```bash
# Find process using port 8000
Get-NetTCPConnection -LocalPort 8000 | Format-Table

# Kill process (if needed)
Stop-Process -Id <PID> -Force
```

## 📚 Documentation

- **Complete Configuration Guide**: See [PHASE_1_COMPLETION.md](PHASE_1_COMPLETION.md)
- **Architecture Overview**: See [DESIGN_V0.8.md](DESIGN_V0.8.md)
- **Code Reuse Strategy**: See [CODE_REUSE_ANALYSIS.md](CODE_REUSE_ANALYSIS.md)
- **OLAV Instructions**: See [.olav/OLAV.md](.olav/OLAV.md)

## 🎯 What's Next

Phase 2 (Coming Soon):
1. Migrate `prompt_manager.py` for template management
2. Create main entry point (`main.py`)
3. Build initial test suite
4. Integrate DeepAgents orchestrator

## ❓ FAQ

**Q: Why is configuration split between `.olav/` and `config/`?**  
A: `.olav/` contains OLAV-specific data (prompts, skills), while `config/` contains system-level settings. This follows industry patterns.

**Q: Can I use different LLM providers?**  
A: Yes! Just set `LLM_PROVIDER=ollama` or `LLM_PROVIDER=azure` and configure the appropriate API keys.

**Q: Where are my secrets stored?**  
A: In `.env` file (never committed). Environment variables are loaded at runtime, not stored in code.

**Q: How do I switch between development and production?**  
A: Set `OLAV_MODE=Production` in your `.env` file. Settings will adjust logging and safety checks accordingly.

---

**Status**: ✅ Phase 1 Complete  
**Last Updated**: 2026-01-07  
**Maintained by**: GitHub Copilot
