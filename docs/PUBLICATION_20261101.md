# Public source snapshot — 2026-11-01

Source: the working tree of `FrancisCheng777/robolab-control-system`, based on commit `1826570932ba6e1ef00f55da8d97c06c65c177a2` plus the current uncommitted collection changes. This is a new repository snapshot, not a rewrite of the running controller repository.

All 427 source/configuration/test/vendor files in the selected source directories were included. `cpp/`, `configs/`, `pi05_demo/`, and `tests/` were preserved byte-for-byte. Publication adjustments affect six scripts:

- `collect.sh`: optional Kinect library location from the environment.
- `export.sh`: configurable LeRobot Python interpreter.
- `check_desk_tool.py`: configurable libfranka echo executable and output-directory creation.
- `verify_stationary_communication.py`: repository-relative root and report-directory creation.
- `smoke.py`: create output parent directories in a fresh checkout.
- `validate.py`: replace unavailable historical training/runtime checks with standalone unit/C++/mock checks and optional LeRobot export. Run CTest from the build directory for compatibility with older CMake.

README, package description/name, dependency version records, ignore rules and third-party notices were updated. The nlohmann/json v3.11.3 license text was added beside the bundled header. No controller parameters were retuned.

## Validation

In an isolated Linux staging directory, using the existing collection/export Python environments:

- Python: 137 tests, OK; 1 skipped.
- C++: `bridge_core_test` and `fault_history_test`, both passed. These reused the existing built artifacts corresponding to the unchanged C++ source; this publication did not perform a clean-room build.
- Mock collection: train and validation sessions, 12 frames each, successful HDF5 inspection.
- LeRobot export: both mock splits reloaded with the official loader; 12 frames and 1 episode per split.
- Python syntax, modified shell syntax and collection `--inspect`: passed.
- Tracked-file scan: no credential-pattern hits, private keys, HDF5 episodes, weights, environments or build products.

No real robot motion was requested for publication. A clean-machine install and full π0.5 training/deployment integration were not performed. Historical documents under `docs/` describe earlier revisions; the root README is the current usage guide.
