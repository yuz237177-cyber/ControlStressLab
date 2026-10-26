# ControlStressLab

[![tests](https://github.com/yuz237177-cyber/ControlStressLab/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/yuz237177-cyber/ControlStressLab/actions/workflows/tests.yml)
[![version](https://img.shields.io/badge/version-1.0.0-green)](https://github.com/yuz237177-cyber/ControlStressLab/releases/tag/v1.0.0)

**面向单输入单输出系统的控制器压力测试、参数整定与性能分析桌面工具。**

从定义对象、声明要求，到多工况搜索、冻结主选和新工况验证，保留每项结论对应的配置、模型、原始轨迹与图表。项目按动力学类型组织，不绑定电机或轨道交通。

> 全部示例与公开实验来自合成仿真，尚未进行硬件验证。有限工况下满足要求、正裕度或可复现，均不构成真实设备适用性或鲁棒稳定性证明。

## 下载与运行

**[下载 v1.0.0 Windows x64 便携版](https://github.com/yuz237177-cyber/ControlStressLab/releases/download/v1.0.0/ControlStressLab-v1.0.0-Windows-x64.zip)**（约141 MB，无需安装Python）

[版本说明与全部附件](https://github.com/yuz237177-cyber/ControlStressLab/releases/tag/v1.0.0) · [SHA256校验清单](https://github.com/yuz237177-cyber/ControlStressLab/releases/download/v1.0.0/SHA256SUMS.txt)

1. 完整解压ZIP，保留同目录的 `_internal` 文件夹。
2. 双击 `ControlStressLab.exe`。
3. 进入“研究项目”，选择一阶、二阶或自定义四阶示例，点击“打开完整示例”。
4. 双击阶段列表查看实验、扫描、搜索、冻结验证和频域结果，再建立自己的模型与协议。

默认工作区为 `%LOCALAPPDATA%/ControlStressLab`，项目页显示实际保存位置。修改草稿不会重写历史结果；导出的 `.cslproj` 项目包可以在另一目录导入并继续分析。

已在Windows11 x64本机隔离Python路径后验证完整流程，并检查125%／150%／200%缩放。另一台全新Windows机器、不同显卡及Windows10兼容性仍需进一步复测。

## v1.0能做什么

| 模块 | 功能 |
|---|---|
| 通用模型 | 输入1～4阶连续实系数严格真有理SISO传递函数，分别定义控制与扰动通道、单位和初始状态；保存开环预览与采样矩阵 |
| 配对控制实验 | PI、抗饱和PID、双自由度PID；原内置对象另保留LADRC；在相同参考、扰动、噪声、延迟与限幅下比较 |
| 参数扫描 | 1～2轴有限网格，检查增益、时间尺度、噪声、延迟与扰动变化，定位不满足要求的原始工况 |
| 约束整定 | 预先声明误差、饱和比例及动作变化率要求，多工况搜索并比较误差与动作之间的取舍 |
| 冻结验证 | 保存主选与选择依据，在未参与选择的新工况上验证；保留失败记录，不根据验证结果重新排名选参 |
| 频域解释 | 对应实际数字PI/PID的Bode、未约消内部极点、S/T、参考／扰动通道和有限频段交越明细，保存逐点与正弦核对 |
| 完整项目 | 模型、协议、各阶段记录、观察历史与任务日志一起导出，迁移后按冻结指纹定位来源 |
| 可追溯产物 | 配置、模型快照、CSV、指标、PNG/SVG、离线HTML与文件校验值自动保存 |

### 频域与时域联动

![v1.0实际频域工作台](docs/design/v1.0-desktop-frequency.png)

频域对应未饱和、固定参数的数字控制器分支，保留采样、测量延迟、测量微分及滤波时序。内部稳定性与GM/PM分别报告；缺失、奇点或分辨率受限使用明确状态。有限频段采样不保证找到所有可能的交越。

LADRC的频域模型及通用对象兼容性尚未建立；当前不以近似PID替代。MIMO、直接状态空间编辑、系统辨识和硬件实时闭环不属于v1.0范围。

### 围绕一个问题组织实验

![v1.0实际项目主页](docs/design/v1.0-desktop-project.png)

项目围绕“模型 → 要求 → 搜索 → 选择 → 冻结 → 验证”组织。阶段标记表示记录已保存，是否满足要求请打开对应结果查看。克隆项目继承已观察输入，不能把看过的数据重新当作新验证工况。

三套示例覆盖一阶过程、二阶振荡与自定义四阶对象。每套包含实际运行的实验、扫描、搜索、冻结、验证和频域结果。

## 验证与证据

v1.0本机验收结果：

- **231项测试通过**，包含20项Qt交互、11项频域与5项项目／原子写入检查。
- 独立参考检查12个频域控制器案例、60条PID／协议记录和41条通用四阶对象轨迹。
- 隔离外部Python配置后，12个后台任务均使用便携包内的程序，完成项目迁移后的验证和频域重算。
- 保存17张实际窗口截图；三套完整示例保留102组PNG/SVG以及全部原始轨迹。
- 原有报告、图片和历史证据包继续保留。

这些数字描述本机已执行的检查，不代表所有平台或全部模型均通过验证。线上检查状态以[GitHub Actions](https://github.com/yuz237177-cyber/ControlStressLab/actions/workflows/tests.yml)为准。

[桌面使用指南](docs/V1_0_DESKTOP_GUIDE.md) · [交付验收与适用边界](docs/V1_0_DESKTOP_VERIFICATION.md) · [模型数学口径](docs/V1_0_GUIDE.md)

## 从源码运行与复现

需要Python 3.10+：

```sh
python -m pip install -e ".[gui]"
python run_gui.py
```

仅使用原有内置对象的核心仿真不依赖第三方数值库；通用模型需要 `.[analysis]`，绘图需要 `.[charts]`。桌面依赖集合已包含二者。

```sh
python -m controlstresslab.experiment --config configs/experiment-transfer-function.json --output outputs/my-experiment --plots
python -m controlstresslab.frequency --output outputs/my-frequency --plots
python -m controlstresslab.tuning --config configs/tuning-transfer-function.json --output outputs/my-search --plots
python -m unittest discover -s tests -v
```

输出目录必须是新目录。原始HTML报告需下载后在本机打开；GitHub网页不直接运行离线HTML。

在Windows上重新构建便携包：

```sh
python -m pip install -e ".[gui,build,reference]"
python scripts/build_desktop.py --verify
```

构建脚本生成完整示例、独立程序、迁移和缩放检查、逐文件清单及ZIP；已有交付目录不会覆盖。[详细构建与使用说明](docs/V1_0_DESKTOP_GUIDE.md)

## 设计记录与后续研究

| 内容 | 入口 |
|---|---|
| 版本与兼容范围 | [CHANGELOG](CHANGELOG.md) · [路线图](docs/ROADMAP.md) |
| 本轮验收状态 | [校验记录](docs/VERIFICATION_STATUS.md) |
| 多工况约束整定 | [协议](docs/V0_8_EXPERIMENT_PROTOCOL.md) · [功能说明](docs/V0_8_GUIDE.md) |
| 扫描与跨实验对照 | [v0.6说明](docs/V0_6_GUIDE.md) |
| 历史GUI与结果 | [v0.9界面记录](docs/V0_9_GUI_GUIDE.md) · [v0.4历史版本](https://github.com/yuz237177-cyber/ControlStressLab/releases/tag/v0.4.0) |
| 研究计划 | [v2.0科研路线](docs/V2_0_RESEARCH_PLAN.md) |

v2.0计划围绕有限预算下的约束感知工况采样开展本科研究，先做文献核对与基线复现，再进行预声明实验和独立验证。目前不宣称方法新颖性或已取得论文结果。

## License

[MIT](LICENSE)。Windows包另附所用第三方组件的许可文本。
