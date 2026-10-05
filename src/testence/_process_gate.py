"""Private Windows launch gate; no project code runs before job assignment.

Invoked by absolute filename with ``python -I -S``, so startup hooks and imports
from the project cannot spawn a child before the controller grants ownership.
"""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    # Windows venv python.exe may be a redirector which spawns the interpreter
    # before Popen returns. Report the actual gated interpreter, not just its
    # launcher's PID, and do not release project code until both are owned.
    ready = Path(sys.argv[1])
    pending = ready.with_suffix(".pending")
    pending.write_text(str(os.getpid()), encoding="ascii")
    pending.replace(ready)
    if sys.stdin.buffer.read(1) != b"1":
        return 1
    return subprocess.call(sys.argv[2:], stdin=subprocess.DEVNULL)


if __name__ == "__main__":
    sys.exit(main())
