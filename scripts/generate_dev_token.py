#!/usr/bin/env python
"""Display information about OLAV's single-token authentication.

In single-token mode, the token is auto-generated on server startup.
This script explains how to retrieve and use the token.

Usage:
    uv run python scripts/generate_dev_token.py
"""


def main() -> None:
    print("""
╔══════════════════════════════════════════════════════════════╗
║               OLAV Single Token Authentication               ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  OLAV uses a simplified single-token authentication model.   ║
║  The token is auto-generated when the server starts.         ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  HOW TO GET YOUR TOKEN                                       ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  1. Start the OLAV server:                                   ║
║     uv run python -m olav.server.app                         ║
║     # or: docker-compose up olav-server                      ║
║                                                              ║
║  2. Look for this in the console output:                     ║
║     ════════════════════════════════════════════════════     ║
║     🔑 ACCESS TOKEN (valid for 24 hours):                    ║
║        <your-token-here>                                     ║
║     ════════════════════════════════════════════════════     ║
║                                                              ║
║  3. Use the token in API requests:                           ║
║     Authorization: Bearer <your-token>                       ║
║                                                              ║
║     API Docs: http://localhost:8000/docs                     ║
║                                                              ║
╠══════════════════════════════════════════════════════════════╣
║  MULTI-WORKER DEPLOYMENT                                     ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  For Docker/multi-replica deployments, set a fixed token:    ║
║                                                              ║
║  # .env or docker-compose.yml                                ║
║  OLAV_API_TOKEN=your-secure-predefined-token                 ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
