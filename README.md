# robolab-collecting-pipeline

Franka Panda + Robotiq 2F-85 + GELLO 的遥操作示教采集代码，当前生产配置使用 **一台 RealSense D405 腕部相机**。包含 C++ 控制桥接、Python 采集状态机、HDF5 记录、质量检查、LeRobot 导出和真机轨迹回放。

这是 2026-11-01 从实际运行的 `robolab-control-system` 工作目录整理的独立源码快照，包括尚未提交到原仓库的采集修复。来源为 [robolab-control-system](https://github.com/FrancisCheng777/robolab-control-system)。**不包含采集数据、模型权重、训练器、运行环境或编译产物。**

## 当前功能

- `responsive_recording`：100 Hz 控制循环、15 Hz 异步记录；C++ libfranka 实时控制桥接。
- 单 D405：原始数据只有 `images/wrist`，不会复制画面伪造其他视角。
- HDF5 保存实测关节、目标指令、夹爪实测/指令、图像、时间戳及设备反馈元数据。
- 有界存储队列；存储失败时停止并标记未完成片段，不静默丢帧。缓存 HDF5 句柄降低写入开销。
- 启动检查陈旧 socket、设备占用、实时调度、Desk 工具参数等。
- `r/e/s/d/q` 连续采集；已保存片段立即落盘。
- LeRobot 导出、按 session 划分验证集、仅用 train split 计算统计、官方 loader 回读检查。
- 原始 `q_target` 按时间插值回放，夹爪指令零阶保持。回放完成不等于任务成功。

## 环境与构建

真机入口面向 Linux。推荐分别创建采集和离线导出环境；以下依赖文件记录当前机器观察到的版本，不是所有操作系统通用的锁文件。

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-collection.txt
```

C++ 需要 CMake、C++17 编译器及与机器人系统兼容的 libfranka。当前 Panda 使用 libfranka 0.9.x。Robotiq SDK、GELLO 代码和 Ruckig/JSON 源码副本位于 `vendor/`；默认以下命令通过 CMake 获取指定版本的 Ruckig/JSON。

```bash
cmake -S cpp/bridge -B build -DPI05_WITH_FRANKA=ON -DPI05_FETCH_DEPS=ON
cmake --build build -j4
(cd build && ctest --output-on-failure)
```

没有机器人依赖时可构建 mock 后端：

```bash
cmake -S cpp/bridge -B build -DPI05_WITH_FRANKA=OFF -DPI05_FETCH_DEPS=ON
cmake --build build -j4
.venv/bin/python scripts/validate.py
```

验证入口只运行单元测试、C++ 测试与 mock 采集。构建真实后端后也不会在测试中连接真机。

## 配置自己的工作站

实际连续采集配置位于 `configs/latency/responsive_recording/{bridge,collection}.trial.json`。当前值来自原工作站：机器人 IP、D405 序列号、USB 设备路径、GELLO 关节映射、默认姿态、工具负载及 CPU 绑定均需对应实际硬件。

- 控制器和碰撞参数原样保留。当前生产 bridge 的平移碰撞阈值为 100 N；它不是期望接触力，也不是其他装置的通用设置。
- CPU/实时网络检查见 `scripts/try_latency.sh`、`scripts/fix_fci_network_priority.py`、`pi05_demo/teleop_runtime.py`。原工作站使用 CPU 12–19；其他拓扑需要适配。
- Desk 工具核对依赖 libfranka 的 `echo_robot_state` 示例程序。加入 PATH 或设置：

```bash
export FRANKA_ECHO=/path/to/libfranka/build/examples/echo_robot_state
```

- 单 D405 不需要 Kinect/libfreenect2。旧双相机兼容路径仍保留；需要时可设置 `FREENECT2_LIB_DIR`。
- 对当前装配的历史验证及参数来源，见 `configs/tools/`。这些记录不代替新装置的标定。

先只检查配置：

```bash
./scripts/collect_session.sh --inspect
```

## 连续采集

```bash
./scripts/collect_session.sh
```

| 按键 | 行为 |
|---|---|
| 启动后的 Enter | 检查设备，自动回默认位置并开爪；进入待机 |
| `r` | 从待机开始跟随 GELLO 并录制 |
| `e` | 结束录制、停稳、回默认位置并开爪；回位不写入片段 |
| `s` | 回位后将待确认片段保存为 success |
| `d` | 回位后永久删除当前片段，不保留 discarded 备份 |
| `q` | 退出；已保存片段保留，未确认片段保留为 aborted |

每段处理完后按 `r` 继续。`scripts/collect_one.sh` 是同一连续流程的兼容入口。

文件写到 `data/raw/collection_<时间>/episode_*.h5`，不会直接平铺在 `data/raw/`。检查及日志写到 `reports/collection/<session>/`。成功标签来自操作者；应同时检查图像、时间完整性和任务结果。

纯遥操作：`./scripts/try_latency.sh responsive --execute --teleop-only`，保留旧的遥操作按键，不启用相机或录制。

## LeRobot 导出

创建独立环境，并安装与 LeRobot 兼容的 PyTorch/torchvision（当前验证环境为 torch 2.7.1+cpu / torchvision 0.22.1+cpu）：

```bash
python3 -m venv .venv-lerobot
# 先按目标平台安装 torch / torchvision，再安装：
.venv-lerobot/bin/pip install -r requirements-export.txt
# 若使用其他环境：export LEROBOT_PYTHON=/path/to/python
```

单 session 试导出：

```bash
./scripts/export.sh --input data/raw/collection_<时间> --output outputs/checkout_v1 --checkout
```

`--checkout` 只做链路检查，不是正式训练发布。正式导出需要至少一个独立 session 作为验证集。当前 exporter 只读取输入目录第一层的 `*.h5`；先将选中的 session 文件汇集到一个独立目录（可使用符号链接），再执行：

```bash
./scripts/export.sh --input data/selected --output outputs/dataset_v1 \
  --validation-session collection_<验证集时间>
```

只导出成功片段；拒绝混合物理配置和混合相机数量。输出包含 train/validation 数据、manifest、norm_stats.json 和 action_codec.json。已有输出目录不会覆盖。

**动作契约必须一致：**

- 原始桥接协议仍是 `panda_delta_q0.03_robotiq_width0.085_v1`。
- 数据集导出使用 `panda_delta_q0.05_robotiq_width0.085_v2`：15 Hz 网格上相邻实测关节增量除以 0.05，夹爪按绝对开度编码。
- 原始 schema-2 的 `q_target` 是绝对目标，不能直接当作归一化模型动作。
- wrist 图像映射到策略的 `base_0_rgb`，其他槽位屏蔽；真实 LeRobot 图像字段为 `observation.images.wrist`。
- 本仓库不含 π0.5-base/RLT 训练器。旧训练/部署端的 v1 契约检查仍需显式迁移到 v2；训练和推理必须使用一致的统计、编码与相机映射。此处不声称完整模型训练接入已经完成。

## 回放

```bash
# 只读检查文件
./scripts/replay_episode.sh --episode data/raw/<session>/<episode>.h5
# mock 回放，不连接机械臂
./scripts/replay_episode.sh --episode data/raw/<session>/<episode>.h5 --mock
# 真机回放，Enter 确认后执行；q / Ctrl-C 中止
./scripts/replay_episode.sh --episode data/raw/<session>/<episode>.h5 --execute
```

默认原速播放一次，可通过 `--speed 0.5` 降速。要求完整、真实、成功的 schema-2 示教且标定匹配。先回到录制起始姿态、开爪，再播放录制目标。15 Hz 指令插值到控制循环，不包含未记录的原始 100 Hz 指令，也没有视觉纠偏。

## 源码目录与来源

- `pi05_demo/`：采集、状态机、存储、检查、导出、回放。
- `cpp/bridge/`：控制与夹爪桥接源码。
- `scripts/`：运行、诊断、构建后的验证入口。
- `configs/`：工作站配置及工具装配资料。
- `tests/`：单元和 mock 集成测试。
- `vendor/`：随代码保存的依赖及许可证。
- `reports/robolab_restore_20261030/*.trial.json`：旧入口仍引用的两个配置文件，因此保留；其他运行报告不发布。
- `docs/`：历史设计/验证记录，以本 README 的当前流程为准。`scripts/alignment_rviz.py` 等可选历史工具另需 ROS 和对应模型资源。

第三方代码沿用各自许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本次公开发布没有为原项目代码新增或重授许可证。
