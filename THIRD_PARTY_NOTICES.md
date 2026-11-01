# Third-party code and provenance

This snapshot derives from FrancisCheng777/robolab-control-system and the earlier RoboLab collection work. Existing attribution and source comments are retained. Publication does not relicense upstream material.

- `vendor/gello/`: GELLO; MIT, copyright Philipp Wu. See `vendor/GELLO_LICENSE`.
- `vendor/robotiq_grippers/`: Robotiq SDK, BSD-3-Clause. See its `LICENSE`; embedded nanomodbus has its own license.
- `vendor/cppdeps/ruckig-0.15.3/`: Ruckig, MIT; see `LICENSE` and its `third_party/` license files.
- `vendor/cppdeps/json-3.11.3/`: nlohmann/json, MIT, copyright Niels Lohmann. License attribution is embedded in the header; see the adjacent `LICENSE.MIT`.
- `configs/tools/robotiq_2f85_no_camera/sources/`: Robotiq model sources; see `LICENSE.robotiq-ros` and source provenance metadata.
- `vendor/gello_publish_zenoh.py`, `vendor/legacy_cameras.py`: RoboLab adapters retained from the source snapshot; upstream origin/history is documented in `docs/baseline/`.

libfranka, RealSense, LeRobot, PyTorch and other separately installed dependencies retain their own licenses. No new blanket license is assigned by this publication.
