#!/usr/bin/env python
"""Generate development JWT tokens for WebGUI testing.

Usage:
    uv run python scripts/generate_dev_token.py
    uv run python scripts/generate_dev_token.py --user operator --days 7
"""

import argparse
from datetime import timedelta


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate OLAV development JWT tokens")
    parser.add_argument(
        "--user",
        choices=["admin", "operator", "viewer"],
        default="admin",
        help="User to generate token for (default: admin)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=30,
        help="Token expiration in days (default: 30)",
    )
    parser.add_argument(
        "--env",
        action="store_true",
        help="Output in .env format",
    )
    args = parser.parse_args()

    # Direct JWT generation to avoid circular imports
    from datetime import UTC, datetime

    from jose import jwt

    from olav.core.settings import settings

    # User role mapping
    user_roles = {
        "admin": "admin",
        "operator": "operator",
        "viewer": "viewer",
    }

    expire = datetime.now(UTC) + timedelta(days=args.days)
    payload = {
        "sub": args.user,
        "role": user_roles[args.user],
        "exp": expire,
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    if args.env:
        print(f"NEXT_PUBLIC_DEV_TOKEN={token}")
    else:
        print(f"\n{'='*60}")
        print(f"  OLAV Development Token")
        print(f"{'='*60}")
        print(f"  User:    {args.user}")
        print(f"  Role:    {user_roles[args.user]}")
        print(f"  Expires: {args.days} days")
        print(f"{'='*60}")
        print(f"\n  Token:\n")
        print(f"  {token}")
        print(f"\n{'='*60}")
        print(f"\n  Add to webgui/.env.local:")
        print(f"  NEXT_PUBLIC_DEV_TOKEN={token}")
        print()


if __name__ == "__main__":
    main()
