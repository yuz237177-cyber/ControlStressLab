# ControlStressLab v1.0.0 — Windows独立桌面版

本版把控制器压力测试、通用建模、多工况整定、频域解释和完整项目流程整合为无需外部Python的Windows x64桌面程序。

## 下载与运行

下载 `ControlStressLab-v1.0.0-Windows-x64.zip`，完整解压后双击 `ControlStressLab.exe`。请保留同目录的 `_internal` 文件夹。首次使用可进入“研究项目”打开一阶、二阶或自定义四阶完整示例。

默认工作区为 `%LOCALAPPDATA%/ControlStressLab`。便携包大小141,195,509字节，SHA256：

```text
82534d78c05f6d02509f5c6c9178853a33c91154c2ae0743785dd6c34cfebbf9
```

## 主要更新

- 1～4阶连续实系数严格真有理SISO模型，显式控制/扰动通道、单位与标准型初态，保存开环预览和冻结矩阵。
- 对应实际采样PI/PID时序的Bode、内部极点、S/T、参考/扰动通道和有限频段裕度，附原仿真器逐点与正弦核对。
- 声明要求、多工况候选搜索、主选与依据冻结、未参与选择的新工况验证。
- 项目主页、原始阶段记录、观察历史、任务日志和完整项目包；迁移后继续验证及频域重算。
- 三套完整示例，102组PNG/SVG及原始CSV、模型、协议与报告保留。
- Windows x64便携包、同包后台执行器、离线使用说明和第三方许可清单。

## 已执行验证

本机231项测试通过；独立参考检查12个频域控制器案例、60条PID/协议记录和41条通用对象轨迹。清空外部Python配置、仅保留Windows系统路径后，在中文/空格目录运行独立程序，12个后台任务全部使用包内EXE，项目迁移后验证和频域重算通过。125%/150%/200%缩放检查通过，保存17张实际窗口截图。

## 范围与限制

全部示例为合成仿真，未完成硬件验证。频域对应未饱和线性分支；正裕度不替代内部稳定性、压力测试或鲁棒稳定性证明。LADRC继续用于原内置对象，通用对象/频域兼容性尚未建立。另一台全新Windows机器、Windows10及不同显卡仍需复测。

[README与使用入口](https://github.com/yuz237177-cyber/ControlStressLab/tree/v1.0.0#readme) · [完整验收](https://github.com/yuz237177-cyber/ControlStressLab/blob/v1.0.0/docs/V1_0_DESKTOP_VERIFICATION.md)
