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

The server URL and port depend on your OLAV server deployment. Check your `.env` file for:
- `OLAV_SERVER_PORT_EXTERNAL` - the external port exposed by the server (e.g., `18000`)

Set the server URL via environment variable or config file:

- Environment: `OLAV_SERVER_URL` (example: `http://localhost:${OLAV_SERVER_PORT_EXTERNAL}`)
- Provide a token via `OLAV_API_TOKEN`, or register to create a session token.

Note: `olav register --server ...` will also persist the server URL to `~/.olav/config.toml` for later commands.

Optional config file: `~/.olav/config.toml`

```toml
[server]
url = "http://localhost:18000"  # Match your .env OLAV_SERVER_PORT_EXTERNAL
timeout = 300
```

## Usage

```powershell
olav                 # Interactive chat loop
olav -q "check BGP"  # Single-shot query
olav status          # Basic connectivity + autocomplete checks
olav register -n my-laptop -t <MASTER_TOKEN> --server http://localhost:<PORT>
```
