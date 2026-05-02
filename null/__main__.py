"""Allow ``python -m null`` as an alias for the ``null`` console script."""

from __future__ import annotations

from null.cli import main

if __name__ == "__main__":
    main()
