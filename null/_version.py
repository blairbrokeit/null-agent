"""Single source of truth for the null package version.

Kept separate from ``__init__`` so that ``setup``/``pyproject`` parsing
does not import the rest of the package (which pulls in optional
provider SDKs).
"""

from __future__ import annotations

__version__ = "0.4.7"
