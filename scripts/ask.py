"""Ask one question from the command line.

    python scripts/ask.py "How many vehicles are available right now?"
    python scripts/ask.py --role gm "Which vehicle has the best margin?"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.chat import answer_question  # noqa: E402
from app.config import ROLES  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask CarChat one question.")
    parser.add_argument("question")
    parser.add_argument("--role", choices=list(ROLES), default="sales")
    args = parser.parse_args()

    result = answer_question(args.question, ROLES[args.role])
    print(f"\nAnswer ({args.role}): {result.answer}")
    if result.sql:
        print(f"\nSQL: {result.sql}")
        print(f"\nRows ({len(result.rows)}):")
        print("  " + " | ".join(result.columns))
        for row in result.rows[:15]:
            print("  " + " | ".join(str(v) for v in row))
        if len(result.rows) > 15:
            print(f"  ... {len(result.rows) - 15} more")


if __name__ == "__main__":
    main()
