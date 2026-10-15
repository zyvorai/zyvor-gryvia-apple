# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""Shared helpers for model-lifecycle runtime wrappers (download, benchmark, evaluate, quantize)."""
import atexit
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HOSTS = ("huggingface.co", "hf.co")


def models_root() -> Path:
    root = Path(os.getenv("GRYVIA_MODELS_DIR") or (Path.home() / "gryvia/state/models"))
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def confine(path: str) -> Path:
    """Resolve `path` and require it to live under the models root or the training runs folder (no traversal, no symlink escape)."""
    p = Path(path).expanduser().resolve()
    roots = (models_root(), (models_root().parent / "runs").resolve())
    if not any(r == p or r in p.parents for r in roots):
        raise SystemExit(f"path outside managed directories: {p}")
    return p


def mlx_python() -> str:
    """Python interpreter that has mlx-lm: $GRYVIA_MLX_PYTHON, else ~/gryvia/venv, else the current interpreter."""
    for c in (os.getenv("GRYVIA_MLX_PYTHON"), str(Path.home() / "gryvia/venv/bin/python")):
        if c and Path(c).is_file():
            return c
    return sys.executable


def artifact_digest(path: Path) -> str:
    """File SHA-256, or SHA-256 of a canonical directory manifest. Symlinks are never followed."""
    if path.is_symlink(): raise SystemExit("symlink artifact refused")
    def digest_file(file):
        h=hashlib.sha256()
        with file.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""): h.update(chunk)
        return h.hexdigest()
    if path.is_file(): return digest_file(path)
    if not path.is_dir(): raise SystemExit("artifact does not exist")
    rows=[]
    for file in sorted(path.rglob("*")):
        if file.is_symlink(): raise SystemExit("symlink in artifact refused")
        if file.is_file(): rows.append(dict(path=file.relative_to(path).as_posix(),bytes=file.stat().st_size,sha256=digest_file(file)))
    if not rows: raise SystemExit("empty artifact directory")
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(",",":")).encode()).hexdigest()


def verify_inputs():
    raw=os.getenv("GRYVIA_INPUT_MANIFEST")
    if not raw: return
    try: items=json.loads(raw)
    except ValueError: raise SystemExit("invalid input manifest")
    if not isinstance(items,list) or len(items)>8: raise SystemExit("invalid input manifest")
    for item in items:
        if not isinstance(item,dict) or not isinstance(item.get("sha256"),str) or len(item["sha256"])!=64:
            raise SystemExit("invalid input digest")
        path=confine(item["path"])
        if artifact_digest(path)!=item["sha256"]: raise SystemExit("artifact digest mismatch; refusing execution")


def _kill_group(proc: subprocess.Popen, grace=0.4) -> None:
    # Kill the group even when its leader has exited: descendants may still hold pipes/GPU allocations.
    try: os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError): return
    deadline=time.monotonic()+grace
    while time.monotonic()<deadline:
        proc.poll()
        # macOS reports EPERM, not ESRCH, once only unreaped exited members remain.
        try: os.killpg(proc.pid,0)
        except (ProcessLookupError, PermissionError): break
        time.sleep(0.02)
    try: os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError): pass
    try: proc.wait(timeout=1)
    except subprocess.TimeoutExpired: pass


class ManagedProcess:
    """Own a process group and stop it if this wrapper loses its parent agent.

    This covers bundled wrappers; arbitrary administrator-configured executables are still trusted.
    """
    def __init__(self,cmd,**kw):
        self.parent=os.getppid(); self.closed=threading.Event(); self.stop_lock=threading.Lock()
        self.proc=subprocess.Popen(cmd,start_new_session=True,**kw)
        self.watcher=threading.Thread(target=self._watch,daemon=True)
        self.watcher.start()
        atexit.register(self.close)

    def _watch(self):
        while not self.closed.wait(0.1):
            if os.getppid()!=self.parent:
                self.stop(); return

    def stop(self):
        with self.stop_lock:
            if self.closed.is_set(): return
            self.closed.set(); _kill_group(self.proc)

    def close(self):
        self.stop()
        if threading.current_thread() is not self.watcher: self.watcher.join(timeout=1)


def run_group(cmd, timeout=None, **kw) -> subprocess.CompletedProcess:
    """Bounded subprocess group cleanup on completion, timeout, cancellation and parent loss."""
    kw.setdefault("capture_output", True); kw.setdefault("text", True); kw.setdefault("stdin", subprocess.DEVNULL)
    managed=ManagedProcess(cmd,stdout=subprocess.PIPE if kw.pop("capture_output") else None,stderr=subprocess.PIPE,**kw)
    proc=managed.proc
    previous=signal.signal(signal.SIGTERM,lambda *_: (managed.stop(),sys.exit(143)))
    try:
        out,err=proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(cmd,proc.returncode,out,err)
    except subprocess.TimeoutExpired:
        managed.stop()
        # Never wait indefinitely on inherited pipes held by a non-cooperative descendant.
        proc.communicate(timeout=2)
        raise
    finally:
        managed.close(); signal.signal(signal.SIGTERM,previous)


def emit(**obj) -> None:
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def find_tool(name: str) -> str:
    candidates = [Path(os.getenv("GRYVIA_LLAMA_BIN_DIR", "")) / name] if os.getenv("GRYVIA_LLAMA_BIN_DIR") else []
    candidates += [Path("/opt/homebrew/bin") / name, Path("/usr/local/bin") / name]
    for c in candidates:
        if c.is_file() and os.access(c, os.X_OK):
            return str(c)
    found = shutil.which(name)
    if found:
        return found
    emit(kind="error", message=f"{name} not found; install llama.cpp (brew install llama.cpp) or set GRYVIA_LLAMA_BIN_DIR")
    sys.exit(127)

# Every bundled lifecycle wrapper importing these helpers checks its managed inputs before loading a model.
verify_inputs()
