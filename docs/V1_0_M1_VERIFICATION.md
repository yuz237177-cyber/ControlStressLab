# v1.0 M1本机验收

> 历史方案/阶段记录；当前已实现范围及交付状态以[v1.0桌面指南](V1_0_DESKTOP_GUIDE.md)和[最终验收](V1_0_DESKTOP_VERIFICATION.md)为准。

日期：2026-10-25。版本：**1.0.0.dev0**。结论：通用模型第一阶段完成；完整v1.0仍在构建，未发布或上传本轮改动，新增线上CI尚未执行。

## 实现与边界

已实现1～4阶连续实系数严格真有理SISO模型、独立控制/扰动分子、标准型初始状态与单位、零阶保持计算、冻结模型矩阵与源码指纹。原生桌面增加模型编辑、导入/导出、后台开环预览；已接入PI/PID族实验、参数扫描、约束搜索、主选冻结及新工况验证。

通用对象不支持LADRC；已有内置对象继续保留其原有实现。通用PID族仍使用原有非负增益，控制方向由用户负责选择。没有直接通道、MIMO、离散模型导入或任意状态矩阵编辑。全部数据来自合成线性模型，没有硬件实测。

频域分析、项目迁移包、完整项目主页、免Python桌面包和干净Windows验收仍待完成。本轮证据ZIP是留档包，冻结收据保留原始绝对来源，不作为M3项目迁移能力。

## 自动检查

| 检查 | 实际结果 |
|---|---|
| 完整本机回归 | **213项通过**，92.029秒 |
| 模型数值与流程检查 | 19项，包含解析解、原内置对象逐点比较、独立积分、非法输入、取消/失败及快照冻结 |
| Qt交互及真实后台进程 | 18项，包括自定义模型预览、导入导出、发送到实验与重开结果 |
| 旧数据 | v0.8五个实验目录和既有设计图片共4572文件校验值不变；原82MB证据ZIP指纹不变 |
| 已安装wheel、离开源码目录 | 自定义三控制器实验与四阶开环预览均完成 |
| 无第三方数值依赖 | 原内置对象仍能运行；自定义对象缺依赖时在创建结果目录前拒绝 |

包含一阶正/零/负增益与非零初始输出，二阶无阻尼/欠阻尼/临界/过阻尼及非零初始速度，积分对象解析解、四阶非恒定分子、两个独立通道和增益/时间尺度，以及保留被极零抵消的内部不稳定模式。

错误控制方向产生的闭环越界保留失败轨迹，输出状态为包含运行失败的完整报告；开环发散预览与取消不标成成功。模型实例和已保存矩阵不随外部字典或编辑器的后来修改变化。

验证去重依据实际连续标准型矩阵、初始状态及输入数据。新增检查证明模型名/单位标签改变、归一化后相同的系数写法不能重新包装成新验证工况。不宣称任意坐标变换下的符号等价判别，也不替用户补齐其他工作区的观察历史。

## 独立回算与审计

计算环境：应用侧NumPy2.5.4、SciPy1.17.1；独立回算侧Python3.9.13、NumPy1.21.5、SciPy1.9.1。独立脚本不导入产品模块，使用SciPy tf2ss从系数重建对偶状态模型，以DOP853重放记录中的实际保持输入/扰动；不调用产品的采样矩阵执行器。

- **55条轨迹通过**：桌面开环1条、三控制器实验3条、扫描27条、搜索16条、新工况验证4条；安装后实验3条及四阶预览1条。
- 最大输出绝对差：3.1086e-15；逐轨迹容差为2e-8×(1+最大绝对输出)。
- 故意将临时副本某个输出样本加0.01，数值回放明确拒绝；原始数据保持不变。
- 另以无产品导入的标准库审计检查16条搜索与4条验证的PID请求、限幅/积分、CSV指标、输入配对及冻结来源；指标最大绝对差2.220446049250313e-16。
- 全部新GUI与安装后结果的源码指纹与本轮源码一致；各目录完整性校验通过。

这些检查验证声明模型与数值实现的一致性，不证明模型代表真实设备，也不构成鲁棒稳定性证明。

## 原生Windows检查与图片

实际使用Windows Qt平台；默认像素比1.25，另以1.5检查。常规窗口1580×1000，小窗口1120×780；开环画布分别为1490×504、1021×480逻辑像素。150%像素比下画布1221×480。小窗口滚动和空格键展开/收起检查通过，模型参数不变。

保存11张实际截图到docs/design：

- [v1.0-gui-model-editor.png](design/v1.0-gui-model-editor.png)
- [v1.0-gui-open-loop-preview.png](design/v1.0-gui-open-loop-preview.png)
- [v1.0-gui-custom-response.png](design/v1.0-gui-custom-response.png)
- [v1.0-gui-custom-scan.png](design/v1.0-gui-custom-scan.png)
- [v1.0-gui-custom-candidates.png](design/v1.0-gui-custom-candidates.png)
- [v1.0-gui-custom-candidate-response.png](design/v1.0-gui-custom-candidate-response.png)
- [v1.0-gui-custom-frozen.png](design/v1.0-gui-custom-frozen.png)
- [v1.0-gui-custom-validation.png](design/v1.0-gui-custom-validation.png)
- [v1.0-gui-legacy-validation.png](design/v1.0-gui-legacy-validation.png)
- [v1.0-gui-model-compact.png](design/v1.0-gui-model-compact.png)
- [v1.0-gui-model-150-percent.png](design/v1.0-gui-model-150-percent.png)

## 本机证据与复现入口

- preview：`outputs/gui-v10-native-1792910996/experiments/20261025-144958-2051b5`
- experiment：`outputs/gui-v10-native-1792910996/experiments/20261025-145000-0cd510`
- scan：`outputs/gui-v10-native-1792910996/experiments/20261025-145003-3be8ab`
- search：`outputs/gui-v10-native-1792910996/experiments/20261025-145011-8a247e`
- selection：`outputs/gui-v10-native-1792910996/experiments/20261025-145016-2661bb`
- validation：`outputs/gui-v10-native-1792910996/experiments/20261025-145017-dc6b47`

完整留档：`outputs/ControlStressLab-v1.0-M1-evidence-20261025.zip`，7,889,001字节，压缩包逐文件SHA256和ZIP结构检查通过。

SHA256：`d7c9f23570188e7acb3c1f4573c5ac55f600559a20117dcd48b462a9888fbdbf`。

摘要：`outputs/v10-m1-final-receipt.json`；数值回算：`outputs/v10-linear-reference.json`；PID/协议审计：`outputs/v10-search-audit.json`、`outputs/v10-validation-audit.json`。outputs为本机产物，不代表已上传GitHub。

```sh
python -m unittest discover -s tests -v
python scripts/check_linear_model_reference.py --suite <实验或预览目录> --output <独立回算报告.json>
python scripts/check_tuning_evidence.py --suite <搜索或验证目录> --output <协议审计报告.json>
```

使用入口与模型口径见[通用模型指南](V1_0_GUIDE.md)。下一阶段M2的数学要求见[频域设计](V0_7_DESIGN.md)。
