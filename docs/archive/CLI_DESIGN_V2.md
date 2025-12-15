# OLAV CLI v2 Design Document

## 1. Vision & Philosophy

**"The Terminal is the Dashboard."**

OLAV CLI v2 aims to be the primary, professional-grade interface for the OLAV Network Operations Platform. It is designed for Network Reliability Engineers (NREs) who prefer the efficiency, scriptability, and focus of the command line.

### Core Principles
1.  **Thin Client**: The CLI is a lightweight "remote control". All heavy lifting (LLM inference, network connections, state management) happens on the Server (Container).
2.  **Rich & Interactive**: Uses `Rich` for beautiful output and `Prompt Toolkit` for a powerful REPL experience (autocompletion, history).
3.  **Unix Philosophy**: Composable commands, standard streams (stdin/stdout), and structured output (JSON/YAML) for piping.
4.  **Stateful Sessions**: Seamlessly resume conversations across machines or interruptions.

## 2. Architecture

```mermaid
graph TD
    User[User Terminal] -->|CLI v2| Client[Thin Client (Python)]
    Client -->|HTTP/WebSocket| API[OLAV API Server]
    API -->|LangGraph| Orchestrator[Workflow Orchestrator]
    Orchestrator -->|Postgres| DB[(State DB)]
```

### Tech Stack
-   **Language**: Python 3.10+
-   **Framework**: `Typer` (CLI structure)
-   **UI/Formatting**: `Rich` (Tables, Markdown, Spinners, Live Live)
-   **REPL**: `prompt_toolkit` (History, Auto-completion, Key bindings)
-   **Network**: `httpx` (Async HTTP/2)
-   **Config**: `pydantic-settings` (Env vars, `.env`, `~/.olav/config.toml`)

## 3. Key Features

### 3.1 Interactive REPL (The "Cockpit")
The default mode `olav` enters a persistent interactive session.

-   **Streaming Thinking Process**: Real-time visualization of the Agent's thought process (e.g., "Analyzing BGP neighbors...", "Querying SuzieQ...").
-   **Syntax Highlighting**: SQL, Python, JSON, and Network Configs are automatically highlighted.
-   **Auto-completion**:
    -   Commands (`/help`, `/clear`, `/mode`)
    -   Device names (fetched from NetBox cache)
    -   SuzieQ table names
-   **Key Bindings**:
    -   `Ctrl+R`: Search history
    -   `Ctrl+L`: Clear screen
    -   `Ctrl+D`: Exit

### 3.2 Command Structure

```bash
# Interactive Session (Default)
olav

# Single Shot Query
olav query "Show me BGP state of R1"

# Expert Mode (Deep Dive)
olav query -e "Audit all edge routers for security risks"

# Inspection
olav inspect run daily-check
olav inspect list
olav inspect report <report_id>

# Session Management
olav session list
olav session resume <session_id>
olav session delete <session_id>

# RAG / Documents
olav doc upload ./cisco_guide.pdf
olav doc search "BGP configuration"

# Configuration
olav config set server_url http://olav.internal:8000
olav login
```

### 3.3 Output Modes
-   **Human (Default)**: Rich text, tables, emojis, markdown.
-   **JSON (`--json`)**: Raw JSON output for `jq` processing.
-   **Raw (`--raw`)**: Plain text without formatting.

### 3.4 File Handling
-   **Upload**: `olav doc upload` streams files to the server.
-   **Download**: `olav report download <id>` saves reports locally.

## 4. Implementation Plan

### Phase 1: Foundation (The "Thin" Client)
-   [ ] Refactor `olav.cli` to remove all server-side dependencies (`olav.agents`, `olav.tools`).
-   [ ] Implement `OlavClient` class using `httpx`.
-   [ ] Create `~/.olav/config.toml` management.

### Phase 2: The REPL Experience
-   [ ] Integrate `prompt_toolkit` for the input loop.
-   [ ] Implement streaming response parser (Server-Sent Events or WebSocket).
-   [ ] Build `ThinkingDisplay` component using `Rich.Live`.

### Phase 3: Advanced Features
-   [ ] **TUI Dashboard**: A read-only view using `Textual` to show system status, recent alerts, and topology (ASCII/Unicode).
-   [ ] **Auto-completion**: API endpoint to fetch dynamic completion data (device names).
-   [ ] **File Operations**: Upload/Download progress bars.

## 5. API Requirements
To support this CLI, the Server must expose:
-   `POST /v1/chat/completions` (OpenAI-compatible or custom streaming endpoint)
-   `GET /v1/sessions`
-   `GET /v1/autocomplete/devices`
-   `POST /v1/documents/upload`

## 6. Migration Guide
-   Users of the old `olav.py` (local execution) will be encouraged to use the new client connecting to the Docker container.
-   The old web UI is archived (deprecated).

---
*Drafted by GitHub Copilot on 2025-12-02*
