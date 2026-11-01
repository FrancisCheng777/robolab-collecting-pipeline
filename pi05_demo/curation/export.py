"""Publish selected native H5 fragments for the existing pipeline exporter."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import h5py

from ..episode import inspect_episode
from ..export_actions import aligned_records
from .core import Recording, atomic_json, discover, normalize_plan, plan_digest, source_name


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def copy_segment(rec, indices, target, digest):
    """Slice every row together, preserving clocks, metadata and labels."""
    start, stop = int(indices[0]), int(indices[-1])+1
    rec.check_source()
    with h5py.File(rec.path, 'r') as source, h5py.File(target, 'x') as dest:
        dest.attrs.update(dict(source.attrs))
        dest.attrs['complete'] = False
        def copy(name, obj):
            if isinstance(obj, h5py.Group):
                dest.require_group(name).attrs.update(dict(obj.attrs))
                return
            if not obj.ndim:
                source.copy(obj, dest, name=name)
                return
            shape = (stop-start, *obj.shape[1:])
            opts = {'chunks': (1, *obj.shape[1:]), 'compression': 'lzf'} if obj.ndim > 1 else {}
            out = dest.create_dataset(name, shape=shape, dtype=obj.dtype, **opts)
            out.attrs.update(dict(obj.attrs))
            # Bound memory even for long recordings / full-resolution additions.
            for offset in range(0, stop-start, 64):
                end = min(stop-start, offset+64)
                out[offset:end] = obj[start+offset:start+end]
        source.visititems(copy)
        dest.attrs.update(frames=stop-start, complete=True,
                          review_source=rec.name, review_source_sha256=digest,
                          review_start_frame=start, review_stop_frame_exclusive=stop)
    rec.check_source()
    inspect_episode(target, allow_mock=True)
    with h5py.File(target, 'r') as f:
        # This also rejects gaps / impossible motion instead of connecting
        # across removed data. The training exporter recomputes per fragment.
        aligned_records(f, rec.fps)


def export_dataset(config, plan, *, progress=None):
    config.validate()
    plan = normalize_plan(plan)
    progress = progress or (lambda event: None)
    paths = {source_name(p, config): p for p in discover(config)}
    unknown = set(plan['recordings']) - paths.keys()
    if unknown:
        raise ValueError(f'Plan references missing sources: {sorted(unknown)}')
    output = Path(config.output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    versions = output.parent / f'.{output.name}.versions'
    if output.exists() or output.is_symlink():
        if not output.is_symlink() or output.resolve().parent != versions.resolve():
            raise ValueError('Output already exists and is not managed by this editor')
    lock = output.parent / f'.{output.name}.export.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    staging = None
    link = output.parent / f'.{output.name}.{uuid.uuid4().hex}.link'
    try:
        with os.fdopen(fd, 'w') as stream:
            stream.write(str(os.getpid()))
        progress({'phase': 'scan'})
        skipped, work, fingerprints = [], [], {}
        for name, path in paths.items():
            try:
                rec = Recording(path, config)
            except (ValueError, OSError, KeyError) as exc:
                if name in plan['recordings']:
                    raise ValueError(f'Edited source is invalid: {name}: {exc}') from exc
                skipped.append({'name': name, 'reason': str(exc)})
                continue
            segments = rec.segments(plan)
            fingerprints[name] = rec.fingerprint
            if rec.outcome != 'success':
                skipped.append({'name': name, 'reason': f'outcome={rec.outcome}; success required'})
                continue
            for i, indices in enumerate(segments):
                if len(indices) < 2 or rec.grid[indices[-1]]-rec.grid[indices[0]] < 1/rec.fps-1e-9:
                    skipped.append({'name': name, 'reason': f'segment {i}: too short for an action'})
                    continue
                work.append((rec, i, indices))
        if not work:
            raise ValueError('No exportable successful fragments; previous output is unchanged')
        versions.mkdir(exist_ok=True)
        staging = versions / uuid.uuid4().hex
        staging.mkdir()
        report = dict(format='native-pipeline-h5', created_at=datetime.now(timezone.utc).isoformat(),
                      plan_digest=plan_digest(plan, config), source_selection=sorted(paths),
                      source_fingerprints=fingerprints, skipped=skipped, total_frames=0,
                      total_episodes=0, segments=[], max_frames_per_source=None)
        hashes = {}
        total = sum(len(ids) for _, _, ids in work)
        for rec, i, indices in work:
            if rec.name not in hashes:
                rec.check_source()
                hashes[rec.name] = sha256_file(rec.path)
                rec.check_source()
            stem = hashlib.sha256(rec.name.encode()).hexdigest()[:16]
            target = staging / f'episode_{stem}_segment{i:04d}.h5'
            copy_segment(rec, indices, target, hashes[rec.name])
            report['segments'].append(dict(file=target.name, source=rec.name,
                start_frame=int(indices[0]), stop_frame_exclusive=int(indices[-1])+1,
                frames=len(indices), session=rec.session, mock=rec.mock,
                source_sha256=hashes[rec.name], camera_views=rec.views))
            report['total_frames'] += len(indices)
            report['total_episodes'] += 1
            progress({'phase': 'write', 'frames': report['total_frames'], 'total_frames': total})
        for rec, _, _ in work:
            rec.check_source()
        atomic_json(staging/'clip_plan.json', plan)
        atomic_json(staging/'export_report.json', report)
        # Atomic switch; previous successful generations remain recoverable.
        link.symlink_to(staging.relative_to(output.parent), target_is_directory=True)
        os.replace(link, output)
        return report
    except BaseException:
        if staging is not None:
            (staging/'FAILED').write_text('Not a completed selection. See server error.\n')
        raise
    finally:
        link.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
