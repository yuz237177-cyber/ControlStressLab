# 独立工具数值对照协议（2026-10-24）

本协议在首次运行前固定。目的：检查公开方程的代码实现、采样时序和指标计算，不能验证参数来自真实电机。
参考程序不导入ControlStressLab，也不读取产品输出；仅接收模型参数、采样网格、参考/负载和预生成噪声。
两侧由同一开发者编写，因此属于独立实现与外部数值工具对照，不是第三方审计。

## 三条对照路径

1. 开环：一阶对象和约化电机，三种采样周期0.01/0.02/0.05 s，三组参数/非零初值，正负电压和负载阶跃。
   产品用自身advance；参考用SciPy cont2discrete(method='zoh')的矩阵指数离散化和dlsim。
2. 无饱和PI闭环：两对象、三种周期。参考把输出和积分量组成增广状态，用dlsim直接推进整个闭环，
   不复用产品的控制器循环。小幅参考/负载，双方必须确认没有限幅，kd=0、无延迟、无噪声。
3. 非线性采样闭环：两种条件积分设置，覆盖标称、负载、噪声、延迟、饱和后回落，
   加入上一轮的0.30/0.35/0.50 s延迟、0.15/0.55/0.60 N m负载代表点，
   以及非零测量微分（滤波/不滤波）、四个J/b角点。
   参考单独实现离散控制与延迟队列，每一保持区间重新调用solve_ivp(DOP853)，rtol=1e-11、atol=1e-12。

三条路径共享SciPy，不能算三套独立软件。状态空间矩阵指数与显式Runge–Kutta提供不同数值路径。
不是对既有196/286条扫描逐点使用外部工具复算；本轮对照的是事先选定的代表集。

## 时序和增广方程

t_k先记录y_k，再读取y_(k-d)+noise_(k-d)；延迟前史恒为真实初值、不叠加噪声。
控制器先计算候选积分，再产生请求输入，限幅后决定是否接纳积分；测量微分无参考跳变冲击。
u_k、load_k在[t_k,t_(k+1))保持；终点只记状态，不产生末尾输入。
参考侧事件先转换成整数索引，不调用产品StepSignal。噪声数组作为共同外生输入，不能验证随机数生成器本身。

标量离散对象 y_(k+1)=a*y_k+g*u_k+h*load_k，PI积分状态为更新前I_k。
令q=kp+ki*dt，则闭环矩阵为：

```text
A_cl = [[a-g*q, g], [-ki*dt, 1]]
B_cl = [[g*q, h], [ki*dt, 0]]
u_k = -q*y_k + I_k + q*r_k
```

## 预定判据（不根据结果调宽）

- 所有轨迹长度、时间索引及终点空输入必须一致，所有数值有限。
- 每一个输出/测量/请求输入/实际输入采样点满足 |product-reference| <= 1e-8 + 1e-9*|reference|。
- IAE满足绝对容差1e-6 rad、相对容差1e-9；独立参考用左端矩形积分，不能用梯形积分混比。
- 恢复状态和按采样网格定义的恢复时间完全一致；无末尾假动作。
- 任何不满足的对照均保留并报告失败，命令返回非零；不删除失败点、不重调增益。
- 包版本、Python版本、源码指纹、输入配置、双方原始轨迹、逐项判据和PNG/SVG图表一起保留。

## 复现

```sh
python -m pip install ".[reference,charts]"
python scripts/reference_checks.py --output outputs/reference-check --plots
# 已有另一套安装SciPy的Python也可作为独立进程：
python scripts/reference_checks.py --reference-python /path/to/python --output outputs/reference-check --plots
```

输出目录必须不存在。运行中status.json不会声称产物完整；最终需要核验checksums.json。
参考脚本兼容Python3.9，产品仍要求Python>=3.10；不同解释器之间仅通过JSON交换。

方法依据：[SciPy 1.9.1 cont2discrete](https://docs.scipy.org/doc/scipy-1.9.1/reference/generated/scipy.signal.cont2discrete.html)、
[dlsim](https://docs.scipy.org/doc/scipy-1.9.1/reference/generated/scipy.signal.dlsim.html)、
[solve_ivp](https://docs.scipy.org/doc/scipy-1.9.1/reference/generated/scipy.integrate.solve_ivp.html)。
