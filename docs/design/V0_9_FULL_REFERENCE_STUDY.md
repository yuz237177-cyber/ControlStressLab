# v0.9：方舟资源全量视觉研究

> 后续实施更新：现已依据本研究接入0.9.0.dev0桌面界面，见[实际窗口与验收](../V0_9_GUI_GUIDE.md)。下文的未实现描述保留为研究/首稿阶段记录。

研究日期：2026-10-25。来源为用户指定的[明日方舟美术资源系统](https://www.ignoredone.space/index.php/arknights_design/)。本文记录视觉观察及对 ControlStressLab 的设计推导，不代表游戏官方设计规范。

## 实际完成的范围

本轮读取指定页面及其公开图片索引，对索引中的 **96 组、2358 个独立图片地址**建立清单，全部取得可读文件，并通过 **74 张编号联系表逐张进行缩略总览**。不是只看封面，也没有把下载成功计作看过。

在总览基础上，选取 **36 份原图**继续研究：其中 6 份长图查看顶部、中部、底部的选定区域，其余 30 份查看整幅图像，共 48 个放大面板。在取得的文件中识别出 21 份动图，每份检查 4 个代表帧，共 84 帧。

范围边界：这里的“全量”指该资源页面本轮公开索引内的全部图片。2358 张完成的是构图、颜色、版式及类型的缩略总览；没有把每张长图的所有小字逐字读完，也没有逐帧观看每份动图。放大阅读和动图抽样有单独清单。

本地检索目录、原始地址、分组、尺寸、文件校验值、逐批观察及放大位置保存在 `outputs/design-references/arknights/full-study/`。素材研究副本保存在忽略目录中；本文不把第三方画面作为产品内的美术素材。

## 上一稿为什么还差一点

上一稿主要取了《矢量突破》的黄紫配色、大字与少量几何装饰，界面骨架仍是侧栏、顶栏、等权卡片。曲线被装在面板里，标题、候选、操作和背景都处在相近的视觉层级，少了参考中的整屏构图与前后关系。

重新看全库后的判断是：下一稿首先需要重排画面，再决定配色、纹理和局部形状。给原来的面板加更多切角或发光边框，解决不了这个问题。

## 资源库中的主要视觉方向

以下为本轮观察后的分析分类；不同系列存在交叉，分类名称是研究用语。

| 方向 | 可定位的参考 | 画面组织方式 | 对我们有用的部分 |
|---|---|---|---|
| 白色档案与编辑排版 | G00–G06 等早期人物资料；G42 的 #0520、#0522 | 大标题、细分隔、序号、很小的资料标签、局部图像叠放 | 报告、实验档案、参数快照的文字层级 |
| 深蓝探索终端 | G36 #0467；G45 #0563 | 大面积低亮背景、局部青色焦点、紧凑功能区 | 曲线工作区的深度与关注点 |
| 灰阶工业与蓝色操作 | G48 #0595 | 灰阶主舞台、底部操作带、局部反白标签 | 扫描页的空间组织与行动位置 |
| 纸白科学档案 | G42 #0520、#0522、#0529 | 圆形图示、黑色标题带、少量橙色、宽松版心 | 实验报告的技术气质；这些图是宣传/设定资料，不能当作可操作界面直接套用 |
| 冷灰海洋与半透明条目 | G57 #0710 | 主景深度、浅色清单、状态淡化 | 背景与列表的前后层级 |
| 几何灰白与黄紫 | G62 #0812、#0815、#0820 | 大块灰白平面、空间化主图、背景巨字、边缘操作 | 主画面的构图和当前阶段的强调 |
| 灰白运动系统 | G70 #0987、#0995、#1009、#1016 | 主场景与前景选择面板、顶部局部导航、底部明确行动 | 候选选择、两方案取舍和禁用状态 |
| 蓝白制图与技术图解 | G72 #1076、#1083 | 横向关系、坐标/标注、大面积白底、局部信息 | 将真实流程、实验关系或信号路径组织成可阅读的画面 |
| 深灰工业与黄白信息窗 | G77 #1408、#1417、#1424 | 暗色整屏关系图，选中后出现浅色详情，操作贴近上下文 | 深色工作台和候选详情的主要参考 |
| 黑绿模拟系统 | G79 #1571、#1578、#1580 | 技术底图、紧凑状态、独立模拟入口、局部橙/绿 | 要求检查、运行状态、开始验证的布局 |
| 灰白建造系统 | G86 #1848、#1851、#1866、#1867、#1874 | 同一舞台上的选中/详情变化，少量酸黄和蓝色焦点 | 选中后展开、流程查看、局部详情和空状态 |
| 白色展览系统 | G92 #2155、#2177、#2199 | 场景化入口、清楚的收集列表、右侧详情、局部青色 | 实验浏览、比较列表与详情联动 |
| 高饱和蓝白与斜向排版 | G93 #2225、#2232 等 | 大色面、裁切文字、斜向装饰与规则的功能网格并置 | 首页和展示材料的识别度，少量用于导航 |
| 剧场、古典、旅行、游乐等主题 | G64/G73/G77 部分海报、G75、G80–G83、G88–G91、G94–G95 | 主题符号、插画、装饰字体与局部功能控件相配合 | 主题一致性、主次和空间感；不把所有装饰混进同一工作台 |

资源定位示例：[G62 矢量突破](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0926)、[G70 运动界面](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0317)、[G77 工业界面](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0904)、[G86 建造界面](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0516)、[G92 展览界面](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0807)。编号与实际文件地址见文末原图表。

## 可以迁移的设计规律

### 1. 让真实图表承担主画面

许多功能界面的主体是一张地图、关系图或空间场景，操作附着在主体周围。我们应把响应曲线、参数扫描图或候选权衡图放到这个位置。图表必须可以直接缩放、选中和对照，不能退化成低对比的背景装饰。

下一稿优先采用上方紧凑导航、中部完整图表、右侧可展开详情、底部当前操作的构图。实验历史可从侧边抽屉打开。详情展开时压缩或重排图表可用区域，不遮住坐标轴和需要查看的数据点。曲线与网格保持清晰，装饰巨字只出现在图外边缘。

### 2. 建立前景、内容和背景的明度差

主舞台使用深灰，边缘放低对比的原创技术纹理；当前候选或违规详情使用浅灰/纸白信息窗。选中条目、主操作和静态背景要有不同权重。每个页面保留一个最明显的主要行动。

参考中的部分发光、雾化和纹理会牺牲小字对比，我们只把它们用于图外背景。科学数据区使用平整底色，不叠颗粒、透视网格或模糊效果。

### 3. 字体加粗需要层级

页面标题和当前候选编号明显放大；分区标题和按钮加粗；指标使用清楚、对齐的数字；单位、来源和辅助说明退后一级。避免所有文本等大等粗。功能页面优先使用容易阅读的中文无衬线字体，衬线、手写和花体仅作为主题海报的观察对象。

建议的初始尺寸由我们重新制定：正文 15–16，按钮/分区 16–18，标题 26–32，关键编号 48–64 逻辑像素；数据标签保留足够字重与间距。实际实现按 Windows 缩放核验，不按截图固定像素。

### 4. 色彩先有语义

网站没有统一的“黑黄方舟色”。深蓝、纸白、橙、青、粉、黄紫都能形成完整系列。我们应选择一套主视觉，保持不同页面一致。

优先研究深灰工作台、纸白上下文面板与少量酸黄操作；曲线和比较方案使用独立的颜色与线型。当前选择、约束违规、运行失败、未验证、验证通过分别有文字和图标，不能用同一个亮色代替全部含义。黄色不同时承担“主要行动”和“失败”两种含义。

### 5. 状态变化比边框装饰更值得借鉴

#1866 与 #1867 展示了同一流程图在选中后出现详情的变化；#0995 与 #1016 展示了上下文变化后的可用项和行动；#2177 的列表与详情共享当前选择。借鉴的是这种状态对应关系。

动图抽样中，#1519–#1529 多为固定说明版式中的局部机制演示，#1900 为主题动作展示，#2315–#2316 和 #2350–#2356 为说明长图中的局部变化。这些不是桌面软件页面切换的直接证据，不据此推定控件动画时长。后续界面动效应服务于选中、展开、计算进度和结果定位，并可关闭。

## 对 ControlStressLab 各页面的具体推导

下面是本项目的设计建议，尚未作为 GUI 实现或验收结果。

| 页面 | 主画面 | 附属信息与行动 |
|---|---|---|
| 单次仿真 | 大幅响应曲线，控制量通过分图或切换查看 | 参数抽屉；当前对象、控制器和条件摘要；运行按钮 |
| 扰动/延迟/参数扫描 | 完整压力地图，选中工况有明显描边 | 工况详情、触犯的具体要求；打开原始轨迹和文件 |
| 多工况整定 | 候选权衡图；需要时切换至对应响应轨迹 | 当前候选、比较候选、约束状态与参数；保留同条件对照 |
| 候选比较 | 共享时间轴的真实曲线与关键约束 | 参数差异、误差/动作指标、主选按钮 |
| 违规定位 | 工况×要求的检查表或地图 | 直接显示哪一条超限、阈值和实测值；打开对应原始数据 |
| 冻结后验证 | 冻结参数摘要与新工况验证结果 | 搜索、冻结、验证清楚分开；没有运行时明确显示未验证 |
| 实验档案与导出 | 纸白档案排版、缩略图与来源 | 报告、候选、约束检查、验证、图片和轨迹清单 |

第一优先应重做“整定/候选比较”页面：它同时能检验大图、候选上下文、状态语义和主操作。先给出普通、选中候选、违规、已冻结未验证四种状态，再推广到其他页面。v0.7 频域尚未实现，不把频域图作为已完成模块展示。

## 下一稿的判断标准

- 远看能识别一块主画面、一组当前上下文和一个主要操作；不再是满屏等权卡片。
- 曲线可用面积实质增加，图外装饰不侵占刻度、图例和数据。
- 粗体标题、大编号、正文、数字和单位有明确层级。
- 选中/比较/违规/失败/未验证均能在不依赖颜色的情况下辨认。
- 深浅面板、留白与局部强调形成层次；不以增加切角数量作为美化目标。
- 窗口缩小、Windows 125%/150% 缩放后仍可读可操作。
- 界面数据来自实际实验；搜索达标不写成独立验证通过。

## 研究产物与当前状态

完整本地目录：`outputs/design-references/arknights/full-study/index.html`。

全量清单：`manifest.json`；逐批查看记录：`review-ledger.json`；放大/代表帧索引：`detail-index.json`；覆盖核对：`coverage-audit.json`。联系表为 `boards/board-000.jpg` 至 `board-073.jpg`，放大面板与代表帧位于 `details/`。

旧稿 `v0.9-arknights-workbench.png/.svg` 作为首轮探索保留，不再视为定稿方向。本轮只更新研究与设计依据，产品界面与源码版本未因本轮研究而变更。

<!-- GENERATED STUDY INDEX -->

## 放大研究的原图定位

| 图片编号 | 资源组 | 原图尺寸 | 查看方式 | 原始文件 |
|---|---|---|---|---|
| #0467 | G36 2022/0923 | 1000×2845 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2022/0923/018.jpg) |
| #0520 | G42 2023/0501 | 1000×4260 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2023/0501/005.png) |
| #0522 | G42 2023/0501 | 1000×3599 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2023/0501/007.png) |
| #0529 | G42 2023/0501 | 1146×717 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2023/0501/014.jpg) |
| #0563 | G45 2023/0711 | 1000×1934 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2023/0711/006.jpg) |
| #0595 | G48 2023/1002 | 2560×6400 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2023/1002/002.png) |
| #0710 | G57 2024/0529 | 2340×6480 | 顶部/中部/底部选定区域 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2024/0529/003.png) |
| #0812 | G62 2024/0926 | 1497×842 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2024/0926/008.png) |
| #0815 | G62 2024/0926 | 1497×842 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2024/0926/011.png) |
| #0820 | G62 2024/0926 | 1497×842 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2024/0926/016.png) |
| #0987 | G70 2025/0317 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0317/003.png) |
| #0995 | G70 2025/0317 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0317/011.png) |
| #1009 | G70 2025/0317 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0317/025.png) |
| #1016 | G70 2025/0317 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0317/032.png) |
| #1076 | G72 2025/0501 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0501/003.png) |
| #1083 | G72 2025/0501 | 2330×1311 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0501/010.png) |
| #1139 | G72 2025/0501 | 1920×1080 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0501/067.jpg) |
| #1140 | G72 2025/0501 | 1920×1080 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0501/068.jpg) |
| #1408 | G77 2025/0904 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0904/014.png) |
| #1417 | G77 2025/0904 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0904/023.png) |
| #1424 | G77 2025/0904 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/0904/030.png) |
| #1571 | G79 2025/1115 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/1115/055.png) |
| #1578 | G79 2025/1115 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/1115/062.png) |
| #1580 | G79 2025/1115 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2025/1115/064.png) |
| #1848 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/005.jpg) |
| #1851 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/008.jpg) |
| #1866 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/023.jpg) |
| #1867 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/024.jpg) |
| #1874 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/031.jpg) |
| #1884 | G86 2026/0516 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0516/041.jpg) |
| #2155 | G92 2026/0807 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0807/003.jpg) |
| #2177 | G92 2026/0807 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0807/025.jpg) |
| #2199 | G92 2026/0807 | 2800×1752 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/0807/047.jpg) |
| #2336 | G95 2026/1009 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/1009/0018.png) |
| #2337 | G95 2026/1009 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/1009/0019.png) |
| #2338 | G95 2026/1009 | 2305×1297 | 整幅图像 | [来源](https://cdn.ignoredone.cn/arknightsdesign/2026/1009/0020.png) |

## 全部资源组覆盖

每组的图片均已纳入编号联系表和总览记录。下面用于定位，不表示每组都适合作为产品主题。

| 组号 | 年份/系列 | 图片数 | 图片编号范围 | 来源 |
|---|---|---|---|---|
| G00 | 2019/0527 | 14 | #0000–#0013 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/0527) |
| G01 | 2019/0702 | 15 | #0014–#0028 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/0702) |
| G02 | 2019/0821 | 29 | #0029–#0057 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/0821) |
| G03 | 2019/1011 | 13 | #0058–#0070 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/1011) |
| G04 | 2019/1114 | 12 | #0071–#0082 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/1114) |
| G05 | 2019/1220 | 9 | #0083–#0091 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2019/1220) |
| G06 | 2020/0104 | 34 | #0092–#0125 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0104) |
| G07 | 2020/0414 | 7 | #0126–#0132 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0414) |
| G08 | 2020/0501 | 19 | #0133–#0151 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0501) |
| G09 | 2020/0612 | 19 | #0152–#0170 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0612) |
| G10 | 2020/0703 | 22 | #0171–#0192 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0703) |
| G11 | 2020/0820 | 18 | #0193–#0210 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0820) |
| G12 | 2020/0917 | 7 | #0211–#0217 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/0917) |
| G13 | 2020/1009 | 10 | #0218–#0227 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/1009) |
| G14 | 2020/1025 | 15 | #0228–#0242 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/1025) |
| G15 | 2020/1210 | 9 | #0243–#0251 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2020/1210) |
| G16 | 2021/0105 | 6 | #0252–#0257 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0105) |
| G17 | 2021/0128 | 10 | #0258–#0267 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0128) |
| G18 | 2021/0302 | 10 | #0268–#0277 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0302) |
| G19 | 2021/0410 | 7 | #0278–#0284 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0410) |
| G20 | 2021/0501 | 11 | #0285–#0295 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0501) |
| G21 | 2021/0526 | 6 | #0296–#0301 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0526) |
| G22 | 2021/0628 | 3 | #0302–#0304 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0628) |
| G23 | 2021/0725 | 18 | #0305–#0322 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0725) |
| G24 | 2021/0910 | 6 | #0323–#0328 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/0910) |
| G25 | 2021/1011 | 7 | #0329–#0335 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/1011) |
| G26 | 2021/1024 | 17 | #0336–#0352 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/1024) |
| G27 | 2021/1214 | 10 | #0353–#0362 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2021/1214) |
| G28 | 2022/0115 | 13 | #0363–#0375 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0115) |
| G29 | 2022/0208 | 7 | #0376–#0382 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0208) |
| G30 | 2022/0309 | 6 | #0383–#0388 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0309) |
| G31 | 2022/0501 | 19 | #0389–#0407 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0501) |
| G32 | 2022/0602 | 8 | #0408–#0415 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0602) |
| G33 | 2022/0629 | 7 | #0416–#0422 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0629) |
| G34 | 2022/0806 | 14 | #0423–#0436 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0806) |
| G35 | 2022/0902 | 14 | #0437–#0450 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0902) |
| G36 | 2022/0923 | 27 | #0451–#0477 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/0923) |
| G37 | 2022/1023 | 12 | #0478–#0489 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/1023) |
| G38 | 2022/1208 | 11 | #0490–#0500 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2022/1208) |
| G39 | 2023/0108 | 7 | #0501–#0507 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0108) |
| G40 | 2023/0207 | 3 | #0508–#0510 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0207) |
| G41 | 2023/0303 | 6 | #0511–#0516 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0303) |
| G42 | 2023/0501 | 19 | #0517–#0535 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0501) |
| G43 | 2023/0602 | 15 | #0536–#0550 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0602) |
| G44 | 2023/0630 | 8 | #0551–#0558 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0630) |
| G45 | 2023/0711 | 11 | #0559–#0569 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0711) |
| G46 | 2023/0723 | 17 | #0570–#0586 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0723) |
| G47 | 2023/0901 | 7 | #0587–#0593 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/0901) |
| G48 | 2023/1002 | 3 | #0594–#0596 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/1002) |
| G49 | 2023/1022 | 17 | #0597–#0613 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/1022) |
| G50 | 2023/1129 | 19 | #0614–#0632 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2023/1129) |
| G51 | 2024/0123 | 17 | #0633–#0649 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0123) |
| G52 | 2024/0127 | 20 | #0650–#0669 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0127) |
| G53 | 2024/0229 | 8 | #0670–#0677 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0229) |
| G54 | 2024/0405 | 16 | #0678–#0693 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0405) |
| G55 | 2024/0501 | 5 | #0694–#0698 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0501) |
| G56 | 2024/0511 | 10 | #0699–#0708 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0511) |
| G57 | 2024/0529 | 8 | #0709–#0716 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0529) |
| G58 | 2024/0703 | 12 | #0717–#0728 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0703) |
| G59 | 2024/0714 | 33 | #0729–#0761 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0714) |
| G60 | 2024/0727 | 20 | #0762–#0781 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0727) |
| G61 | 2024/0828 | 23 | #0782–#0804 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0828) |
| G62 | 2024/0926 | 18 | #0805–#0822 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/0926) |
| G63 | 2024/1002 | 13 | #0823–#0835 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/1002) |
| G64 | 2024/1101 | 30 | #0836–#0865 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/1101) |
| G65 | 2024/1130 | 25 | #0866–#0890 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/1130) |
| G66 | 2024/1225 | 28 | #0891–#0918 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2024/1225) |
| G67 | 2025/0118 | 26 | #0919–#0944 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0118) |
| G68 | 2025/0209 | 16 | #0945–#0960 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0209) |
| G69 | 2025/0301 | 24 | #0961–#0984 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0301) |
| G70 | 2025/0317 | 62 | #0985–#1046 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0317) |
| G71 | 2025/0403 | 27 | #1047–#1073 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0403) |
| G72 | 2025/0501 | 71 | #1074–#1144 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0501) |
| G73 | 2025/0530 | 29 | #1145–#1173 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0530) |
| G74 | 2025/0706 | 25 | #1174–#1198 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0706) |
| G75 | 2025/0715 | 146 | #1199–#1344 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0715) |
| G76 | 2025/0802 | 50 | #1345–#1394 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0802) |
| G77 | 2025/0904 | 82 | #1395–#1476 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/0904) |
| G78 | 2025/1021 | 40 | #1477–#1516 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/1021) |
| G79 | 2025/1115 | 112 | #1517–#1628 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/1115) |
| G80 | 2025/1224 | 48 | #1629–#1676 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2025/1224) |
| G81 | 2026/0109 | 26 | #1677–#1702 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0109) |
| G82 | 2026/0210 | 53 | #1703–#1755 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0210) |
| G83 | 2026/0305 | 17 | #1756–#1772 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0305) |
| G84 | 2026/0408 | 29 | #1773–#1801 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0408) |
| G85 | 2026/0501 | 43 | #1802–#1844 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0501) |
| G86 | 2026/0516 | 81 | #1845–#1925 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0516) |
| G87 | 2026/0526 | 32 | #1926–#1957 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0526) |
| G88 | 2026/0610 | 21 | #1958–#1978 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0610) |
| G89 | 2026/0705 | 21 | #1979–#1999 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0705) |
| G90 | 2026/0712 | 74 | #2000–#2073 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0712) |
| G91 | 2026/0801 | 79 | #2074–#2152 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0801) |
| G92 | 2026/0807 | 63 | #2153–#2215 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0807) |
| G93 | 2026/0904 | 65 | #2216–#2280 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0904) |
| G94 | 2026/0920 | 37 | #2281–#2317 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/0920) |
| G95 | 2026/1009 | 40 | #2318–#2357 | [资源组](https://www.ignoredone.space/index.php/arknights_design/?path=arknightsdesign/2026/1009) |
