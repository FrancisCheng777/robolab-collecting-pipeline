"""Native collection H5 adapter for the RoboLab clip editor.

Plan persistence and inclusive editing are adapted from roboLab/lerobot_tools.
The original acquisition timeline is never resampled in the review UI.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

import h5py
import numpy as np
from ..vision import episode_views


@dataclass(frozen=True)
class Config:
    input_dir: str = "data/raw"
    output: str = "outputs/review/selected"
    fps: int = 15

    def validate(self):
        if not isinstance(self.fps, int) or isinstance(self.fps, bool) or not 1 <= self.fps <= 240:
            raise ValueError("fps must be an integer between 1 and 240")
        source, output = Path(self.input_dir).resolve(), Path(self.output).resolve()
        if not source.is_dir():
            raise ValueError(f"Input directory does not exist: {source}")
        if output == source or source in output.parents:
            raise ValueError("Output must be outside the input directory")


def valid_name(name):
    return (isinstance(name, str) and bool(name) and "\\" not in name
            and not PurePosixPath(name).is_absolute()
            and all(p not in ("", ".", "..") for p in name.split("/"))
            and name.endswith(".h5"))


def source_name(path, config):
    return Path(path).absolute().relative_to(Path(config.input_dir).absolute()).as_posix()


def discover(config):
    config.validate()
    root = Path(config.input_dir).absolute()
    return sorted(p for p in root.rglob("*.h5")
                  if p.is_file() and p.resolve().is_relative_to(root.resolve()))


def fingerprint(path: Path) -> dict:
    stat = path.stat()
    # JS Number cannot exactly represent epoch nanoseconds (> 2**53).
    return {"size": stat.st_size, "mtime_ns": str(stat.st_mtime_ns)}


def atomic_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def empty_plan() -> dict:
    return {"version": 1, "recordings": {}}


def normalize_plan(plan: dict) -> dict:
    if not isinstance(plan, dict) or plan.get("version") != 1:
        raise ValueError("Clip plan must be an object with version: 1")
    recordings = plan.get("recordings", {})
    if not isinstance(recordings, dict):
        raise ValueError("recordings must be an object")
    result = empty_plan()
    for name, edit in recordings.items():
        if not valid_name(name):
            raise ValueError(f"Invalid source filename: {name}")
        if not isinstance(edit, dict) or not isinstance(edit.get("drop", False), bool):
            raise ValueError(f"Invalid edit for {name}")
        intervals = edit.get("exclude", [])
        if not isinstance(intervals, list):
            raise ValueError("exclude must be a list of [start_seconds, end_seconds]")
        checked = []
        for pair in intervals:
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("Each exclusion needs start and end")
            if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in pair):
                raise ValueError("Clip bounds must be numeric")
            a, b = map(float, pair)
            if not math.isfinite(a) or not math.isfinite(b) or a < 0 or b < a:
                raise ValueError("Clip bounds must satisfy 0 <= start <= end and be finite")
            checked.append([a, b])
        merged = []
        for a, b in sorted(checked):
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(b, merged[-1][1])
            else:
                merged.append([a, b])
        item = {"drop": edit.get("drop", False), "exclude": merged}
        if "fingerprint" in edit:
            fp = edit["fingerprint"]
            if (not isinstance(fp, dict) or set(fp) != {"size", "mtime_ns"}
                or not isinstance(fp["size"], int) or isinstance(fp["size"], bool) or fp["size"] < 0
                or isinstance(fp["mtime_ns"], bool) or not isinstance(fp["mtime_ns"], (str, int))
                or not str(fp["mtime_ns"]).isascii() or not str(fp["mtime_ns"]).isdigit()):
                raise ValueError("Invalid source fingerprint")
            item["fingerprint"] = {"size": fp["size"], "mtime_ns": str(fp["mtime_ns"])}
        result["recordings"][name] = item
    return result


def load_plan(path: Path | None) -> dict:
    return empty_plan() if path is None or not path.exists() else normalize_plan(json.loads(path.read_text()))


def plan_digest(plan: dict, config: Config | None = None) -> str:
    obj = {"plan": normalize_plan(plan)}
    if config is not None:
        obj["config"] = asdict(config)
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


class Recording:
    def __init__(self, path, config):
        self.path, self.config = Path(path), config
        self.name = source_name(path, config)
        self.fingerprint = fingerprint(self.path)
        with h5py.File(path, "r") as f:
            if f.attrs.get("schema") not in ("pi05_plug_demo/1", "pi05_plug_demo/2") or not f.attrs.get("complete"):
                raise ValueError("Incomplete or unsupported native collection H5")
            from ..collector import METADATA_FIELDS
            self.collection_metadata = {k: f.attrs[k].item() if isinstance(f.attrs[k], np.generic) else f.attrs[k]
                                        for k in METADATA_FIELDS if k in f.attrs}
            self.schema = str(f.attrs["schema"])
            self.outcome, self.mock = str(f.attrs["outcome"]), bool(f.attrs["mock"])
            self.session = str(f.attrs["session"])
            self.task = str(f.attrs["task"])
            self.views = list(episode_views(f))
            n = int(f.attrs["frames"])
            if n < 1:
                raise ValueError("Empty recording")
            if "images" not in f or set(f["images"]) != set(self.views):
                raise ValueError("Image streams differ from the configured cameras")
            for key in ("timestamp", "q", "gripper_width", "state", "gripper_command_width"):
                if key not in f or len(f[key]) != n:
                    raise ValueError(f"Invalid {key}")
            def check_rows(name, obj):
                if isinstance(obj, h5py.Dataset) and obj.ndim and len(obj) != n:
                    raise ValueError(f"Row count mismatch: {name}")
            f.visititems(check_rows)
            self.grid = np.asarray(f["timestamp"], dtype=float)
            if not np.isfinite(self.grid).all() or np.any(np.diff(self.grid) <= 0):
                raise ValueError("Invalid timestamps")
            self.seconds = self.grid - self.grid[0]
            self.fps = float(json.loads(f.attrs["config_json"]).get("control_hz", config.fps))
            if not np.isfinite(self.fps) or self.fps <= 0:
                raise ValueError("Invalid collection FPS")
            # The plots show measured joints and commanded aperture, not the
            # legacy 8D absolute targets or the downstream normalized actions.
            values = np.column_stack((f["q"][:], f["gripper_command_width"][:]))
            if values.shape != (n, 8) or not np.isfinite(values).all():
                raise ValueError("Invalid joint/aperture values")
            self.aligned = {"action": values}
            self.lag = {}
            for view in self.views:
                ds = f[f"images/{view}"]
                if ds.shape != (n, 224, 224, 3) or ds.dtype != np.uint8:
                    raise ValueError(f"Invalid RGB data: {view}")
                stamps = np.asarray(f[f"camera_time/{view}"])
                if not np.isfinite(stamps).all():
                    raise ValueError(f"Invalid camera timestamps: {view}")
                self.lag[view] = (self.grid-stamps)*1000
            self.gaps = {"recording": [
                {"start": float(self.seconds[i]), "end": float(self.seconds[i+1])}
                for i in np.flatnonzero(np.diff(self.grid) > .2)]}
        self.check_source()

    def check_source(self):
        if fingerprint(self.path) != self.fingerprint:
            raise ValueError(f"Source changed since scan: {self.name}; restart review")

    def segments(self, plan):
        edit = plan.get("recordings", {}).get(self.name, {})
        if "fingerprint" in edit and edit["fingerprint"] != self.fingerprint:
            raise ValueError(f"Clip plan belongs to a different source version: {self.name}")
        if edit.get("drop", False):
            return []
        keep = np.ones(len(self.grid), dtype=bool)
        ns = np.floor(self.seconds*1e9 + .5).astype(np.int64)
        for a, b in edit.get("exclude", []):
            keep &= ~((ns >= math.floor(a*1e9+.5)) & (ns <= math.floor(b*1e9+.5)))
        indices = np.flatnonzero(keep)
        return [] if not len(indices) else list(np.split(indices, np.flatnonzero(np.diff(indices)>1)+1))

    def read_rgb(self, h5, camera, index):
        if camera not in self.views:
            raise ValueError("Unknown camera")
        return h5[f"images/{camera}"][index]

    def summary(self, plan=None):
        segments = self.segments(plan or empty_plan())
        return dict(name=self.name, valid=True, fingerprint=self.fingerprint,
                    duration=float(self.seconds[-1]), start=0., end=float(self.seconds[-1]),
                    frames=len(self.grid), kept_frames=sum(map(len, segments)),
                    episodes=len(segments), gaps=self.gaps, camera_views=self.views,
                    outcome=self.outcome, mock=self.mock, session=self.session, task=self.task,
                    fps=self.fps, **self.collection_metadata)


def scan(config, plan=None, paths=None):
    entries = []
    for path in (discover(config) if paths is None else paths):
        try:
            entries.append(Recording(path, config).summary(plan))
        except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
            entries.append(dict(name=source_name(path, config), valid=False, error=str(exc)))
    return sorted(entries, key=lambda e: (e.get('collection_total_index', 0), e['name']))
