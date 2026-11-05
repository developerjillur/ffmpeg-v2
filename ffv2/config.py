from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .errors import FFV2Error

CODE_ROOT = Path(__file__).resolve().parents[1]
PROJECT = Path(os.environ.get('FFV2_PROJECT_ROOT', str(Path.cwd()))).expanduser().resolve()
WORK = Path(os.environ.get('FFV2_WORK_ROOT', str(PROJECT / '.ffv2-work'))).expanduser().resolve()
PROJECT_MOUNT = PROJECT
HOST_LOCK = Path(os.environ.get('FFV2_HOST_LOCK', str(Path.home() / 'Library/Caches/ffmpeg-v2/host.lock'))).expanduser().absolute()
GIB = 1024 ** 3


def within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def check_mounts(path):
    path = Path(path).absolute()
    mounts = [Path(value).expanduser().absolute() for value in os.environ.get('FFV2_REQUIRED_MOUNTS', '').split(os.pathsep) if value]
    if len(path.parts) > 2 and path.parts[1] == 'Volumes':
        mounts.append(Path('/Volumes') / path.parts[2])
    for mount in mounts:
        if within(path, mount) and not os.path.ismount(mount):
            raise FFV2Error("storage_unmounted", "প্রয়োজনীয় volume mounted নেই।",
                            details={"mount": str(mount)}, exit_code=75)


@dataclass(frozen=True)
class Settings:
    state: Path = PROJECT / ".runtime"
    output_roots: tuple = (PROJECT, WORK / "Work")
    input_roots: tuple = (PROJECT,)
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    engine_selection_id: str = ""
    host_lock: Path = HOST_LOCK

    @classmethod
    def load(cls, *, state=None, input_roots=None, use_active=True):
        from .engine import selection
        selected = selection() if use_active else None
        defaults = selected["binaries"] if selected else {"ffmpeg": "ffmpeg", "ffprobe": "ffprobe"}
        ffmpeg = os.environ.get("FFV2_FFMPEG", defaults["ffmpeg"])
        ffprobe = os.environ.get("FFV2_FFPROBE", defaults["ffprobe"])
        if os.environ.get('FFV2_RELEASE_ID') and (ffmpeg != defaults['ffmpeg'] or ffprobe != defaults['ffprobe']):
            raise FFV2Error('release_binary_override', 'Installed code/engine pair-এ binary override নয়; verified release install ব্যবহার করুন।')
        identity = selected["selection_id"] if selected and ffmpeg == defaults["ffmpeg"] and ffprobe == defaults["ffprobe"] else ""
        return cls(state=Path(state or os.environ.get("FFV2_STATE_DIR", PROJECT / ".runtime")).absolute(),
                   input_roots=tuple(Path(p).resolve() for p in (input_roots or (PROJECT,))),
                   ffmpeg=ffmpeg, ffprobe=ffprobe, engine_selection_id=identity)

    def ensure_state(self):
        check_mounts(self.state)
        resolved = self.state.resolve()
        if any(character in str(resolved) for character in ("\0", "\n", "\r")):
            raise FFV2Error("invalid_state", "Resolved runtime directory-তে control character গ্রহণযোগ্য নয়।")
        if not any(within(resolved, p.resolve()) for p in self.output_roots):
            raise FFV2Error("state_path_denied", "Runtime data project অথবা configured work root-এর মধ্যে থাকতে হবে।")
        if self.state.is_symlink():
            raise FFV2Error("state_path_denied", "Runtime directory symlink হতে পারবে না।")
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(resolved, 0o700)
        return resolved
