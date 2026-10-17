"""Command-line access to a saved Ridian mailbox."""

import argparse
import json
import sys
from pathlib import Path

from ._state import load_or_create_state, prepare_curl
from .client import Mailbox, MailboxError


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, help="HTTPS mailbox API origin, without /v1")
    parser.add_argument(
        "--state", type=Path, help="Private state file; defaults to ~/.config/ridian/"
    )
    parser.add_argument(
        "operation",
        choices=["setup", "prepare-curl", "status", "list", "message", "events", "ack-events"],
    )
    parser.add_argument("--message-id", help="Message ID returned by list")
    parser.add_argument("--cursor", help="Page cursor or processed event cursor")
    args = parser.parse_args()

    if args.operation == "message" and not args.message_id:
        parser.error("Supply a message ID from list using --message-id.")
    if args.operation == "ack-events" and not args.cursor:
        parser.error("Supply next_cursor from a fully processed events page using --cursor.")

    try:
        box = Mailbox(base_url=args.base_url, state=args.state)
        if args.operation == "prepare-curl":
            state = load_or_create_state(box.state_path, box.base_url)
            prepare_curl(box.state_path, state)
            print("Private curl files prepared. No network request made.")
            return 0
        if args.operation == "ack-events":
            box.acknowledge_events(args.cursor)
            print("Event cursor saved.")
            return 0
        if args.operation == "setup":
            result = box.setup()
        elif args.operation == "status":
            result = box.status()
        elif args.operation == "list":
            result = box.messages(cursor=args.cursor)
        elif args.operation == "message":
            result = box.message(args.message_id)
        else:
            result = box.events(cursor=args.cursor)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except MailboxError as error:
        print(str(error), file=sys.stderr)
        if error.retry_after is not None:
            print(f"Wait at least {error.retry_after} seconds before retrying.", file=sys.stderr)
        print("Keep the same state file; see the README troubleshooting section.", file=sys.stderr)
        return 1
    except (ValueError, OSError, KeyError, TypeError):
        print(
            "Check the HTTPS origin and private state file permissions. "
            "Preserve the existing state file when recovering access.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
