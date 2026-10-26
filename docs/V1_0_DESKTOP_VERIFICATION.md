# v1.0独立桌面交付验收

> 2026-10-26发布更新：v1.0.0的公开安装包与校验清单见[GitHub Release](https://github.com/yuz237177-cyber/ControlStressLab/releases/tag/v1.0.0)。下文的本机验收记录保留其执行时范围；线上状态以[Actions](https://github.com/yuz237177-cyber/ControlStressLab/actions/workflows/tests.yml)为准。

2026-10-25，版本**1.0.0**。完成本机Windows x64独立桌面交付；原生界面与后台任务使用便携包中的运行环境，无需外部Python。

## 可用产物

- 程序：`dist/v1.0.0/ControlStressLab/ControlStressLab.exe`。
- 便携ZIP：`dist/ControlStressLab-v1.0.0-Windows-x64.zip`。
- ZIP大小：141,195,509字节，约134.65MiB；包内1232文件。
- SHA256：`82534d78c05f6d02509f5c6c9178853a33c91154c2ae0743785dd6c34cfebbf9`。
- 同目录提供.sha256.txt、交付收据；程序目录包含逐文件校验清单、构建信息、离线使用说明与第三方许可文本。

dist与outputs为本机产物，不表示已上传GitHub。解压整个目录后启动EXE，保留_internal目录。

## 交付范围

M1通用模型继续保留；新增M2数字PID频域模型、M3项目与迁移流程、M4桌面入口，以及M5本机便携包。三套完整项目包含一阶过程、二阶振荡和通用四阶对象，从控制实验、扫描、搜索、冻结、验证到频域均实际运行并保存。

频域采用实际采样积分/测量微分/滤波时序，延迟位于测量路径，检查未约消内部矩阵极点。有限频段交越搜索保存检出项、残差与数值状态；不声称全频率根计数保证。小阶跃逐点核对及适用时的正弦核对随分析保存。

项目索引使用相对引用，原始运行目录、模型和冻结收据不改写。迁移后按指纹定位原搜索；观察登记和任务日志一起导出。已实际检查移走原目录后继续冻结验证和重新运行来自原工况的频域分析；单独频域目录也保存来源副本，以支持离开原目录后重算。

## 自动与独立检查

| 检查 | 结果 |
|---|---|
| 全部本机测试 | **231项通过**，173.600秒；包含20项Qt交互、11项频域、5项项目/原子写入检查 |
| 三套示例 | 每套6个完整阶段，共102张PNG、同数SVG；原始CSV、配置、源码及冻结依据保留 |
| 独立频域核对 | 12个控制器案例通过；SciPy ZOH、独立PID状态推进与python-control FRD，不导入产品计算代码 |
| 独立频域数值 | 比较344,442个通道复数值；最大归一化差1.0394e-12，最大内部极点差4.4349e-13 |
| 独立交越对照 | 参考检出24项；最大相对频率差2.1736e-08，预设容差1e-3 |
| 独立PID/协议审计 | 六份报告、60条搜索/验证记录通过；原始指标最大差4.9738e-14 |
| 独立通用对象回放 | 41条四阶对象轨迹通过Python3.9.13/SciPy1.9.1环境DOP853回放；最大输出差6.3283e-15 |
| 交付文件 | ZIP CRC及逐文件SHA256通过；应用内源码快照与本轮源码一致 |
| 原数据留存 | 原v0.8、M1证据包SHA256未变；M1的11张界面图逐张与归档一致 |

频域独立参考使用python-control0.10.2；对象回放使用NumPy1.21.5/SciPy1.9.1的独立环境；应用计算使用NumPy2.5.4/SciPy1.17.1。检查的是声明模型和实现的一致性，全部数据仍为合成仿真，不等于硬件验证或鲁棒稳定性证明。

## 实际独立运行

清空PYTHONPATH/PYTHONHOME/QT等外部配置，PATH只保留Windows系统目录；把程序复制到中文、含空格的另一目录启动。系统中仍有开发Python，但程序未通过该Python启动，也未通过它执行后台计算。

原生窗口完成：
1. 从便携包导入完整示例。
2. 建立模型并保存开环预览。
3. 三控制器实验和参数扫描。
4. 候选搜索、填写依据、主选冻结、新工况验证。
5. 频域四类图表与原始数据保存。
6. 完整项目导出，移走原项目目录，导入新目录。
7. 从迁移后的收据继续验证，并从迁移后的原工况重新计算频域。

共12个后台任务的记录确认`frozen=true`，执行文件均为同一便携包EXE；界面保持响应，心跳2338次。

本机Windows11上检查125%、150%、200%像素比，小窗口与键盘展开/收起；保存17张真实截图。构建中修复了同名ICU库误混入、SVG后端遗漏和Windows文件短暂被占用导致的提交失败。

**尚未在另一台全新Windows实机复测**，不将本机环境隔离描述为干净机器验收。线上CI与正式公开Release尚未执行，本轮没有上传GitHub。Windows10、不同显卡/机器仍需额外兼容性检查。

## 证据位置

- `outputs/desktop-final-build/desktop-acceptance.json`：独立运行、全部后台程序路径和项目迁移。
- `outputs/desktop-final-build/layout-1.5.json`、`layout-2.0.json`：缩放检查。
- `outputs/v1-frequency-reference.json`、`v1-frozen-frequency-reference.json`：独立频域结果。
- `outputs/v1-custom-linear-reference.json`与六份v1-audit报告：对象回放、PID与协议审计。
- `outputs/v1-final-verification.json`：本轮摘要。
- `outputs/desktop-final-build/example-results`：三套全部原始示例；程序包内examples目录保存可导入项目包。


- [v1.0-desktop-project.png](design/v1.0-desktop-project.png)
- [v1.0-desktop-model.png](design/v1.0-desktop-model.png)
- [v1.0-desktop-response.png](design/v1.0-desktop-response.png)
- [v1.0-desktop-frequency.png](design/v1.0-desktop-frequency.png)
- [v1.0-desktop-validation.png](design/v1.0-desktop-validation.png)
- [v1.0-desktop-relocated.png](design/v1.0-desktop-relocated.png)
- [v1.0-desktop-compact.png](design/v1.0-desktop-compact.png)
- [v1.0-layout-1.5-bode.png](design/v1.0-layout-1.5-bode.png)
- [v1.0-layout-1.5-poles.png](design/v1.0-layout-1.5-poles.png)
- [v1.0-layout-1.5-sensitivity.png](design/v1.0-layout-1.5-sensitivity.png)
- [v1.0-layout-1.5-channels.png](design/v1.0-layout-1.5-channels.png)
- [v1.0-layout-1.5-project.png](design/v1.0-layout-1.5-project.png)
- [v1.0-layout-2.0-bode.png](design/v1.0-layout-2.0-bode.png)
- [v1.0-layout-2.0-poles.png](design/v1.0-layout-2.0-poles.png)
- [v1.0-layout-2.0-sensitivity.png](design/v1.0-layout-2.0-sensitivity.png)
- [v1.0-layout-2.0-channels.png](design/v1.0-layout-2.0-channels.png)
- [v1.0-layout-2.0-project.png](design/v1.0-layout-2.0-project.png)

使用入口见[桌面指南](V1_0_DESKTOP_GUIDE.md)，独立参考脚本分别为scripts/check_frequency_reference.py、scripts/check_tuning_evidence.py和scripts/check_linear_model_reference.py。
