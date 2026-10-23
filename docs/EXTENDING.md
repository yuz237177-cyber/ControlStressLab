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
reference/load 为 StepSignal，首点为 t=0；所有事件、延迟与评价时刻必须严格对齐 dt。
跨采样周期比较时不能假定每样本相同噪声标准差对应相同物理噪声谱。

## 当前通用性边界

协议中的 u、output 和 disturbance 为一般标量，数学执行可用于其他对象。
v0.1 的 Scenario 参数名 voltage_limit、CLI、CSV 列名和指标单位仍为电机演示约定。
因此其他物理对象需自行适配记录单位，不应直接套用电机报告。
后续版本再引入单独的信号单位元数据和一般执行器接口；本版不宣称支持任意对象的完整开箱报告。
