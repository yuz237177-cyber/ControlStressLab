# 实验协议

## 对比单位与范围

一次完整闭环运行是记录单位。两种控制器在同一对象、初始条件、目标信号、执行限制与随机场景下配对。
时间序列内的每个采样点不是独立重复。无随机因素时重复相同运行不会增加独立证据。

内置实验是演示协议，不是控制器普遍优劣结论。默认增益固定，未进行自动优化。

## 场景

| 场景 | 条件 | 恢复观察起点 |
|---|---|---:|
| nominal | t=0.5 s 参考从 0 到 60 rad/s | 0.5 s |
| load_step | 正常参考；t=4 s 增加 0.15 N m 负载 | 4 s |
| measurement_noise | 正常参考；每样本标准差 1 rad/s 的高斯噪声 | 0.5 s |
| measurement_delay | 正常参考；测量纯延迟 0.1 s | 0.5 s |
| saturation_release | t=0.5 s 参考升为 140，t=4 s 回落至 60 rad/s | 4 s |

全部值是合成测试假设。噪声场景与负载场景互相独立，不默认叠加。
持续时间 12 s，默认周期 0.01 s。评价区间为 [0.5,12) s。

## 随机性与公平性

噪声在调用控制器前按场景预生成，两控制器使用相同序列。
控制器内部计算不会消耗场景随机数。记录种子、采样周期与 Python 版本。
后续做随机场景比较时，对完整运行指标做成对分析，而非把采样点当作独立样本。
种子数量不是自动满足统计效力的样本量保证。
当前五种场景中四种是确定性的；多种子只改变 measurement_noise，重复确定性场景不会增加独立证据。

后续调参时建立开发场景和最终留出场景，预先说明目标函数和预算。
加入实物后按实验日/设备状态分组，组内交错或随机运行控制器，并恢复可比初始状态，记录温升和电源变化。

## 指标定义

- RMSE：评价区间内以真实输出误差、左端点矩形积分计算的均方根误差，单位 rad/s。
- IAE：相同区间绝对误差积分，单位 rad。
- 最大绝对误差：评价区间内控制采样点的最大误差，单位 rad/s。
- 输入总变差：评价区间内相邻实际电压之差的绝对值之和，单位 V；不是能耗。
- 分段 IAE/RMSE：在同一评价区间内按 recovery_start_s 锚点拆为 pre/post 两段，IAE 单位仍为 rad。
  空段指标为 null、段时长为0；有两段时两段IAE之和等于全窗口IAE。
- 饱和比例：请求电压与实际电压不同的时间占评价区间时间比例。
- 恢复时间：从指定事件起点到最后一段持续在绝对误差带内的区间起点。
  误差带默认 ±1.2 rad/s，该区间须持续至少 0.5 s 且直到观察结束仍不出带。
  它是有限观察窗口的恢复指标，非稳定性证明。最终端点用于检查恢复，不参与误差积分。

最终参考值在恢复窗口内必须恒定，否则配置拒绝执行。
未恢复记为 null，并给出 not_recovered_in_observation_window。
提前失败的完整时长指标全部记为 null，避免短轨迹被误判为低累计误差。
完成、未恢复、越界和数值失败分别解释，不合并为总分。

v0.1.1 补充：恢复时间依据仿真真实状态，实测需定义测量/估计来源、噪声处理及判据，不能直接照搬。
输入总变差在噪声下依赖采样周期与带宽；跨周期比较须统一物理噪声和执行条件，“每采样TV”不作为通用修复。
最大绝对误差包含参考阶跃瞬时，不能当作稳态精度。
延迟等于运行时长允许作为极端场景，记录 no_live_measurement_during_control 诊断。
interface_error 表示接口/配置记录/复位等错误；numerical_failure 表示非有限量或数值阶段异常。
metric_failure 表示指标超出可表示范围，结果不可比较。默认捕获并记录，simulate(..., fail_fast=True) 可保留原异常调试。
KeyboardInterrupt 等用户中断不转为数值失败；批次保存中断标记后继续向上传播。

## 时间与状态字段

| 字段 | 含义 |
|---|---|
| observed_until_s | 最后一条true_output_rad_s非空行的时间；没有有效输出时约定为0，不代表已完成一次观测 |
| termination_time_s | 最后尝试采样的循环时刻；尚未进入循环的复位/元数据失败为0 |
| last_integrated_time_s | 最后一次成功返回的advance所对应区间的结束时间；无成功推进时为0 |
| action_taken | 已把该行输入交给对象advance；即使advance随后抛异常也可能为true |
| transition_completed | 对象advance已成功返回；为true的行才覆盖interval_s时长 |

| recovery_status | 含义 |
|---|---|
| recovered_in_observation_window | 最终连续在带内的时长满足dwell，恢复时间有值 |
| not_recovered_in_observation_window | 观察窗内未达到判据，恢复时间null |
| run_incomplete | 运行提前停止，不计算完整窗口恢复指标 |
| metrics_invalid | 指标计算溢出或非有限，指标不可比较；对应metric_failure |

## 批次产物协议

v0.1.2的manifest schema为1.2，trace_schema_version=1.1；CSV列保持1.1，status.json采用schema 1.0。
status.json是权威状态文件，manifest中的status_authority明确指向它。

| state | 含义 |
|---|---|
| in_progress | 正在运行或写出，尚未提交完整产物集 |
| completed | 全部预期运行完成且无失败 |
| completed_with_failures | 显式继续策略运行完全部任务，其中包含失败 |
| stopped_on_failure | 默认策略在首次失败后停止，保留已完成的记录和失败报告 |
| aborted | 普通异常中止，如写盘失败，继续重抛原异常 |
| interrupted | KeyboardInterrupt或SystemExit中止，继续传播原中断/退出码 |

所有状态固定包含schema_version、state、expected_runs、written_runs、failed_runs、artifacts_complete、error_type、message。
无异常时最后两项为null，计数初始为0；written_runs仅统计CSV和逐次JSON均已写出的记录，failed_runs是其中的失败数，
尚未完整写出的运行不计入这两个数。

先写逐次记录、汇总和报告，再写manifest与checksums，最后写带artifacts_complete=true的status.json。
checksums预先使用该最终状态的序列化字节计算status.json指纹。
外部程序必须同时检查终态、artifacts_complete和checksums，不能只看manifest的batch_status。
artifacts_complete只表示产物集完整，含失败或提前停止的批次也可以产出完整报告。
异常路径尽力更新status和已存在的manifest；若介质已不可写，或进程被强制终止，标记可能无法更新，
此时缺少完整标记或校验不通过的目录不得当作已验证实验。

## 复现与溯源

manifest.json 记录对象、控制器、场景、时间窗、版本和环境。逐次 CSV 保存实际轨迹。
checksums.json 记录输出文件 SHA-256，能帮助发现文件变动，不能证明测量来源真实。
输出目录禁止覆盖；正式引用实验时同时记录所用源码提交版本。
