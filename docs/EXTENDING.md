# Python 扩展接口

先在仓库执行 `python -m pip install -e .`，或在自己的源码环境中设置 src 路径。

```python
from controlstresslab import DCMotor, PID, Scenario, simulate
from controlstresslab.metrics import evaluate

run = simulate(DCMotor(), PID(anti_windup=True), Scenario())
print(evaluate(run))
```

## 对象协议

- output：当前真实标量输出。
- reset()：恢复独立运行的初始状态。
- advance(u, disturbance, dt)：保持实际输入和扰动推进 dt。

## 控制器协议

- reset()：清空积分、滤波器、历史测量等全部状态。
- command(reference, measurement, dt)：返回请求输入。
- observe_applied(applied)：接收执行限幅后的实际输入；无抗饱和需求也应提供空实现。

v0.1.1 要求 command 返回有限实数，不接受数值字符串、None 或布尔值。
默认运行捕获普通异常并返回带 failure（阶段、类型、消息、traceback）的 Run；fail_fast=True 可重抛。
用户中断始终向上传播。捕获并返回失败不表示对象内部已安全复位。

自定义对象/控制器可实现 `to_config() -> dict`，用于记录运行前配置。字段须能以严格 JSON 序列化。
非 dataclass 且未实现该方法时会显式记录 params_recorded=false，而不是声称配置完整可复现。

不能在控制器接口中传入真实状态、未来噪声或测试专用隐藏参数。

## 场景

Scenario 为不可变配置，修改可用 dataclasses.replace。
reference/load 支持 StepSignal 或 SampledSignal。StepSignal首点为t=0；SampledSignal必须与场景采样周期、长度一致。
所有阶跃事件、延迟与评价时刻必须严格对齐dt。采样波形在每个控制区间零阶保持。
跨采样周期比较时不能假定每样本相同噪声标准差对应相同物理噪声谱。

持续变化参考使用 `recovery_mode="tracking_only"`，此时跟踪指标正常计算，恢复时间为null并明确标记不适用：

```python
from controlstresslab import FirstOrder, LinearADRC, Scenario, simulate, waveform

reference = waveform("sine", duration_s=16, amplitude=0.3, offset=0.7)
scenario = Scenario(duration_s=16, reference=reference,
                    recovery_mode="tracking_only", voltage_limit=3)
run = simulate(FirstOrder(), LinearADRC(), scenario)
```

内置新增对象为 `InductiveDCMotor`、`MassSpringDamper`；控制器新增 `TwoDOFPID`、`LinearADRC`。
LADRC的阶次、b0和带宽需要与对象匹配，不应把某对象的参数直接套到另一对象。

## 当前通用性边界

协议中的 u、output 和 disturbance 为一般标量，数学执行可用于其他对象。
兼容内核仍保留Scenario的voltage_limit参数及原电机轨迹/指标字段名；它在数学执行中表示一般输入限幅。
基础演示报告继续采用电机单位。`controlstresslab-coverage`另行导出通用列名，并在配置/报告中记录每类对象的单位、尺度和限幅。
使用自定义对象时仍需明确单位，不能直接把旧电机列名当作新对象的物理量；任意执行器与任意自定义报告尚未通用化。
见 [覆盖扩展设计](COVERAGE_EXPANSION_DESIGN.md) 和 [轨迹协议](EXPERIMENT_PROTOCOL.md)。
