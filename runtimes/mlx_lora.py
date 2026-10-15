#!/usr/bin/env python3
# SPDX-License-Identifier: BUSL-1.1
# Copyright © 2026 Zyvor AI Labs Private Limited
"""LoRA fine-tuning on this Mac with mlx-lm, reporting live loss/learning-rate metrics.

Single-Mac, single-GPU training: no multi-node or distributed claims. The dataset is a JSONL file under the managed
models directory (rows like {"text": ...} or {"prompt":..., "completion":...}); seeded, deduplicated 80/10/10 splits are made per run."""
import argparse
import json
import os
import re
import random
import hashlib
import math
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import confine, emit, models_root, ManagedProcess, artifact_digest  # noqa: E402

TRAIN = re.compile(r"Iter (\d+): Train loss ([\d.]+), Learning Rate ([\d.eE+-]+), It/sec ([\d.]+), Tokens/sec ([\d.]+).*?Peak mem ([\d.]+) GB")
VAL = re.compile(r"Iter (\d+): Val loss ([\d.]+)")


ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# mlx-lm >= 0.3x prints a table:  "   5  5.464 ▼  2,804  0.2k"  (train)   and   "   5  val 5.253  0.01s"  (validation)
TABLE_TRAIN = re.compile(r"^\s*(\d+)\s+([\d.]+)\s*[▼▲=]?\s+([\d,]+)\s+[\d.]+k?\s*$")
TABLE_VAL = re.compile(r"^\s*(\d+)\s+val\s+([\d.]+)")


def parse_line(line: str):
    line = ANSI.sub("", line)
    m = TABLE_VAL.match(line)
    if m:
        return dict(kind="metric", step=int(m.group(1)), valLoss=float(m.group(2)))
    m = TABLE_TRAIN.match(line)
    if m:
        return dict(kind="metric", step=int(m.group(1)), trainLoss=float(m.group(2)), tokensPerSec=float(m.group(3).replace(",", "")))
    m = TRAIN.search(line)
    if m:
        step, loss, lr, its, tps, peak = m.groups()
        return dict(kind="metric", step=int(step), trainLoss=float(loss), lr=float(lr), itPerSec=float(its), tokensPerSec=float(tps), peakGB=float(peak))
    m = VAL.search(line)
    if m:
        return dict(kind="metric", step=int(m.group(1)), valLoss=float(m.group(2)))
    return None


def prepare(data: Path, run_dir: Path, valid_fraction: float, seed=42) -> tuple[int, int]:
    if not 0<valid_fraction<0.5: raise SystemExit("invalid validation fraction")
    rows=[]; seen=set()
    for line in data.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        obj=json.loads(line)
        if not isinstance(obj,dict) or not any(k in obj for k in ("text","messages","prompt")):
            raise SystemExit("each dataset row must be a text, messages or prompt object")
        if "text" in obj and not isinstance(obj["text"],str): raise SystemExit("text must be a string")
        if "prompt" in obj and not all(isinstance(obj.get(k),str) for k in ("prompt","completion")): raise SystemExit("prompt and completion must be strings")
        if "messages" in obj:
            messages=obj["messages"]
            if not isinstance(messages,list) or not messages or not all(isinstance(m,dict) and m.get("role") in ("system","user","assistant") and isinstance(m.get("content"),str) for m in messages):
                raise SystemExit("invalid chat messages")
        canonical=json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(",",":"))
        if canonical not in seen: rows.append(canonical); seen.add(canonical)
    if len(rows)<4: raise SystemExit("dataset needs at least 4 unique rows")
    random.Random(seed).shuffle(rows)
    n_valid=max(1,int(len(rows)*valid_fraction)); n_test=n_valid
    split=run_dir/"data"; split.mkdir(parents=True,exist_ok=True)
    parts={"train":rows[n_valid+n_test:],"valid":rows[:n_valid],"test":rows[n_valid:n_valid+n_test]}
    for name,values in parts.items(): (split/(name+".jsonl")).write_text("\n".join(values)+"\n",encoding="utf-8")
    (split/"split.json").write_text(json.dumps(dict(seed=seed,uniqueRows=len(rows),counts={k:len(v) for k,v in parts.items()}),sort_keys=True))
    return len(parts["train"]),n_valid


def saved_step(adapter: Path) -> int:
    # Numbered snapshots are the only reliable step marker; live metric reports are not durable checkpoints.
    steps=[]
    for file in adapter.glob("*_adapters.safetensors"):
        prefix=file.name.split("_",1)[0]
        if prefix.isdigit(): steps.append((int(prefix),file))
    return max(steps,key=lambda item:item[0])[0] if steps else 0


def promote_checkpoints(segment: Path, adapter: Path, offset: int):
    import shutil
    for file in segment.glob("*"):
        if not file.is_file(): continue
        name=file.name
        prefix=name.split("_",1)[0]
        if name.endswith("_adapters.safetensors") and prefix.isdigit(): name=f"{int(prefix)+offset:07d}_adapters.safetensors"
        target=adapter/name; temp=adapter/(name+".tmp")
        shutil.copyfile(file,temp); temp.replace(target)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", required=True, help="Hugging Face repo id or local MLX model directory")
    p.add_argument("--data", required=True, help="JSONL dataset under the managed models directory")
    p.add_argument("--iters", type=int, default=100); p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--num-layers", type=int, default=8); p.add_argument("--learning-rate", type=float, default=1e-5)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--max-seq-length", type=int, default=512)
    a = p.parse_args(argv)
    if not (1 <= a.iters <= 5000 and 1 <= a.batch_size <= 32 and -1 <= a.num_layers <= 64 and 16 <= a.max_seq_length <= 4096):
        p.error("bounds: iters 1..5000, batch 1..32, layers -1..64, seq 16..4096")
    if not math.isfinite(a.learning_rate) or not 0<a.learning_rate<=1: p.error("learning rate must be finite and in (0,1]")
    data = confine(a.data)
    if not data.is_file():
        emit(kind="error", message=f"dataset not found: {data}")
        return 1
    if "/" in a.model and not a.model.startswith("/"):
        pass  # Hugging Face repo id: mlx-lm downloads it itself
    elif a.model.startswith("/"):
        confine(a.model)
    run_dir = models_root().parent / "runs" / (os.getenv("GRYVIA_JOB_ID") or str(int(time.time())))
    run_dir.mkdir(parents=True, exist_ok=True)
    identity=dict(model=a.model,datasetSha256=hashlib.sha256(data.read_bytes()).hexdigest(),seed=a.seed,
                  batch=a.batch_size,layers=a.num_layers,learningRate=a.learning_rate,sequence=a.max_seq_length)
    marker=run_dir/"training.json"
    if marker.exists() and json.loads(marker.read_text())!=identity: raise SystemExit("training inputs changed; refusing checkpoint reuse")
    marker.write_text(json.dumps(identity,sort_keys=True))
    n_train, n_valid = prepare(data, run_dir, 0.1, a.seed)
    adapter = run_dir / "adapter"
    # Resume after the owner returned / the agent restarted: the same job id keeps its run folder, so reuse the last
    # saved adapter weights. (mlx-lm restarts its iteration counter; the weights are what carries over.)
    # Recover complete numbered snapshots left in segment folders by an abruptly killed wrapper.
    for segment_dir in sorted((p for p in (adapter/"segments").glob("*") if p.name.isdigit()), key=lambda p:int(p.name)):
        if segment_dir.is_dir() and segment_dir.name.isdigit(): promote_checkpoints(segment_dir,adapter,int(segment_dir.name))
    completed=saved_step(adapter)
    resume = adapter / (f"{completed:07d}_adapters.safetensors" if completed else "adapters.safetensors")
    if completed:
        resume=next(f for f in adapter.glob("*_adapters.safetensors") if f.name.split("_",1)[0].isdigit() and int(f.name.split("_",1)[0])==completed)
    remaining=max(0,a.iters-completed)
    if remaining==0:
        import shutil
        shutil.copyfile(resume,adapter/"adapters.safetensors")
        emit(kind="result", adapterPath=str(adapter), sha256=artifact_digest(adapter), artifactType="directory", completedSteps=completed, iters=a.iters, resumeMode="adapter-weights-only")
        return 0
    emit(kind="progress", stage="train", trainRows=n_train, validRows=n_valid, model=a.model)
    cmd = [sys.executable, "-m", "mlx_lm", "lora", "--model", a.model, "--train", "--data", str(run_dir / "data"), "--iters", str(remaining),
           "--batch-size", str(a.batch_size), "--num-layers", str(a.num_layers), "--learning-rate", str(a.learning_rate),
           "--adapter-path", str(adapter), "--steps-per-report", "1" if a.iters <= 20 else "5", "--steps-per-eval", str(max(1, a.iters // 4)),
           "--val-batches", "2", "--seed", str(a.seed), "--max-seq-length", str(a.max_seq_length), "--save-every", str(max(10, min(50, a.iters // 4)))]
    if resume.is_file():
        cmd += ["--resume-adapter-file", str(resume)]
        emit(kind="progress", stage="resume", adapter=str(resume))
    # Each invocation saves numbered files starting from zero again. A segment folder prevents overwriting older checkpoints.
    segment=adapter/"segments"/str(completed)
    segment.mkdir(parents=True,exist_ok=True)
    cmd[cmd.index("--adapter-path")+1]=str(segment)
    managed=ManagedProcess(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    proc=managed.proc

    def _term(*_):
        managed.close()
        promote_checkpoints(segment,adapter,completed)
        emit(kind="progress", stage="yielded", completedSteps=saved_step(adapter), resumeMode="adapter-weights-only")
        sys.exit(143)
    signal.signal(signal.SIGTERM, _term)
    last_train = last_val = None
    tail = []
    for line in proc.stdout:
        tail = (tail + [line.rstrip()])[-8:]
        m = parse_line(line)
        if m:
            m["step"]+=completed
            emit(**m)
            last_train = m.get("trainLoss", last_train)
            last_val = m.get("valLoss", last_val)
    code = proc.wait()
    managed.close()
    promote_checkpoints(segment,adapter,completed)
    if code != 0 or not (adapter/"adapters.safetensors").exists():
        emit(kind="error", message="mlx_lm lora failed: " + " | ".join(tail[-3:]))
        return code or 1
    emit(kind="result", adapterPath=str(adapter), sha256=artifact_digest(adapter), artifactType="directory", completedSteps=a.iters, resumeMode="adapter-weights-only", finalTrainLoss=last_train, finalValLoss=last_val, iters=a.iters, trainRows=n_train, model=a.model)
    return 0


if __name__ == "__main__":
    sys.exit(main())
