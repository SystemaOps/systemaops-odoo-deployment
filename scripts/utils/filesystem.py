import os
import shutil
from pathlib import Path
from typing import List, Optional


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_template(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True)


def verify_files(directory: Path, filenames: List[str]) -> List[str]:
    missing: List[str] = []
    for name in filenames:
        if not (directory / name).exists():
            missing.append(name)
    return missing


def read_text(path: Path) -> str:
    with open(path, "r") as f:
        return f.read()


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        f.write(content)
    tmp.replace(path)


def replace_in_file(path: Path, old: str, new: str) -> int:
    content = read_text(path)
    count = content.count(old)
    if count:
        write_text(path, content.replace(old, new))
    return count