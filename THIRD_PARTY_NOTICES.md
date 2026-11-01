# Third-party code and provenance

This snapshot derives from FrancisCheng777/robolab-control-system and the earlier RoboLab collection work. Existing attribution and source comments are retained. Publication does not relicense upstream material.

- `vendor/gello/`: GELLO; MIT, copyright Philipp Wu. See `vendor/GELLO_LICENSE`.
- `vendor/robotiq_grippers/`: Robotiq SDK, BSD-3-Clause. See its `LICENSE`; embedded nanomodbus has its own license.
- `vendor/cppdeps/ruckig-0.15.3/`: Ruckig, MIT; see `LICENSE` and its `third_party/` license files.
- `vendor/cppdeps/json-3.11.3/`: nlohmann/json, MIT, copyright Niels Lohmann. License attribution is embedded in the header; see the adjacent `LICENSE.MIT`.
- `configs/tools/robotiq_2f85_no_camera/sources/`: Robotiq model sources; see `LICENSE.robotiq-ros` and source provenance metadata.
- `vendor/gello_publish_zenoh.py`, `vendor/legacy_cameras.py`: RoboLab adapters retained from the source snapshot; upstream origin/history is documented in `docs/baseline/`.

libfranka, RealSense, LeRobot, PyTorch and other separately installed dependencies retain their own licenses. No new blanket license is assigned by this publication.

- `pi05_demo/curation/`: interface, review service, and edit-plan helpers adapted from the lab's `/home/heinrich/roboLab/scripts/lerobot_tools/` working copy on the 4090, retrieved 2026-11-01. Those source files were untracked in the original working tree (repository HEAD `bc0bed9e9cd2916ad0c6f67697ef931dd80773c6`); the HEAD is not a commit containing the editor. The adapter replaces legacy dual-camera ingestion and absolute-action export with native collection H5 ingestion and fragment export. Original lab authorship is retained; this adaptation does not assign a new license.
