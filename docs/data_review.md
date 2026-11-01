# 单腕部相机数据筛选

## 找到的原工具

截图对应 4090 上 `/home/heinrich/roboLab/scripts/review_h5.py`，界面和服务位于 `scripts/lerobot_tools/`。它原本读取 `recording_*.h5` 中的 Kinect、RealSense、Franka state/command 四路独立数据，导出 8 维绝对目标。这与本项目的 H5、`images/wrist` 和相邻实测状态动作定义不同。筛选器兼容旧 `episode_*.h5` 及新文件名，例如 `rlt_1031_zyp_11_total31.h5`；可以搜索采集者姓名，标题末尾保留总编号。

适配版位于本仓库 `pi05_demo/curation/`，复用其界面、方案保存和版本冲突检查；用本项目数据适配器及原生 H5 分段导出替换旧读取/导出逻辑。原工具未修改。来源说明见 `THIRD_PARTY_NOTICES.md`。

## 4090 已配置入口

独立运行副本：`/home/heinrich/robolab-collecting-review`。复用师兄现有的离线 Python 环境，不安装或修改机器人采集环境：

```bash
cd /home/heinrich/robolab-collecting-review
REVIEW_PYTHON=/home/heinrich/roboLab/.venv-lerobot/bin/python \
  ./scripts/review.sh \
  --input /home/heinrich/robolab-control-system/data/raw \
  --clips outputs/review/clips.json \
  --output outputs/review/selected \
  --port 8767
```

4090 浏览器打开 `http://127.0.0.1:8767`。Mac 使用 SSH 转发：

```bash
ssh -N -L 8767:127.0.0.1:8767 4090-v6
```

如果提示端口占用，先检查已有工作台是否已启动；可复用当前页面。日志在运行副本 `outputs/review/server.log`，启动进程 PID 在 `outputs/review/server.pid`。页面每 5 秒自动刷新录制清单，新增 H5 无需重启；不会覆盖未保存的剪辑或切走当前正在看的录制。

原始 H5 现在直接位于 `/home/heinrich/robolab-control-system/data/raw/`，不用逐个进入 session 文件夹。2026-11-01 整理了 25 个 H5（19 个 success、6 个 aborted），逐文件核验 SHA-256，保留 H5 内容与 session 属性，同步迁移计数账本及保存的筛选方案路径。整理清单及账本备份位于 `/home/heinrich/robolab-control-system/reports/raw_flatten_20261101/`。新采集也直接保存到该层。

筛选完成后转换：

```bash
LEROBOT_PYTHON=/home/heinrich/roboLab/.venv-lerobot/bin/python \
  ./scripts/export.sh --input outputs/review/selected \
  --output outputs/review_checkout --checkout
```

正式训练数据必须另指定独立的 `--validation-session`，不使用 `--checkout`。筛选不会把 failure/aborted 改为 success，也不会把 mock 改成真实录制。原有 exporter 仍检查相机、配置、时序、动作范围和 session 划分。

## 裁剪与时序

- 页面播放使用原始时间戳，不把不均匀采样伪装成固定帧率。曲线显示实测关节角（rad）及夹爪指令开口（m）。
- 删除区间闭合，按原始录制内秒数匹配；删除后两侧独立成段。H5 中全部逐帧字段一起裁剪，保留原始单调时钟，导出来源、源文件 SHA-256、起止帧索引随片段保存。
- 每段至少两帧且覆盖一个采样周期。片段通过原生 episode 校验与动作对齐检查后才发布；超过 200 ms 的缺口不会跨越插值。
- 筛选 H5 数量与最终 LeRobot 帧数不同：v2 最后一帧没有下一时刻，不产生末端动作；离线均匀采样还可能改变帧数。
- 保存方案带文件大小/纳秒修改时间指纹；冲突或源文件改变会拒绝保存/导出。导出期间用方案快照，上一成功版本保留。锁文件防止两个服务并发写同一输出。
- 原图已经是采集端保存的 224×224 RGB，界面不会从不存在的全分辨率源恢复细节。

## 验证

```bash
python -m unittest discover -s tests -p test_curation.py -v
node tests/test_curation_player.js
# 可选 Chromium 集成测试（需要 Playwright 及 Chromium）
CURATION_BROWSER_TEST=1 python -m unittest discover -s tests -p test_curation_browser.py -v
```

2026-11-01 用真实录制 `collection_20261031_224444/episode_1793457901505978802_e727d13c.h5`（346 帧、单 wrist、success、非 mock）做了临时副本验证：前 16 帧中剔除 5–8 帧，得到 12 帧原生 H5 / 2 个片段，再由原有 exporter 生成 10 帧 / 2 个 LeRobot episode。官方 loader 验证了四个视频边界。测试文件已在临时目录清理，没有给用户录制保存默认裁剪决策；报告位于运行副本 `outputs/real_smoke_report.json`。
