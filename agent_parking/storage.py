"""Private JSON files: owner-only directories and atomic replacement."""

import json
import os


def private_dir(directory):
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)  # mkdir's mode is filtered by the umask


def write_json(path, value):
    """Write `value` to `path` (0600), replacing it atomically: a failure midway keeps
    the previous file."""
    private_dir(path.parent)
    tmp = path.parent / (".%s.%d.tmp" % (path.name, os.getpid()))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
