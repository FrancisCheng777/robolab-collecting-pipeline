# Franka 已采集轨迹回放

在 4090 终端运行：

```bash
bash ~/robolab-control-system/scripts/replay_session.sh
```

1. 先在采集或模型推理窗口按 `q` 正常退出。
2. 输入采集时显示的“总第 N 条”中的 N（例如 `153`），或完整文件名。数字是稳定的采集总编号，不是列表行号；无总编号的旧文件只能按文件名选择。默认读取 `~/robolab-control-system/data/raw/`，只显示完整、真实、成功保存的 schema 2 示范。
3. 摆好插头、插排并清空到起点的运动路径，再按 Enter。机械臂会先移动到这条记录的起始关节位置并张爪。
4. 到位后程序保持，按 `r` 开始回放一遍；`q` 或 Ctrl-C 随时停止并退出。结束后停止，不自动再回放或回初始位。

默认半速，可使用 `--speed 1` 原速回放（支持大于 0、不超过 1）。

```bash
# 只列文件，不打开硬件
bash ~/robolab-control-system/scripts/replay_session.sh --list
# 只检查最新示范，不打开硬件
bash ~/robolab-control-system/scripts/replay_session.sh --latest --inspect
# 选择最新示范，仍需 Enter 确认移动到起点、r 确认开始
bash ~/robolab-control-system/scripts/replay_session.sh --latest
# 指定示范
bash ~/robolab-control-system/scripts/replay_session.sh --episode ~/robolab-control-system/data/raw/文件名.h5 --speed 0.5
```

回放的是采集时记录的绝对关节目标 `q_target` 和夹爪命令宽度，按原时间戳插值并缩放时间，不经过 VLA、AC 或 RTC。控制器、关节范围、碰撞保护及反馈新鲜度检查沿用采集配置；起点取实测 `q[0]`。支持起始夹爪已张开的记录（至少 80 mm），控制参数必须与当前采集配置一致。接触、物品位置和夹持变化会影响实际运动，因此重播同一目标序列不代表一定重现原来的插入结果。

报告保存到 `~/robolab-control-system/reports/replays/replay_*/`：`result.json`（完成/停止/错误及原文件哈希）、`events.json`、`trace.json`、桥接和故障日志。原 H5 不修改，不产生新的训练示范。

若提示网卡调度未恢复，在采集和回放均已退出时运行：

```bash
sudo /usr/bin/python3 ~/robolab-control-system/scripts/fix_fci_network_priority.py --apply
```

实现验证包含单元测试、真实示范只读检查和模拟桥接回放；真实机械臂回放需要操作者在场按上述流程启动。
