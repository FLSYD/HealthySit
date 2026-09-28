# HealthySit - 智能坐姿监测系统 · 技术规范

## 1. 项目概述

**项目名称**: HealthySit - 智能坐姿监测系统

**项目类型**: Python 桌面应用程序（基于 Tkinter）

**核心功能概述**: 利用计算机视觉技术，通过普通摄像头实时捕捉用户画面，分析人体骨骼关键点，检测久坐行为和四种不良坐姿（头部前倾、头部侧倾、弯腰驼背、肩膀倾斜），并提供可视化提醒与数据记录。

**目标用户**: 程序员、学生、办公室工作者等长期伏案人群。

---

## 2. 技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| 编程语言 | Python 3.10 | 当前测试与打包版本 |
| 姿态检测 | MediaPipe Pose (Google 开源) | 33 个骨骼关键点 |
| 图像处理 | OpenCV | 摄像头读取与骨骼绘制 |
| GUI 框架 | Tkinter | Python 标准库，无需额外安装 |
| 图表绘制 | Matplotlib + SciPy | 趋势折线图平滑曲线 |
| 数据存储 | SQLite + CSV | 本地持久化 |
| 数学计算 | NumPy | 角度计算 |
| 音频 | winsound (Windows 标准库) | 系统提示音 |

---

## 3. UI/UX 规格

### 3.1 布局结构

**主窗口**: 1200×780 像素，固定大小

```
┌──────────────────────────────────────────────────────────────────┐
│  标题栏: HealthySit - 智能坐姿监测系统  [×]                        │
├────────────────────────────────────────────┬─────────────────────┤
│                                            │   坐姿状态（大字）    │
│                                            │   ─────────────     │
│           实时摄像头预览                    │   头部侧倾   --      │
│           (640×480 Canvas)                 │   肩膀倾斜   --      │
│           + 骨骼叠加可视化                  │   头部前倾   --      │
│                                            │   躯干倾斜   --      │
│                                            │   ─────────────     │
│                                            │   久坐时间  00:00:00 │
│                                            │   违规次数     0     │
├────────────────────────────────────────────┴─────────────────────┤
│  [开始监测] [结束监测] [重置统计] | [健康历史] [系统设置]           │
├──────────────────────────────────────────────────────────────────┤
│  状态栏: 就绪 | 摄像头: 已连接 | FPS: 30                           │
└──────────────────────────────────────────────────────────────────┘
```

**历史查看器窗口**: 1000×660 像素，固定大小，模态弹窗
**设置窗口**: 400×640 像素，固定大小，模态弹窗
**会话详情弹窗**: 540×540 像素，居中显示

### 3.2 视觉设计

**配色方案**:

| 用途 | 色值 | 说明 |
|------|------|------|
| 主色调 | `#1E3A5F` | 深蓝色，标题栏背景 |
| 强调色 | `#00D084` | 健康绿，正常状态 |
| 警告色 | `#FF9F43` | 橙色，次要警告 |
| 危险色 | `#FF4757` | 红色，严重警告 |
| 背景色 | `#F5F7FA` | 浅灰白，页面背景 |
| 卡片色 | `#FFFFFF` | 白色，卡片背景 |
| 文字色 | `#2C3E50` | 深灰，主要文字 |
| 次要文字 | `#8A9BB0` | 浅灰，次要说明 |
| 边框色 | `#E0E6ED` | 边框线颜色 |

**字体**: Microsoft YaHei（系统内置，无需额外安装）

**间距系统**:
- 窗口内边距: 16px
- 组件间距: 12px
- 区域间距: 24px

**视觉效果**:
- 卡片式布局（白底卡片 + 轻微圆角）
- 按钮 hover 颜色加深效果
- 状态变化颜色即时响应

### 3.3 组件规格

**摄像头预览区**:
- 画布尺寸: 640×480 像素
- 暂停状态: 半透明深色遮罩 + 暂停图标
- 骨骼叠加: 正坐显示两耳两肩四点四线，侧坐显示耳→肩→髋三点两线

**状态面板**:
- 坐姿状态: 20px 加粗，根据等级显示绿/橙/红色
- 视角指示: 带颜色圆点的标签（正坐模式/侧坐模式/等待监测）
- 角度数据: 4 行，异常时文字变为警告色
- 久坐计时: HH:MM:SS 格式，
- 违规计数: 红色数字

**控制按钮**:
- 开始监测（绿色）→ 暂停监测（橙色）→ 继续监测（绿色）
- 结束监测（红色，仅监测中可点击）
- 重置统计（灰色，需二次确认）
- 健康历史（紫色）
- 系统设置（灰色）

**历史查看器**:
- 摘要卡片: 4 项统计数据
- 趋势图: 最近 10 次会话评分折线图，空数据时居中提示文字
- 会话列表: 颜色编码卡片列表（优秀=绿/良好=蓝/一般=黄/较差=橙/差=红）
- 会话详情弹窗: 大字评分 + 统计数据 + 4 项平均角度 + 操作按钮
- 操作栏: 导出全部 / 清除历史 / 关闭

---

## 4. 功能规格

### 4.1 姿态检测模块

**检测目标**: MediaPipe Pose 33 个人体关键点（如图2-1所示），重点使用 6 个：

| 编号 | 名称 | 用途 |
|------|------|------|
| 7 | 左耳 (LEFT_EAR) | 侧坐/正坐关键点 |
| 8 | 右耳 (RIGHT_EAR) | 侧坐/正坐关键点 |
| 11 | 左肩 (LEFT_SHOULDER) | 躯干/肩膀基准点 |
| 12 | 右肩 (RIGHT_SHOULDER) | 躯干/肩膀基准点 |
| 23 | 左髋 (LEFT_HIP) | 侧坐躯干基准点 |
| 24 | 右髋 (RIGHT_HIP) | 侧坐躯干基准点 |

**正坐/侧坐自动识别**:

```
肩宽 = |右肩x - 左肩x| / 图像宽度 × 1000（归一化）
肩宽 > 100 → 正坐模式（检测：头部侧倾、肩膀倾斜）
肩宽 ≤ 100 → 侧坐模式（检测：头部前倾、弯腰驼背）
```
需连续 5 帧稳定才切换模式，防止频繁抖动。

**关键角度计算**:

1. **头部侧倾角** (Head Tilt Angle) — 正坐模式
   - 公式: `atan2(左耳y - 右耳y, 左耳x - 右耳x)`，转为锐角（0°~90°）
   - 默认阈值: **15°**

2. **肩膀倾斜角** (Shoulder Tilt Angle) — 正坐模式
   - 公式: `atan2(右肩y - 左肩y, 右肩x - 左肩x)`，转为锐角（0°~90°）
   - 默认阈值: **15°**

3. **头部前倾角** (Head Forward Angle) — 侧坐模式
   - 公式: `atan2(近耳x - 近肩x, 近肩y - 近耳y)`，转为锐角（近侧耳→近侧肩与垂直方向夹角）
   - 默认阈值: **20°**

4. **躯干倾斜角** (Torso Angle) — 侧坐模式
   - 公式: `atan2(近髋x - 近肩x, 近肩y - 近髋y)`，转为锐角（近侧肩→近侧髋与垂直方向夹角）
   - 默认阈值: **15°**

### 4.2 坐姿判定逻辑

**判定规则**: 角度超过阈值且持续 3 帧以上才触发违规，防止偶发误检。

**判定优先级**:
- 侧坐模式: 躯干倾斜 > 头部前倾
- 正坐模式: 头部侧倾 > 肩膀倾斜

**久坐检测**:
- 默认阈值: 连续坐姿 60 分钟
- 设为 0 则关闭久坐提醒
- 提醒次数: 0=不提醒，1~10=指定次数，11=不限制

### 4.3 提醒机制

**视觉提醒**:
- 状态文字颜色变化（绿色=正常，橙色=轻微警告，红色=严重违规）
- 状态栏实时提示信息

**声音提醒**:
- 使用 Windows 系统提示音（`winsound.MessageBeep`）
- 可在设置中开关，默认开启
- 提醒冷却时间: 5 秒（防止重复触发）

### 4.4 数据管理

**本地存储 (SQLite)**: 数据库文件 `data/posture.db`，WAL 模式，busy_timeout=20s，synchronous=NORMAL。`SCHEMA_VERSION = 3`，由 `meta` 表统一管理版本。共 **6 张表**，覆盖会话、统计、违规、报告、配置日志、元数据等完整数据生命周期。

**sessions — 会话记录表**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `start_time` | TEXT | ISO 8601 格式，开始时间 |
| `end_time` | TEXT | ISO 8601 格式，结束时间 |
| `total_duration` | INTEGER | 总时长（秒） |
| `total_violations` | INTEGER | 违规次数 |
| `normal_duration` | INTEGER | 正常时长（秒） |
| `violation_duration` | INTEGER | 违规时长（秒） |
| `posture_score` | REAL | 坐姿评分 0~100（默认 100.0） |
| `posture_level` | TEXT | excellent/good/fair/poor/bad |
| `avg_neck_angle` | REAL | 平均头部侧倾角（°） |
| `avg_torso_angle` | REAL | 平均躯干倾斜角（°） |
| `avg_head_forward_angle` | REAL | 平均头部前倾角（°） |
| `avg_shoulder_diff` | REAL | 平均肩膀倾斜角（°） |
| `sitting_view` | TEXT | front/side（默认 front） |
| `status` | TEXT | active/completed/cancelled（默认 active） |
| `notes` | TEXT | 备注（可选） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

**daily_stats — 每日统计表**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `date` | TEXT UNIQUE | 日期（YYYY-MM-DD） |
| `total_sitting_time` | INTEGER | 当日累计坐姿时长（秒） |
| `total_violations` | INTEGER | 当日累计违规次数 |
| `total_sessions` | INTEGER | 当日总会话数 |
| `avg_posture_score` | REAL | 当日平均坐姿评分（默认 100.0） |
| `posture_level` | TEXT | 当日综合坐姿等级 |
| `normal_time` | INTEGER | 当日累计正常时长（秒） |
| `violation_time` | INTEGER | 当日累计违规时长（秒） |
| `excellent_sessions` | INTEGER | 优秀会话数（≥90 分） |
| `good_sessions` | INTEGER | 良好会话数（75~89 分） |
| `fair_sessions` | INTEGER | 一般会话数（60~74 分） |
| `poor_sessions` | INTEGER | 较差会话数（40~59 分） |
| `bad_sessions` | INTEGER | 差会话数（<40 分） |
| `notes` | TEXT | 备注（可选） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

> 会话结束（`end_session()`）时自动 UPSERT 写入。

**violation_log — 违规日志表**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `session_id` | INTEGER | 关联的会话 ID（无外键约束） |
| `timestamp` | TEXT | ISO 8601 格式，违规发生时间 |
| `violation_type` | TEXT | hunchback/head_forward/head_tilt/shoulder_tilt |
| `violation_value` | REAL | 实际测量值（°） |
| `threshold_value` | REAL | 触发阈值（°） |
| `duration_seconds` | INTEGER | 持续时长（秒，默认 0） |
| `status` | TEXT | active/resolved（默认 active） |
| `resolved_at` | TEXT | 解决时间（ISO 8601） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

**health_reports — 健康报告表（周报/月报快照）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `report_date` | TEXT | 报告生成日期（YYYY-MM-DD） |
| `report_type` | TEXT | daily/weekly/monthly |
| `start_date` | TEXT | 报告覆盖起始日期 |
| `end_date` | TEXT | 报告覆盖结束日期 |
| `total_sitting_time` | INTEGER | 周期内总坐姿时长（秒） |
| `total_violations` | INTEGER | 周期内总违规次数 |
| `total_sessions` | INTEGER | 周期内总会话数 |
| `avg_posture_score` | REAL | 周期内平均坐姿评分（默认 100.0） |
| `posture_level` | TEXT | 周期综合坐姿等级 |
| `normal_time` | INTEGER | 周期内累计正常时长（秒） |
| `violation_time` | INTEGER | 周期内累计违规时长（秒） |
| `daily_breakdown` | TEXT | 每日明细 JSON 字符串 |
| `violation_breakdown` | TEXT | 违规类型分布 JSON 字符串 |
| `recommendations` | TEXT | 健康建议 JSON 字符串 |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

> 由 `generate_health_report()` 写入，存储周期快照便于历史查阅与对比。

**settings_log — 设置变更日志表**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `timestamp` | TEXT | 变更时间（ISO 8601） |
| `setting_key` | TEXT | 设置项键名（如 `head_tilt_threshold`） |
| `old_value` | TEXT | 变更前值 |
| `new_value` | TEXT | 变更后值 |
| `notes` | TEXT | 备注（可选） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

> 记录参数调整历史，便于追踪用户配置演变。

**meta — 数据库元数据表**

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | TEXT PRIMARY KEY | 元数据键名 |
| `value` | TEXT | 元数据值 |
| `updated_at` | TEXT | 更新时间（默认 CURRENT_TIMESTAMP） |

> 当前存储 `schema_version = 3`，由 `INSERT OR REPLACE` 维护，供未来数据库迁移使用。

**会话生命周期**:
1. `start_session()` — 创建 active 会话
2. 实时更新会话状态（违规计数、久坐时长），监测结束时 `end_session()` 自动计算评分和等级，更新 `daily_stats`
3. 支持 `cancel_session()` 取消会话（不计入统计）

**坐姿评分算法**:
```
violation_rate = violation_duration / total_duration
posture_score = max(0.0, 100.0 - violation_rate × 80.0)
```

| 评分 | 等级 |
|------|------|
| ≥90 分 | 优秀 (excellent) |
| 75~89 分 | 良好 (good) |
| 60~74 分 | 一般 (fair) |
| 40~59 分 | 较差 (poor) |
| <40 分 | 差 (bad) |

**CSV 导出**（UTF-8-BOM 编码）:

| 导出类型 | 内容 | 字段 |
|---------|------|------|
| sessions | 所有已完成会话 | 开始时间、结束时间、总时长、违规次数、正常时长、违规时长、坐姿评分、坐姿等级、4项平均角度 |
| daily | 每日统计 | 日期、总时长、总违规、会话数、平均评分、坐姿等级、正常时长、违规时长、5级会话计数 |
| violations | 违规事件 | 时间、会话ID、违规类型、实际值、阈值、持续秒数、状态 |
| 单会话 | 指定会话详情 | 同 sessions，每字段一行 |

### 4.5 设置选项

| 参数 | 范围 | 默认值 | 说明 |
|------|------|--------|------|
| 头部侧倾阈值 | 5°~25° | 15° | 头部侧倾角超过此值触发 |
| 肩膀倾斜阈值 | 5°~25° | 15° | 两肩高度差超过此值触发 |
| 头部前倾阈值 | 10°~30° | 20° | 头部前倾角超过此值触发（侧坐模式） |
| 躯干倾斜阈值 | 5°~25° | 15° | 躯干倾斜角超过此值触发 |
| 久坐提醒间隔 | 0~120 分钟 | 60 分钟 | 设为 0 则关闭久坐提醒 |
| 久坐提醒次数 | 0~不限制 | 1 次 | 超过此次数后停止提醒 |
| 骨骼点显示 | 开关 | 开 | 实时显示骨骼线与关键点 |
| 声音提醒 | 开关 | 开 | 异常时播放系统提示音 |

---

## 5. PyInstaller 打包

---

## 6. PyInstaller 打包

### 打包命令

```bash
# 激活虚拟环境
.venv\Scripts\activate

# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller healthy_sit.spec --clean -y
```

打包输出位于 `dist/HealthySit/HealthySit.exe`，包含完整运行时，无需额外安装 Python 或 VC++ 运行库。

### spec 文件关键配置

- `binaries`: 显式包含 System32 中的 VC++ 运行时 DLL（msvcp140\*.dll、vcruntime140\*.dll、concrt140.dll）以及 numpy.libs、scipy.libs 中的 OpenBLAS 动态库
- `hookspath`: 指向 `hooks/` 目录，加载自定义 `hook-PIL.py`
- `hiddenimports`: 包含 PIL._tkinter_finder、matplotlib.backends.backend_tkagg 等标准 hook 容易遗漏的模块

### 已知打包限制

- mediapipe.tasks.vision 不存在于 site-packages，hiddenimports 中不可添加
- 打包前请关闭所有正在运行的 HealthySit.exe，否则 PermissionError 导致 dist 目录无法清理

---

## 6. 验收标准

### 6.1 功能验收

| 编号 | 功能 | 状态 |
|------|------|------|
| F01 | 系统启动后能正常打开主窗口 | ✅ |
| F02 | 摄像头能够正常读取并显示视频流 | ✅ |
| F03 | MediaPipe 能正确检测人体骨骼关键点 | ✅ |
| F04 | 正坐/侧坐自动识别与模式切换 | ✅ |
| F05 | 能正确识别头部前倾姿态（侧坐模式） | ✅ |
| F06 | 能正确识别头部侧倾姿态（正坐模式） | ✅ |
| F07 | 能正确识别弯腰驼背姿态（侧坐模式） | ✅ |
| F08 | 能正确识别肩膀倾斜姿态（正坐模式） | ✅ |
| F09 | 久坐超时能触发提醒 | ✅ |
| F10 | 会话数据能正常保存到 SQLite 数据库 | ✅ |
| F11 | CSV 导出功能正常（sessions/daily/violations） | ✅ |
| F12 | 设置参数能正确应用并持久化 | ✅ |
| F13 | 健康历史查看器正常显示趋势图和会话列表 | ✅ |
| F14 | 坐姿趋势折线图正常渲染（空数据时显示提示） | ✅ |
| F15 | 会话详情弹窗居中显示 | ✅ |

### 6.2 性能要求

| 指标 | 要求 | 状态 |
|------|------|------|
| 视频帧率 | ≥15 FPS | ✅ |
| 姿态检测延迟 | <100ms | ✅ |
| 系统内存占用 | <500MB | ✅ |
| CPU 占用率 | <50%（单核） | ✅ |

### 6.3 用户体验

| 指标 | 要求 | 状态 |
|------|------|------|
| 界面布局 | 清晰美观，卡片式设计 | ✅ |
| 操作响应 | 流畅无卡顿 | ✅ |
| 状态提示 | 直观易懂，颜色编码 | ✅ |
| 窗口交互 | 所有弹窗居中显示 | ✅ |
| 中文显示 | 无乱码方框（字体正确配置） | ✅ |

---

## 7. 已知限制

- 仅支持单人场景检测，多人场景可能导致误检
- 极端光照条件（强背光或过暗）可能影响检测精度
- 侧身或背面姿态检测效果较差
- 需要保持上半身在摄像头视野内
- 无自定义音频文件支持，使用 Windows 系统提示音
