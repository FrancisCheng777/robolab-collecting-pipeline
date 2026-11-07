# Franka 总第 153 条轨迹：独立回放包

适用于 **Ubuntu 24.04 x86_64 + PREEMPT_RT**，已有 Franka 真机控制权限的电脑。对应同一台 **Panda + Robotiq 2F-85**，不是 FR3。控制库为随包提供的 libfranka 0.9.0，不覆盖电脑现有 libfranka。

固定轨迹：`data/rlt_1105_fg_2_total153.h5`，采集者 fg，总第 153 条，个人第 2 条，396 帧，原时长约 26.34 秒。原始 H5 完整保留（包括腕部图像），未改写轨迹或元数据。操作者描述它为插花示范；录制时任务文字仍是旧的插头任务，回放只执行文件中的关节/夹爪轨迹，不使用这段任务文字驱动任何模型。

## 第一次安装

解压后进入目录（路径可含空格）：

```bash
cd franka_replay_153
# 已有 python3-venv / pip 时可跳过下面这行。
sudo apt install python3-venv python3-pip
bash setup.sh
bash run_replay.sh --inspect
```

安装需要联网下载三个 Python 包，使用目录内 `.venv`，不改动原 Python 环境。无需 GPU、CUDA、模型权重、GELLO、D405 相机或原采集项目。

`--inspect` 只核验文件，不连接机器人。`bash run_replay.sh --mock` 可用模拟桥接走完流程，不打开真实硬件。

## 真机回放

1. 退出其他机械臂控制程序，在 Franka Desk 启用 FCI、解除故障，确认仍为同一套末端工具配置。
2. 电脑机器人网卡需能访问 `172.16.0.40`。默认使用到机器人 IP 的路由自动识别网卡，自动选择两个可用 CPU 核。IP、网卡或 Robotiq 串口不同时编辑 `host.json`；物理控制增益、限位和碰撞阈值保持录制配置。
3. 在普通用户终端运行（不要用 sudo 运行回放）：

```bash
# 每次电脑重启后执行；仅设置网卡接收线程和 Robotiq USB 延迟，不连接/移动机械臂。
bash prepare_station.sh
# 默认 0.5 倍速，每次只重播一遍。
bash run_replay.sh
```

4. 程序固定选择总第 153 条并显示完整路径。摆好物品、清空到起点的路径后按 **Enter**：机械臂会移动到该记录起始位并张爪。
5. 到达起点后保持，按 **r** 开始回放，**q / Ctrl-C** 随时停止并退出。回放结束停止，不循环、不自动复位。

原速：`bash run_replay.sh --speed 1`。允许速度范围大于 0 且不超过 1。回放的是记录的绝对关节目标和夹爪开度，接触与物品位置变化会影响实际效果。

## 常见检查

- `ulimit -r` 应为 `99`；如果不是，请按已安装的 Franka 实时环境配置用户权限，重新登录后再试。回放程序不会关闭 libfranka 的实时检查。
- `cat /sys/kernel/realtime` 应为 `1`。
- Robotiq 串口默认采用录制时的 USB 序列号路径。相同 USB 转接器通常保持相同路径；若改变，可用 `ls -l /dev/serial/by-id/` 查看并在 `host.json` 填入 `gripper_device`。普通用户需有该串口的读写权限（通常是 dialout 组）。
- 网络优先级设置会在重启后失效。`prepare_station.sh` 将本机实际机器人网卡的接收线程设置为 FIFO 50，并保存原设置到 `/var/backups/franka-replay153-station-*.json`。如需恢复，在退出控制后运行 `sudo python3 scripts/prepare_station.py --rollback /var/backups/对应文件.json`。
- `FCI refused`：在 Franka Desk 激活 FCI。工具参数不匹配时程序拒绝回放，应先核对 Desk 中安装的相机、支架和夹爪配置，不要绕过检查。
- 包内动态库通过启动脚本的 `LD_LIBRARY_PATH` 加载，不需要改动系统库路径。预编译程序为 Ubuntu 20.04 x86_64 构建；已在独立目录验证，Ubuntu 24.04 目标机仍需运行安装和只读检查。必要时可以 `bash rebuild_native.sh` 在目标机按随包源码重编译。

## 文件与验证

- `manifest.json`：数据、代码和运行库 SHA-256，文件来源及兼容性说明。
- `native/bin`、`native/lib`：桥接、只读状态工具及依赖；`sources/`、`cpp/`、`vendor/`：可重编译源码；`licenses/`：第三方许可证。
- `reports/replays/`：每次回放的结果、实测关节/参考轨迹、事件及控制日志，不产生训练数据。
- `VALIDATION.json`：在源主机解压到独立路径后进行的检查结果。真机没有自动执行，目标电脑的实时性能和实体回放需操作者现场验证。

请通过入口脚本启动；不要直接从原项目复制命令。源 H5 的任务文本虽仍为插头任务，本包不会把它混入插头训练集。
