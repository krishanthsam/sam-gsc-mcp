"""`python -m sam_gsc_mcp` entry point."""

import sys

if sys.version_info < (3, 10):
    sys.exit(
        "sam-gsc-mcp needs Python 3.10 or newer (you have "
        f"{sys.version_info.major}.{sys.version_info.minor}). Install a newer Python or use uvx."
    )

from sam_gsc_mcp.server import main  # noqa: E402

if __name__ == "__main__":
    main()
