"""Private Windows launch gate; no project code runs before job assignment.

Invoked by absolute filename with ``python -I -S``, so startup hooks and imports
from the project cannot spawn a child before the controller grants ownership.
"""

import subprocess
import sys


def main() -> int:
    if sys.stdin.buffer.read(1) != b"1":
        return 1
    return subprocess.call(sys.argv[1:], stdin=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
