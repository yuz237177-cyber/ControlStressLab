# v0.4 GUI验收

日期：2026-10-24。范围：Windows、Python3.12.14、PySide6-Essentials6.12.0、Matplotlib3.11.2。版本v0.4.0，以需要Python环境的桌面版发布。

## 自动检查

150项测试通过：原131项数值与证据链测试、12项公共实验服务测试、7项Qt交互测试。没有GUI依赖的环境运行143项，另7项明确跳过。

```sh
python -m unittest discover -s tests -v
```

服务检查覆盖配置类型/范围、配对输入、8条一阶/二阶与全部控制器完整轨迹对照、终点空输入、失败指标null、中断保留、写图失败、禁止覆盖、ZIP逐文件一致性、路径越界和损坏/遗漏校验。

Qt检查通过实际按钮启动独立worker：二阶实验与相同配置CLI的完整轨迹/指标一致；运行中界面定时器持续响应；开始—取消—重试有效；失败状态、错误配置、预算训练/冻结测试、保存/导入配置、旧结果校验和后台ZIP均已验证。

## Windows真实窗口

使用Windows平台插件打开真实窗口，执行以下流程并从Qt窗口直接保存截图。截图不是设计稿，也未用手工生成的响应替换仿真数据。

- 一阶对象，4种控制器，各12秒阶跃/阶跃扰动。
- 二阶对象，抗饱和PID与LADRC，12秒正弦跟踪。
- 预算页快速协议：96次训练+64次冻结测试，共160次；全部原始训练记录及测试轨迹保留。
- 通用coverage与v0.3 benchmark历史目录读取、单位/指标和校验检查；其他已归档报告继续校验通过。
- 全部本轮实验自动保存PNG/SVG及原始数据，并另存完整ZIP。历史报告不被改写。

[一阶截图](design/v0.4-gui-running.png) · [二阶截图](design/v0.4-gui-second-order.png) · [预算配置](design/v0.4-gui-budget.png) · [冻结测试结果](design/v0.4-gui-frozen-test.png) · [本机历史](design/v0.4-gui-history.png)

本机细节记录位于 `outputs/gui-verification.json`、`outputs/gui-tests-v04.log`、`outputs/gui-windows-verification.log`，各实验位于 `outputs/gui/experiments`，运行日志与请求位于 `outputs/gui/jobs`。这些为本机验收记录，不是已上线的CI结果。

另在独立Python3.9.13/SciPy1.9.1进程中核对本轮GUI保存的118条对象轨迹及30条LADRC控制请求，全部通过。预算产物独立审计覆盖8组训练选择、112条保存轨迹、8组配对输入；指标复算最大差3.553e-15。该回放检查的是对象推进与线性观察器/控制矩阵，不是完整独立非线性闭环或硬件验证。

最终wheel已构建并安装到独立本地目录，在源码目录外通过pythonw启动GUI及子进程，2种控制器实验、图表保存与校验通过；导入路径与版本已确认来自安装目录。记录位于 `outputs/installed-gui-verification.json`。这证明Python包与无控制台启动流程可用，仍不等于免Python分发包验收。

## 边界与待办

源码启动器已可双击；v0.4.0发布Python包与源码，明确要求Python和桌面依赖。[完整GUI实验证据ZIP](https://github.com/yuz237177-cyber/ControlStressLab/releases/download/v0.4.0/ControlStressLab-v0.4.0-GUI-evidence.zip)附原始轨迹、PNG/SVG、配置、校验清单和匹配源码。

免Python便携EXE、Qt部署/许可证打包及干净Windows离线启动尚未完成，作为后续分发任务；Linux的offscreen测试不能代替Windows分发包验收。

本轮没有新增控制算法或修改训练选择规则；GUI与CLI一致只验证调用和存取一致性，不代表模型有实测真实性或存在普遍最优控制器。历史的SciPy对象回放与ADRC矩阵对照仍按其原范围解释。
