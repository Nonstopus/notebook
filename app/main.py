from __future__ import annotations

import sys


def main() -> int:
    message = (
        "Tkinter entrypoint removed. "
        "Use 'python -m app.main_qt' to launch the GUI."
    )
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
