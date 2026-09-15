from __future__ import annotations

import shutil
import subprocess

_COMMANDS = (["pbcopy"], ["wl-copy"], ["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"])


def copy(text: str) -> bool:
    for cmd in _COMMANDS:
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text.encode(), check=False)
            return True
    return False
