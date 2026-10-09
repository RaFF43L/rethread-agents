#!/usr/bin/env python
"""Runs database migrations (Alembic).

Usage:
    python migrate.py               # upgrade to the latest version
    python migrate.py upgrade head  # explicit upgrade
    python migrate.py downgrade -1  # rollback one revision
    python migrate.py current       # show current revision
    python migrate.py history       # show history
"""
import sys

from alembic.config import Config
from alembic import command


def main():
    alembic_cfg = Config("alembic.ini")

    if len(sys.argv) < 2:
        command.upgrade(alembic_cfg, "head")
        print("Migrations applied successfully.")
        return

    action = sys.argv[1]

    if action == "upgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        command.upgrade(alembic_cfg, revision)
        print(f"Upgraded to: {revision}")

    elif action == "downgrade":
        revision = sys.argv[2] if len(sys.argv) > 2 else "-1"
        command.downgrade(alembic_cfg, revision)
        print(f"Downgraded to: {revision}")

    elif action == "current":
        command.current(alembic_cfg, verbose=True)

    elif action == "history":
        command.history(alembic_cfg, verbose=True)

    elif action == "stamp":
        revision = sys.argv[2] if len(sys.argv) > 2 else "head"
        command.stamp(alembic_cfg, revision)
        print(f"Stamped database at: {revision}")

    else:
        print(f"Unknown action: {action}")
        print("Available: upgrade, downgrade, current, history, stamp")
        sys.exit(1)


if __name__ == "__main__":
    main()
