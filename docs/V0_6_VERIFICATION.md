# v0.6本机验收与结果边界

日期：2026-10-24。版本：0.6.0.dev0。环境：Windows、Python3.12.14、PySide6-Essentials6.12.0、Matplotlib3.11.2。本轮未上传GitHub，线上CI尚未验证这些改动。

## 自动检查

完整171项测试通过：原150项、11项通用扫描、6项跨实验服务、4项新增Qt交互。GUI依赖未安装时，160项非GUI检查执行，11项Qt测试明确跳过。

```sh
python -m unittest discover -s tests -v
```

新检查覆盖完整网格与预算、全点预校验、固定控制器参数、两个对象和全部控制器对原内核的完整轨迹一致性、噪声配对、阈值边界、失败指标null、失败种子遮罩、不覆盖、取消和写图失败。

对照检查覆盖单位不兼容、重复轨迹、窗口/多因素提示、原指标/输入/CSV字节保留、源目录消失后的独立读取、预览后源文件被修改时禁止导出。

Qt通过实际按钮启动后台进程，验证扫描配置导入/保存、热力图点击、最差已完成工况定位、协作取消和对照快照。独立CSV审计加入负向测试：伪造保存RMSE并同步更新该文件校验后，独立复算仍能发现错误。

## Windows原生窗口

| 案例 | 设置 | 运行数 |
|---|---|---:|
| 一阶扫描 | 5个时间常数×5个延迟×3个噪声种子×PID/LADRC | 150 |
| 二阶扫描 | 5个质量×3个阻尼×2个噪声种子×PID/LADRC | 60 |
| 失败路径注入 | 2个时间常数×2个种子×2个控制器，故意收紧输出越界阈值 | 8 |
| A/B/C自由实验 | 无噪声/延迟、只加噪声、噪声+延迟，各2个控制器 | 6 |
| 对照快照 | A/B/C中各选PID原始轨迹 | 3条复制轨迹 |

前两组210次全部运行完成；8次故障注入均按运行失败保留，RMSE等数值为空。该注入用于验证软件错误路径，不是发现了真实对象的物理失效边界。

本机保留全部报告、CSV/JSON、默认PNG/SVG和导出ZIP，路径索引位于 `outputs/v06-verification.json`，任务数据位于 `outputs/gui-v06/experiments/`。

[参数地图](design/v0.6-parameter-map.png) · [要求检查](design/v0.6-requirements-map.png) · [最差已完成工况](design/v0.6-worst-observed.png) · [二阶地图](design/v0.6-second-order-map.png) · [失败遮罩](design/v0.6-failure-map.png) · [跨实验对照](design/v0.6-experiment-comparison.png) · [实际输入对照](design/v0.6-input-comparison.png)

## 独立审计与数值回放

在独立Python3.9.13环境执行无产品导入的 `check_scan_evidence.py`：218条扫描记录、109组配对输入全部通过，包含故障注入。两组正常扫描CSV指标复算最大绝对差分别为3.411e-13和2.501e-12，均在预先声明容差内。

独立SciPy1.9.1环境回放219条记录（216条原始轨迹及3条对照副本）和108条LADRC控制请求，全部通过；覆盖两个正常扫描、A/B/C实验与对照快照。故意失败的8条不作为完整轨迹参与该回放。

旧的五组固定报告校验均通过，历史数据未重写。与本轮生产实验指纹一致的31个源码文件另存于 `outputs/v06-source-snapshot/`。

本机测试记录：`outputs/v06-final-tests.log`；真实窗口记录：`outputs/v06-windows-verification.log`；独立审计：`outputs/v06-audit-*.json`；SciPy结果：`outputs/v06-scipy-*.json`。

新增命令已从构建出的0.6.0.dev0 wheel安装到独立目录，并在源码目录外完成18次扫描和跨工况对照快照，版本与导入路径已核对。记录位于 `outputs/v06-install.log`、`outputs/v06-installed-scan/` 和 `outputs/v06-installed-comparison/`。

完整本机成果另存为 `outputs/ControlStressLab-v0.6-dev-evidence-20261024.zip`，包含全部案例、图表、独立审计、真实截图及与生产指纹一致的源码快照。生产之后仅调整了GUI的中文图题/单位显示，归档保留生产源码与当前查看器源码两份，数值内核未改变。

## 边界

网格、阈值与种子描述有限测试条件，最大观察值不等于连续参数域的真正最坏情况。种子聚合不产生现实可靠性概率，满足阈值不构成稳定性证明。

当前仍需Python环境，未构建便携EXE。本轮没有发布v0.6或制作视频，公开稳定版本保持v0.4.0。
