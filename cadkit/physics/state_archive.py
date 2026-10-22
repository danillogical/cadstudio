"""Native MuJoCo integration-state archive (M4b).

The archive is the runtime's own state vector, not a hand-picked subset:

* the mask is the installed runtime's ``mjSTATE_INTEGRATION`` (all bits the runtime exposes
  for integration, including activation, warmstart, controls, applied forces, mocap, user and
  plugin state where present);
* the layout is derived from ``mj_stateSize`` per bit, so component offsets are recorded
  rather than assumed and a zero-size component is recorded as present with size 0;
* rows are post-state: ``state[0]`` is the post-reset state and ``state[k]`` is the state
  after exactly ``k`` ``mj_step`` calls. ``inputs[k]`` (ctrl/applied/mocap) is the input
  applied before step ``k`` and produces row ``k``.

Nothing here imports a project, reads CAD, or writes physical state by hand.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import zipfile
from pathlib import Path

import numpy as np

STATE_FORMAT = "m4b-1"

#: Canonical component order. Offsets are cumulative in this order and must sum to the
#: integration-state size, which is what makes the layout self-checking.
STATE_BITS = (
    "mjSTATE_TIME", "mjSTATE_QPOS", "mjSTATE_QVEL", "mjSTATE_ACT", "mjSTATE_WARMSTART",
    "mjSTATE_CTRL", "mjSTATE_QFRC_APPLIED", "mjSTATE_XFRC_APPLIED", "mjSTATE_EQ_ACTIVE",
    "mjSTATE_MOCAP_POS", "mjSTATE_MOCAP_QUAT", "mjSTATE_USERDATA", "mjSTATE_PLUGIN",
)

#: Default budgets. Overridable through scenario budgets; enforced before large arrays are
#: created and again while rows are appended.
DEFAULT_MAX_STATE_BYTES = 256 * 1024 * 1024
MAX_ARCHIVE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 64
MAX_ARCHIVE_ROWS = 2_000_000
MAX_REPLAY_WALL_S = 600.0


#: Pinned same-runtime replay tolerances. Same-platform reproduction within tolerance is
#: claimed; bit equality across platforms is not.
REPLAY_TOLERANCES = {
    "state_atol": 1e-9, "state_rtol": 1e-9,
    "time_atol": 1e-12, "control_atol": 1e-12,
    "metric_atol": 1e-9, "metric_rtol": 1e-9,
    "check_value_atol": 1e-9,
}


class ArchiveError(ValueError):
    """The archive or its metadata is missing, malformed, oversized or tampered with."""


def integration_mask(mujoco) -> int:
    return int(mujoco.mjtState.mjSTATE_INTEGRATION)


def state_layout(mujoco, model) -> dict:
    """Mask, size and per-component offsets derived only from the installed runtime."""
    mask = integration_mask(mujoco)
    components = []
    offset = 0
    for name in STATE_BITS:
        bit = getattr(mujoco.mjtState, name, None)
        if bit is None:
            components.append({"name": name, "mask": None, "offset": None, "size": 0,
                               "present": False})
            continue
        size = int(mujoco.mj_stateSize(model, int(bit)))
        components.append({"name": name, "mask": int(bit), "offset": offset,
                           "size": size, "present": size > 0})
        offset += size
    total = int(mujoco.mj_stateSize(model, mask))
    if offset != total:
        raise ArchiveError(
            f"state component sizes sum to {offset} but mj_stateSize(INTEGRATION) is {total}; "
            f"the runtime layout is not understood")
    return {
        "state_format": STATE_FORMAT,
        "mask": mask,
        "size": total,
        "components": components,
        "nq": int(model.nq), "nv": int(model.nv), "na": int(model.na),
        "nu": int(model.nu), "nbody": int(model.nbody), "nmocap": int(model.nmocap),
        "neq": int(model.neq), "nuserdata": int(model.nuserdata),
    }


def get_native_state(mujoco, model, data) -> np.ndarray:
    layout = state_layout(mujoco, model)
    state = np.zeros(layout["size"], dtype=np.float64)
    mujoco.mj_getState(model, data, state, layout["mask"])
    return state


def set_native_state(mujoco, model, data, state) -> None:
    layout = state_layout(mujoco, model)
    arr = np.ascontiguousarray(state, dtype=np.float64)
    if arr.shape != (layout["size"],):
        raise ArchiveError(
            f"state shape {arr.shape} does not match the runtime layout {layout['size']}")
    if not np.all(np.isfinite(arr)):
        raise ArchiveError("state contains non-finite values")
    mujoco.mj_setState(model, data, arr, layout["mask"])


def state_bytes_estimate(layout: dict, rows: int, *, extra_per_row: int = 0) -> int:
    return int(rows) * (8 * int(layout["size"]) + int(extra_per_row))


def state_sha256(state: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(state, dtype=np.float64).tobytes()).hexdigest()


def row_sha256(integration_state: np.ndarray, row: int) -> str:
    return state_sha256(np.asarray(integration_state[row]))


def write_archive(path: Path, arrays: dict[str, np.ndarray]) -> None:
    """Write a compressed NumPy archive; every array must be numeric, never object."""
    for name, array in arrays.items():
        if getattr(array.dtype, "hasobject", False):
            raise ArchiveError(f"refusing to write object array {name!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as fh:
        np.savez_compressed(fh, **arrays)


#: Members a states archive may contain. Anything else is rejected.
_STATE_MEMBERS = {
    "time", "qpos", "qvel", "act", "ctrl", "qacc_warmstart", "qfrc_applied",
    "mocap_pos", "mocap_quat", "phase_code", "phase_index", "step_index",
    "integration_state", "integration_mask", "integration_size",
    "transition_ctrl", "transition_qfrc_applied", "transition_xfrc_applied",
    "transition_mocap_pos", "transition_mocap_quat",
    "phase_names", "joint_names", "body_names", "actuator_names", "timestep_s",
}


def required_members(layout: dict) -> set[str]:
    """Members that must exist for this model layout (zero-size components are omitted)."""
    components = {c["name"]: int(c.get("size", 0)) for c in layout.get("components", [])}
    required = set(_STATE_MEMBERS)
    if not components.get("mjSTATE_XFRC_APPLIED"):
        required.discard("transition_xfrc_applied")
    if not components.get("mjSTATE_MOCAP_POS"):
        required.discard("transition_mocap_pos")
    if not components.get("mjSTATE_MOCAP_QUAT"):
        required.discard("transition_mocap_quat")
    return required


def inspect_npz(path: Path, *, expected_members: set[str] | None = None,
                max_bytes: int = MAX_ARCHIVE_BYTES,
                max_members: int = MAX_ARCHIVE_MEMBERS) -> dict[str, zipfile.ZipInfo]:
    """Inspect a ZIP central directory before any decompression."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"cannot open archive {path}: {exc}") from exc
    _validate_member_infos(infos, expected_members=expected_members,
                           max_bytes=max_bytes, max_members=max_members)
    return {info.filename: info for info in infos}


def _validate_member_infos(infos, *, expected_members, max_bytes, max_members) -> None:
    if len(infos) > max_members:
        raise ArchiveError(f"archive has {len(infos)} members, above {max_members}")
    names = [info.filename for info in infos]
    if len(set(names)) != len(names):
        raise ArchiveError("archive has duplicate member names")
    total = 0
    for info in infos:
        name = info.filename
        if name.endswith("/"):
            raise ArchiveError(f"archive member {name!r} is a directory")
        if "/" in name or "\\" in name or name.startswith(".") or ".." in name:
            raise ArchiveError(f"archive member {name!r} has an unsafe path")
        if info.flag_bits & 0x1:
            raise ArchiveError(f"archive member {name!r} is encrypted")
        base = name[:-4] if name.endswith(".npy") else name
        allowed = expected_members if expected_members is not None else _STATE_MEMBERS
        if base not in allowed:
            raise ArchiveError(f"archive member {name!r} is not expected")
        total += int(info.file_size)
    if total > max_bytes:
        raise ArchiveError(
            f"archive declares {total} uncompressed bytes, above the {max_bytes} budget")


def _parse_npy_header(header: bytes) -> tuple[tuple[int, ...], str, int]:
    """Parse an NPY header with no allocation; only shape and descr are trusted."""
    import ast
    import struct

    if len(header) < 10 or header[:6] != b"\x93NUMPY":
        raise ArchiveError("archive member is not a valid NPY file")
    major = header[6]
    if major == 1:
        header_len = struct.unpack("<H", header[8:10])[0]
        total = 10 + header_len
        body = header[10:total]
    elif major in (2, 3):
        if len(header) < 12:
            raise ArchiveError("archive member has a truncated NPY header")
        header_len = struct.unpack("<I", header[8:12])[0]
        total = 12 + header_len
        body = header[12:total]
    else:
        raise ArchiveError(f"unsupported NPY version {major}")
    try:
        parsed = ast.literal_eval(body.decode("latin1").strip())
    except (ValueError, SyntaxError, UnicodeDecodeError) as exc:
        raise ArchiveError(f"malformed NPY header: {exc}") from exc
    if not isinstance(parsed, dict) or "descr" not in parsed or "shape" not in parsed:
        raise ArchiveError("NPY header lacks descr or shape")
    descr = parsed["descr"]
    if not isinstance(descr, str) or descr[:1] in ("O", "V") or "<" not in descr and "|" not in descr:
        raise ArchiveError(f"unsupported NPY dtype {descr!r}")
    kind = descr[1] if len(descr) >= 2 and descr[0] in "<>=|" else descr[0]
    if kind not in "fiufSU":
        raise ArchiveError(f"unsupported NPY dtype kind {kind!r}")
    shape = parsed["shape"]
    if not isinstance(shape, tuple):
        raise ArchiveError("NPY shape is not a tuple")
    for value in shape:
        if not isinstance(value, int) or value < 0:
            raise ArchiveError(f"NPY shape has an invalid dimension {value!r}")
    if len(shape) > 3:
        raise ArchiveError(f"NPY member has {len(shape)} dimensions, above 3")
    return tuple(shape), descr, total


def _itemsize(descr: str) -> int:
    import numpy as np

    try:
        return int(np.dtype(descr).itemsize)
    except TypeError as exc:
        raise ArchiveError(f"unsupported NPY dtype {descr!r}") from exc


def _validate_npy_members(raw: bytes, infos, *, expected_members, max_bytes, max_rows):
    """Parse every NPY header before np.load and reject oversized/mismatched shapes."""
    required = expected_members if expected_members is not None else _STATE_MEMBERS
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos_by_name = {info.filename: info for info in infos}
        shapes: dict[str, tuple[int, ...]] = {}
        total_payload = 0
        for name, info in infos_by_name.items():
            base = name[:-4] if name.endswith(".npy") else name
            if base not in required:
                raise ArchiveError(f"archive member {name!r} is not expected")
            with archive.open(info) as fh:
                head = fh.read(4096)
            shape, descr, header_total = _parse_npy_header(head)
            itemsize = _itemsize(descr)
            if itemsize <= 0 or itemsize > 1024:
                raise ArchiveError(f"member {name!r} has an implausible itemsize {itemsize}")
            count = 1
            for value in shape:
                count *= int(value)
            payload = count * itemsize
            if int(info.file_size) != header_total + payload:
                raise ArchiveError(
                    f"member {name!r} declares {info.file_size} bytes but header {header_total} "
                    f"plus shape {shape} with {descr} needs {header_total + payload}")
            total_payload += payload
            if total_payload > max_bytes:
                raise ArchiveError(
                    f"archive payload exceeds the {max_bytes}-byte budget before load")
            shapes[base] = shape
        missing = set(required) - set(shapes)
        if missing:
            raise ArchiveError(f"archive is missing required members {sorted(missing)}")
        if "time" not in required:
            return None, shapes
        if "time" not in shapes:
            raise ArchiveError("archive has no time member")
        if len(shapes["time"]) != 1:
            raise ArchiveError("time member must be one-dimensional")
        rows = int(shapes["time"][0])
        if rows > max_rows:
            raise ArchiveError(f"archive has {rows} rows, above the {max_rows} budget")
        per_row = {
            "time", "qpos", "qvel", "act", "ctrl", "qacc_warmstart", "qfrc_applied",
            "mocap_pos", "mocap_quat", "phase_code", "phase_index", "step_index",
            "integration_state", "transition_ctrl", "transition_qfrc_applied",
            "transition_xfrc_applied", "transition_mocap_pos", "transition_mocap_quat",
        }
        for base, shape in shapes.items():
            if base in per_row and shape and shape[0] != rows:
                raise ArchiveError(
                    f"member {base!r} first dimension {shape[0]} differs from {rows} rows")
        return rows, shapes


def read_state_archive(path, *, expected_members: set[str] | None = None,
                       max_bytes: int = MAX_ARCHIVE_BYTES,
                       max_rows: int = MAX_ARCHIVE_ROWS,
                       allow_nonfinite: bool = False) -> dict[str, np.ndarray]:
    """Load a states archive from a path or already-read bytes.

    The archive bytes are read once, every NPY header is parsed and validated before
    ``np.load`` (so a forged shape cannot request a huge allocation), and no pickle is used.
    """
    if isinstance(path, (bytes, bytearray, memoryview)):
        raw = bytes(path)
    else:
        from .evidence import bounded_regular_bytes
        raw = bounded_regular_bytes(Path(path).parent, Path(path).name, max_bytes=max_bytes)
    return read_state_archive_bytes(raw, expected_members=expected_members,
                                    max_bytes=max_bytes, max_rows=max_rows,
                                    allow_nonfinite=allow_nonfinite)


def read_state_archive_bytes(raw: bytes, *, expected_members: set[str] | None = None,
                             max_bytes: int = MAX_ARCHIVE_BYTES,
                             max_rows: int = MAX_ARCHIVE_ROWS,
                             allow_nonfinite: bool = False) -> dict[str, np.ndarray]:
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError) as exc:
        raise ArchiveError(f"cannot open archive: {exc}") from exc
    _validate_member_infos(infos, expected_members=expected_members,
                           max_bytes=max_bytes, max_members=MAX_ARCHIVE_MEMBERS)
    rows, shapes = _validate_npy_members(raw, infos, expected_members=expected_members,
                                         max_bytes=max_bytes, max_rows=max_rows)
    try:
        with np.load(io.BytesIO(raw), allow_pickle=False) as data:
            arrays = {name: np.array(data[name], copy=True) for name in data.files}
    except (OSError, ValueError, EOFError, zipfile.BadZipFile) as exc:
        raise ArchiveError(f"cannot load archive: {exc}") from exc
    string_members = {"phase_names", "joint_names", "body_names", "actuator_names"}
    for name, array in arrays.items():
        if getattr(array.dtype, "hasobject", False):
            raise ArchiveError(f"archive member {name!r} is an object array")
        if name in string_members:
            if array.dtype.kind not in "US":
                raise ArchiveError(
                    f"archive member {name!r} must be a string array, got {array.dtype}")
            continue
        if array.dtype.kind not in "fiu":
            raise ArchiveError(f"archive member {name!r} has unsupported dtype {array.dtype}")
        if array.shape != shapes.get(name):
            raise ArchiveError(
                f"archive member {name!r} loaded shape {array.shape} != header {shapes.get(name)}")
        if (not allow_nonfinite and array.size
                and not np.all(np.isfinite(array.astype(np.float64, copy=False)))):
            raise ArchiveError(f"archive member {name!r} contains non-finite values")
    return arrays


def validate_layout(layout: dict, model, mujoco) -> None:
    """The recorded layout must match the runtime exactly, including zero-size components."""
    expected = state_layout(mujoco, model)
    if int(layout.get("mask", -1)) != expected["mask"]:
        raise ArchiveError(
            f"recorded state mask {layout.get('mask')} != runtime {expected['mask']}")
    if int(layout.get("size", -1)) != expected["size"]:
        raise ArchiveError(
            f"recorded state size {layout.get('size')} != runtime {expected['size']}")
    for key, expected_key in (("nq", "nq"), ("nv", "nv"), ("na", "na"), ("nu", "nu"),
                              ("nbody", "nbody"), ("nmocap", "nmocap")):
        if key in layout and int(layout[key]) != expected[key]:
            raise ArchiveError(f"recorded layout {key}={layout[key]} != runtime {expected[key]}")
    recorded = {c["name"]: c for c in layout.get("components", [])}
    for component in expected["components"]:
        got = recorded.get(component["name"])
        if got is None:
            raise ArchiveError(f"recorded layout is missing component {component['name']}")
        for key in ("mask", "offset", "size"):
            if got.get(key) != component[key]:
                raise ArchiveError(
                    f"recorded component {component['name']} {key}={got.get(key)} != "
                    f"runtime {component[key]}")


def write_state_meta(path: Path, *, layout: dict, summary: dict, checkpoints: dict,
                     phase_names=None, control_names=None) -> None:
    """Strict JSON metadata: mask/layout, row semantics and phase/control mapping."""
    payload = {
        "state_format": STATE_FORMAT,
        "layout": layout,
        "row_semantics": {
            "state[0]": "post-reset state, no mj_step has run",
            "state[k]": "state after exactly k mj_step calls",
            "inputs[k]": "ctrl/applied/mocap applied before step k, producing row k",
            "phase_index": "zero-based index into phase_names; reset is 0",
            "phase_code": "phase_index + 1 (one-based convenience column)",
        },
        "phase_names": (list(phase_names) if phase_names is not None
                        else [item["name"] for item in summary["plan"]["phases"]]),
        "control_names": (list(control_names) if control_names is not None
                          else summary.get("control_names", [])),
        "checkpoints": checkpoints,
        "tolerances": summary.get("replay_tolerances", {}),
    }
    path.write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_state_meta(path: Path) -> dict:
    from .evidence import EvidenceError, bounded_regular_bytes

    path = Path(path)
    try:
        raw = bounded_regular_bytes(path.parent, path.name, max_bytes=MAX_ARCHIVE_BYTES)
    except (EvidenceError, OSError) as exc:
        raise ArchiveError(f"cannot read state metadata {path}: {exc}") from exc
    return load_state_meta_bytes(raw)


def load_state_meta_bytes(raw: bytes) -> dict:
    from .scenario import ScenarioError, _parse_json_text

    try:
        payload = _parse_json_text(raw.decode("utf-8"), "state_meta.json")
    except (ScenarioError, UnicodeDecodeError) as exc:
        raise ArchiveError(f"cannot parse state metadata: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("state_format") != STATE_FORMAT:
        raise ArchiveError("unsupported or malformed state metadata")
    layout = payload.get("layout")
    if not isinstance(layout, dict) or "components" not in layout:
        raise ArchiveError("state metadata has no usable layout")
    for component in layout["components"]:
        if not all(math.isfinite(float(component.get(key, 0)))
                   for key in ("offset", "size") if component.get(key) is not None):
            raise ArchiveError("state metadata component offsets are not finite")
    return payload

