# 波形、控制器和对象扩展设计（2026-10-24）

本轮先固定覆盖矩阵，再计算结果。不进行运行结果驱动的重新调参。
沿用配对实验设计：每个对象/场景下的所有控制器共享参考、扰动、采样周期、限幅及噪声序列。
一次配置是一条确定性合成轨迹，不把时间采样点或不同配置当作独立统计重复。

## 覆盖矩阵

四类对象：一阶对象、约化电机、含电枢电感的二状态电机、质量—弹簧—阻尼系统。
四种方案：普通PI、带测量微分和条件积分抗饱和的PID、双自由度PID(beta=0.6, gamma=0)、线性ADRC。
14类场景：阶跃/斜坡/正弦/三角/线性扫频/多次阶跃参考，
阶跃/矩形脉冲/正弦/方波/线性扫频/随机二值块扰动，正弦参考+二值扰动，以及噪声+测量延迟。
共4×4×14=224次，dt=0.01 s，时长16 s，噪声种子42。

全部波形在控制网格上预生成，以零阶保持施加到对象。不会把连续波形假定成区间内精确连续变化。
PRBS在此是固定种子的独立±幅值二值块，每块0.5 s，不声称是最大长度LFSR序列。
采样周期、波形长度、事件与保持块必须对齐；正弦/扫频最高频率每周期至少10个样本。
方波的边沿由控制网格表示，不把它称为无混叠的连续方波。

## 单位与参数

| 对象 | 输出 / 输入 / 扰动单位 | 参考尺度 | 输入限幅 | 扰动幅值 | kp / ki / kd（PID） | LADRC阶次 / b0 / wc / wo |
|---|---|---:|---:|---:|---|---|
| FirstOrder(gain=1,tau=1) | unit / unit / unit | 1 | 3 | 0.2 | 1.5 / 1 / 0.1 | 1 / 1 / 2.5 / 10 |
| DCMotor（原默认值） | rad/s / V / N m | 60 | 12 | 0.15 | 0.25 / 0.8 / 0.015 | 1 / 10 / 3 / 12 |
| InductiveDCMotor（原电机参数，L=0.2 H） | rad/s / V / N m | 60 | 12 | 0.15 | 0.25 / 0.8 / 0.03 | 2 / 50 / 2 / 10 |
| MassSpringDamper(m=1,c=0.6,k=4) | m / N / N | 0.5 | 5 | 0.5 | 6 / 3 / 3 | 2 / 1 / 2.5 / 10 |

普通PI使用同对象kp、ki，kd=0且无抗饱和；另两个PID使用相同kp/ki/kd及滤波时间0.03 s。
不同算法参数并未通过统一带宽/控制能量优化，因此图表只比较这些公开配置，不能推出算法普遍优劣。
同一对象的参数跨所有场景固定。LADRC仅接收测量与自己上一拍的实际限幅输入，不能访问真实速度/电流/外扰。

## 方程与离散实现

```text
含电感电机：J*omega' = Kt*i - b*omega - load
             L*i' = u - R*i - Ke*omega
质量弹簧：  x' = v; m*v' = u + disturbance - c*v - k*x
双自由度：  u = kp*(beta*r-y) + I - kd*filtered_dy; I候选量仍用(r-y)
一阶ESO：   z1' = z2 + b0*u_applied + 2*wo*(y-z1)
             z2' = wo^2*(y-z1)
二阶ESO：   z1' = z2 + 3*wo*(y-z1)
             z2' = z3 + b0*u_applied + 3*wo^2*(y-z1)
             z3' = wo^3*(y-z1)
```

二状态对象采用2×2解析矩阵指数/ZOH，核心不增加第三方依赖。
ESO使用显式Euler、旧状态同时更新，反馈使用更新后的估计；上一拍实际输入用于观测器，初值z1=y0、其余0。
一阶控制为(wc*(r-z1)-z2)/b0，二阶为(wc^2*(r-z1)-2*wc*z2-z3)/b0。
要求wo*dt<=0.2，属于本实现的采样保护条件，不是整个闭环稳定性证明。

新导出采用通用列名，并单独记录单位；兼容仿真内核仍保留原电机字段名，不将其作为新CSV的物理单位。
持续变化参考或持续周期扰动场景标记tracking_only，恢复时间为null且状态为not_applicable_tracking_only。
斜坡/多次阶跃结束后，才从最终参考固定时刻评价恢复；脉冲结束后单独评价。

## 指标、验证和产物

在t>=0.5 s的真实状态上计算左端矩形IAE、RMSE、输入总变差和饱和时长比例。
跨对象图采用NRMSE=RMSE/参考尺度、NIAE=IAE/(尺度×评价时长)、TV/输入限幅；没有总分或统一冠军。
失败运行完整窗口指标必须为null，图表不能以零分代替失败。每个对象另画独立热力图和响应。
所有224条CSV/配置、汇总、状态、源码指纹、报告与12组PNG/SVG一起保存，再制作不可覆盖的ZIP归档。

验证包括波形边沿/复现/长度/采样、变化参考的恢复语义、二状态解析解和分步保持一致性、
2DOF退化为原PID、ESO方程/实际输入反馈/重置，以及整批配对和产物校验。
补充SciPy外部工具回放新对象的保持输入，验证对象推进；这部分不等于独立验证新的控制器算法。

方程依据：
[电机建模（密歇根大学CTMS）](https://ctms.engin.umich.edu/CTMS/index.php?example=MotorSpeed&section=SystemModeling)、
[质量弹簧阻尼（CTMS）](https://ctms.engin.umich.edu/CTMS/index.php?example=Introduction&section=SystemModeling)、
[2DOF PID（MathWorks）](https://www.mathworks.com/help/control/ug/two-degree-of-freedom-2-dof-pid-controllers.html)、
[LADRC结构（MathWorks）](https://www.mathworks.com/help/slcontrol/ug/active-disturbance-rejection-control.html)、
[LADRC（Herbst原文）](https://www.mdpi.com/2079-9292/2/3/246)。
这些资料支持方程和结构，不支持本项目参数是实测值；本轮仍是合成教学模型。
