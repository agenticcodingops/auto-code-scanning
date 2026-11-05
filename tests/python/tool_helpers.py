"""External application fixtures, shared by both hook shells."""
from pathlib import Path
import sys


def application(folder, name, source):
    folder.mkdir(parents=True, exist_ok=True)
    script = folder / (name + '_fixture.py')
    script.write_text(source, encoding='utf-8')
    executable = folder / name
    executable.write_text(f'#!/bin/sh\nexec "{Path(sys.executable).as_posix()}" "{script.as_posix()}" "$@"\n',
                          encoding='utf-8', newline='\n')
    executable.chmod(0o755)
    windows = folder / (name + '.cmd')
    windows.write_text(f'@"{sys.executable}" "{script}" %*\n@exit /b %errorlevel%\n', encoding='utf-8')
    return windows if sys.platform == 'win32' else executable
