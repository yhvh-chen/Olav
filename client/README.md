# OLAV Client (CLI)

This is the lightweight, installable OLAV CLI client.

It talks to an existing OLAV server over HTTP/SSE only (no local LangGraph, no NetBox/OpenSearch dependencies).

## Install

From this repository root:

```powershell
cd client
python -m pip install .
```

Or with `uv`:

```powershell
# From repository root
uv run --project client olav --help

# Or if you prefer running inside the client folder
cd client
uv sync
uv run olav --help
```

Note: this repository also contains the full OLAV package which exposes an `olav` command.
To run the standalone client CLI from the monorepo, prefer `uv run --project client olav ...`.

## Configure

- Set server URL: `OLAV_SERVER_URL` (example: `http://localhost:18001`)
- Provide a token via `OLAV_API_TOKEN`, or register to create a session token.

Note: `olav register --server ...` will also persist the server URL to `~/.olav/config.toml` for later commands.

Optional config file: `~/.olav/config.toml`

```toml
[server]
url = "http://localhost:18001"
timeout = 300
```

## Usage

```powershell
olav                 # Interactive chat loop
olav -q "check BGP"  # Single-shot query
olav status          # Basic connectivity + autocomplete checks
olav register -n my-laptop -t <MASTER_TOKEN> --server http://localhost:18001
```
