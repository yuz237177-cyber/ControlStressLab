# 已保存的实验成果

## 波形、算法与对象覆盖

- [完整报告](coverage-expansion-2026-10-24/report.html)
- [完整ZIP](coverage-expansion-2026-10-24.zip)
- [实际结果与解释](../docs/COVERAGE_EXPANSION_RESULTS.md)
- [独立SciPy逐项核对](coverage-reference-final-2026-10-24.json)

12组图片各含PNG和SVG：参考波形、扰动波形、四对象响应、四对象指标热力图、实际控制动作及归一化取舍。
归档同时保存224条完整CSV、逐次配置、56组配对输入/噪声数组、汇总、源码快照与校验清单。
既有三轮图片与报告继续保留。

## 独立工具对照

- [完整报告](reference-scipy-2026-10-24/report.html)
- [完整ZIP](reference-scipy-2026-10-24.zip)
- [结果解释](../docs/REFERENCE_COMPARISON_RESULTS.md)

包含54个配置的双方完整JSON轨迹、4组PNG/SVG、全部输入、逐项判据、工具版本和源码快照。
同一开发者的独立实现及SciPy两种数值路径对照，不等于第三方审计或硬件验证。

## 扰动强度与测量延迟扫描

- [完整报告](load-delay-2026-10-24/report.html)
- [固定归档说明](load-delay-2026-10-24/README.md)
- [完整ZIP](load-delay-2026-10-24.zip)

包含8组PNG/SVG、286条完整轨迹、配置/指标、11份匹配源码快照及校验清单。
共606个保留文件（另有归档清单）；ZIP内容已逐项核对。原outputs目录继续保留。

## 参数不确定性分析

- [固定归档说明](parameter-uncertainty-2026-10-23/README.md)
- [完整报告](parameter-uncertainty-2026-10-23/report.html)（下载仓库后在本机打开）
- [完整ZIP](parameter-uncertainty-2026-10-23.zip)

归档包含上一轮7张PNG、7张SVG、196次配置/指标、代表性轨迹，以及与当时指纹一致的源码快照。
原实验文件校验值、归档校验值和ZIP内容均已核对。原outputs目录也继续保留，归档不覆盖原结果。

后续实验应使用新输出目录。需要制作固定归档时可运行：

```sh
python scripts/archive_results.py --source outputs/my-experiment --destination reports/my-experiment
```

目标目录或同名ZIP已存在时命令拒绝执行。合成结果的保存和校验不能证明硬件真实性。
