"""Allow `python -m tavern ...` to work."""

from tavern.cli import main
import sys

if __name__ == "__main__":
    sys.exit(main())
