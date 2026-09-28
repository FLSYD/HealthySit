# HealthySit - 智能坐姿监测系统

基于计算机视觉的久坐行为与健康坐姿分析系统

---

## 项目简介

本系统利用 Google 开源的 MediaPipe 视觉框架，通过普通摄像头实时捕捉用户画面，分析人体骨骼关键点（耳朵、肩膀、臀部），自动识别 **头部前倾**、**头部侧倾**、**弯腰驼背**、**肩膀倾斜** 四种常见不良坐姿，结合久坐提醒、数据记录和趋势分析，帮助用户养成健康的坐姿习惯。

---

## 功能特点

- **四种姿态检测**：头部前倾 / 头部侧倾 / 弯腰驼背 / 肩膀倾斜
- **正坐/侧坐自适应**：根据肩宽自动识别正坐与侧坐视角，切换对应检测模式
- **久坐提醒**：可自定义提醒间隔，到时弹出通知并播放系统提示音
- **实时骨骼可视化**：可选叠加骨骼点与连线，实时了解检测状态
- **会话数据记录**：SQLite 本地存储，自动汇总每次监测的坐姿评分与时长
- **健康趋势分析**：折线图展示最近 10 次会话评分变化

- **CSV 数据导出**：支持导出单个会话或者全部会话为 CSV 文件
- **历史会话管理**：支持查看、删除历史会话

---

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11（推荐） |
| Python | 3.10（当前测试与打包版本） |
| 摄像头 | 普通高清摄像头（推荐 720p 及以上） |
| 内存 | 4 GB 以上 |
| 磁盘 | 1 GB 以上可用空间 |

---

## 快速开始

### 1. 获取源码并创建虚拟环境

源码开发请使用纯英文目录，例如 `C:\Projects\HealthySit`。MediaPipe 的原生模型加载器不能正确读取某些中文路径；打包后的 EXE 已自动使用英文运行缓存。

```powershell
git clone https://github.com/FLSYD/HealthySit.git
cd HealthySit
py -3.10 -m venv .venv
```

### 2. 安装依赖

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

依赖文件锁定了已验证的主要版本。`opencv-contrib-python` 已包含 `cv2`，无需另外安装 `opencv-python`。

### 3. 启动程序

```powershell
.\.venv\Scripts\python.exe main.py
```

---

## 使用指南

### 主界面

| 区域 | 说明 |
|------|------|
| 左侧预览区 | 实时摄像头画面，可叠加骨骼点可视化 |
| 右侧状态区 | 坐姿状态、4 项角度数据、久坐时长、违规次数 |
| 底部控制栏 | 开始/暂停/结束监测、重置统计、健康历史、系统设置 |

### 操作流程

1. **开始监测** — 点击绿色按钮启动摄像头和姿态检测
2. **实时调整** — 系统实时分析坐姿，异常时状态文字变为红色/橙色警告
3. **结束监测** — 点击结束，会话自动保存到数据库并计算本次坐姿评分
4. **查看历史** — 打开健康历史窗口，查看趋势图、会话列表，支持一键导出所有会话
5. **参数设置** — 调整各角度阈值、久坐提醒间隔、声音开关、骨骼点显示

---

## 参数说明

| 参数 | 范围 | 默认值 | 说明 |
|------|------|--------|------|
| 头部侧倾阈值 | 5° ~ 25° | 15° | 耳朵连线与水平线夹角超过此值触发（正坐模式） |
| 肩膀倾斜阈值 | 5° ~ 25° | 15° | 两肩高度差超过此值触发（正坐模式） |
| 头部前倾阈值 | 10° ~ 30° | 20° | 头部前倾角超过此值触发（侧坐模式） |
| 躯干倾斜阈值 | 5° ~ 25° | 15° | 躯干与垂直线夹角超过此值触发（侧坐模式） |
| 久坐提醒间隔 | 0 ~ 120 分钟 | 60 分钟 | 设为 0 则关闭久坐提醒 |
| 久坐提醒次数 | 0 ~ 不限制 | 1 次 | 超过提醒次数后停止提醒 |
| 显示骨骼点 | 开/关 | 开 | 实时显示检测到的骨骼线与关键点 |
| 声音提醒 | 开/关 | 开 | 久坐提醒时播放 Windows 系统提示音 |

---

## 算法原理

### 骨骼关键点

使用 MediaPipe Pose 模型（33 个关键点），重点依赖以下 7 个点：

| 编号 | 名称 | 用途 |
|------|------|------|
| 7 | 左耳 | 侧坐/正坐关键点 |
| 8 | 右耳 | 侧坐/正坐关键点 |
| 11 | 左肩 | 躯干/肩膀基准点 |
| 12 | 右肩 | 躯干/肩膀基准点 |
| 23 | 左髋 | 侧坐躯干基准点 |
| 24 | 右髋 | 侧坐躯干基准点 |

### 正坐 / 侧坐自动识别

```
肩宽 = |右肩x - 左肩x|
肩宽 > 100 px → 正坐模式（检测：头部侧倾、肩膀倾斜）
肩宽 ≤ 100 px → 侧坐模式（检测：头部前倾、弯腰驼背）
```
需连续 5 帧肩宽稳定才会切换模式，防止频繁抖动。

### 四种角度计算

| 角度 | 计算方式 | 判定规则 |
|------|---------|---------|
| 头部侧倾角 | atan2(左耳y - 右耳y, 左耳x - 右耳x)，转为锐角 | 角度 > 阈值 |
| 肩膀倾斜角 | atan2(右肩y - 左肩y, 右肩x - 左肩x)，转为锐角 | 角度 > 阈值 |
| 头部前倾角（侧坐） | atan2(近耳x - 近肩x, 近肩y - 近耳y)，转为锐角（近侧耳→近侧肩与垂直方向夹角） | 角度 > 阈值 |
| 躯干倾斜角（侧坐） | atan2(近髋x - 近肩x, 近肩y - 近髋y)，转为锐角（近侧肩→近侧髋与垂直方向夹角） | 角度 > 阈值 |

### 坐姿评分算法

```
违规率 = 违规时长 / 总时长
评分 = max(0, 100 - 违规率 × 80)
```

| 评分范围 | 等级 |
|---------|------|
| ≥ 90 分 | 优秀 |
| 75 ~ 89 分 | 良好 |
| 60 ~ 74 分 | 一般 |
| 40 ~ 59 分 | 较差 |
| < 40 分 | 差 |

---

## 数据说明

### 数据库（SQLite）

数据库文件位于 `data/posture.db`：源码运行时在项目目录，打包运行时在原始 EXE 旁；英文运行缓存不保存用户数据。数据库启用 WAL 模式、busy_timeout=20s、synchronous=NORMAL 以支持并发安全写入。`SCHEMA_VERSION = 3`，数据库初始化时写入 `meta` 表进行版本管理。共包含以下 **6 张表**：

**1. `sessions` — 每次监测会话记录**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `start_time` | TEXT NOT NULL | 会话开始时间（ISO 8601） |
| `end_time` | TEXT | 会话结束时间（ISO 8601） |
| `total_duration` | INTEGER | 总时长（秒） |
| `total_violations` | INTEGER | 违规次数 |
| `normal_duration` | INTEGER | 正常时长（秒） |
| `violation_duration` | INTEGER | 违规时长（秒） |
| `posture_score` | REAL | 坐姿评分 0~100（默认 100.0） |
| `posture_level` | TEXT | 等级枚举：excellent/good/fair/poor/bad |
| `avg_neck_angle` | REAL | 平均头部侧倾角（°） |
| `avg_torso_angle` | REAL | 平均躯干倾斜角（°） |
| `avg_head_forward_angle` | REAL | 平均头部前倾角（°） |
| `avg_shoulder_diff` | REAL | 平均肩膀倾斜角（°） |
| `sitting_view` | TEXT | 坐姿视角：front/side（默认 front） |
| `status` | TEXT | 会话状态：active/completed/cancelled（默认 active） |
| `notes` | TEXT | 备注（可选） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

**2. `daily_stats` — 每日健康统计**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `date` | TEXT UNIQUE NOT NULL | 日期（YYYY-MM-DD） |
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

> 由 `end_session()` 触发，UPSERT 写入该日统计。

**3. `violation_log` — 违规事件明细**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `session_id` | INTEGER | 关联的会话 ID（无外键约束） |
| `timestamp` | TEXT NOT NULL | 违规发生时间（ISO 8601） |
| `violation_type` | TEXT NOT NULL | 违规类型：hunchback/head_forward/head_tilt/shoulder_tilt |
| `violation_value` | REAL | 实际测量值（°） |
| `threshold_value` | REAL | 触发阈值（°） |
| `duration_seconds` | INTEGER | 持续时长（秒，默认 0） |
| `status` | TEXT | 状态：active/resolved（默认 active） |
| `resolved_at` | TEXT | 解决时间（ISO 8601） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

**4. `health_reports` — 健康报告（周报/月报快照）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `report_date` | TEXT NOT NULL | 报告生成日期（YYYY-MM-DD） |
| `report_type` | TEXT NOT NULL | 报告类型：daily/weekly/monthly |
| `start_date` | TEXT NOT NULL | 报告覆盖起始日期 |
| `end_date` | TEXT NOT NULL | 报告覆盖结束日期 |
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

> 由 `generate_health_report()` 写入，存储周期快照便于历史查阅。

**5. `settings_log` — 设置变更日志**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER PRIMARY KEY | 自增 ID |
| `timestamp` | TEXT NOT NULL | 变更时间（ISO 8601） |
| `setting_key` | TEXT NOT NULL | 设置项键名 |
| `old_value` | TEXT | 变更前值 |
| `new_value` | TEXT | 变更后值 |
| `notes` | TEXT | 备注（可选） |
| `created_at` | TEXT | 创建时间（默认 CURRENT_TIMESTAMP） |

> 记录参数调整历史，便于追踪用户配置演变。

**6. `meta` — 数据库元数据**

| 字段 | 类型 | 说明 |
|------|------|------|
| `key` | TEXT PRIMARY KEY | 元数据键名 |
| `value` | TEXT | 元数据值 |
| `updated_at` | TEXT | 更新时间（默认 CURRENT_TIMESTAMP） |

> 当前存储 `schema_version = 3` 用于版本管理。

### CSV 导出格式

导出的 CSV 文件包含以下 12 个字段（UTF-8-BOM 编码）：

```
开始时间, 结束时间, 总时长(秒), 违规次数, 正常时长(秒),
违规时长(秒), 坐姿评分, 坐姿等级, 头部侧倾(°),
肩膀倾斜(°), 头部前倾(°), 躯干倾斜(°)
```

---

## 项目结构

```
HealthySit/
├── main.py                  # 主程序入口
├── requirements.txt         # Python 依赖
├── requirements-dev.txt     # 开发与打包依赖
├── healthy_sit.spec         # Windows 打包配置
├── SPEC.md                  # 项目技术规范
├── README.md                # 本文件
│
├── src/                     # 核心业务模块
│   ├── __init__.py
│   ├── pose_detector.py     # MediaPipe 姿态检测封装
│   ├── posture_analyzer.py   # 坐姿分析与判定逻辑
│   ├── data_manager.py      # SQLite 数据库 + CSV 导出
│   ├── runtime.py           # 英文运行缓存与数据路径
│   └── audio_manager.py     # Windows 系统提示音播放
│
├── ui/                      # Tkinter 界面模块
│   ├── __init__.py
│   ├── main_window.py       # 主窗口（1200×780）
│   ├── camera_preview.py     # 摄像头预览组件（640×480）
│   ├── status_panel.py      # 状态面板（角度/久坐/违规）
│   ├── control_panel.py      # 控制按钮面板
│   ├── settings_dialog.py    # 参数设置对话框
│   └── history_viewer.py    # 健康历史查看器（含趋势图）
│
├── hooks/                   # PyInstaller 打包钩子
│   └── hook-PIL.py          # 强制打包 PIL 所有 Python 模块
│
├── assets/                  # 资源文件
│   └── sounds/              # 音效文件目录（预留）
│
├── data/                    # 数据存储目录
│   └── posture.db           # SQLite 数据库（自动创建）
│
├── logs/                    # 日志目录
│   └── healthysit.log       # 应用运行日志
│
├── tests/                   # 自动化回归测试
├── scripts/verify_app.py    # 真实界面与合成帧模型验收
└── .venv/                   # Python 虚拟环境（本地，不上传）
```

---

## 注意事项

1. **摄像头位置**：建议放置在与面部平齐或稍高的位置，正对用户
2. **光照条件**：避免强烈背光或过暗环境，光线均匀为佳
3. **遮挡问题**：尽量保持肩膀和颈部不被衣物遮挡
4. **单人场景**：目前仅支持单人检测，多人场景可能导致误检
5. **隐私保护**：所有数据均存储在本地，不会上传至任何服务器
6. **声音提醒**：使用 Windows 系统提示音，无需额外音频文件

---

## 常见问题

**Q: 摄像头无法打开？**
> 请检查摄像头是否被其他程序占用，或尝试重新连接摄像头。

**Q: 检测效果不理想？**
> 尝试调高光线、调整摄像头角度，或在"设置"中调整各角度阈值。

**Q: 误检率较高？**
> 适当调高各阈值参数，或确保在光线充足、摄像头正对用户的环境下使用。

**Q: 声音没有声音？**
> 确认"设置"中声音提醒已开启，Windows 系统音量未静音。

---

## 开发者参考

### 运行测试

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\verify_app.py --gui --model
```

单元测试使用临时数据库、模拟时钟和模拟摄像头。界面验收会创建并关闭 Tk 窗口，模型验收使用合成空白帧；两者都不打开摄像头、不读取个人历史数据。真实摄像头权限、画面质量和人体识别效果需要在目标设备上手动检查。

GitHub Actions 会在 Windows / Python 3.10 上自动执行测试、真实界面与模型验收，并生成可下载的 `HealthySit-Windows` 构建产物。

### 打包 Windows 应用

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --distpath build\release healthy_sit.spec
```

程序生成于 `build\release\HealthySit\HealthySit.exe`，分发时需保留整个 `HealthySit` 文件夹。打包配置不包含本地 `data`、`logs`；首次运行时自动创建。更新已有安装时保留它的 `data` 文件夹，再替换 EXE 和 `_internal`。

如果打包日志出现 `tkinter installation is broken`，先在正常桌面终端执行 `python -c "import tkinter; tkinter.Tcl()"` 检查：受限执行环境可能导致探测失败，不应继续发布缺少 Tk 的构建。

### 上传范围

仓库只保存源码、测试、资源与文档。`.gitignore` 排除了本地数据库、日志、虚拟环境、IDE 配置、构建缓存和 EXE；应用程序可从 Actions 构建产物获得。

### 查看日志

```bash
# Windows PowerShell
Get-Content logs\healthysit.log -Tail 50 -Wait
```

### 查看数据库

```bash
sqlite3 data\posture.db ".tables"
sqlite3 data\posture.db "SELECT id, start_time, posture_score, posture_level FROM sessions ORDER BY id DESC LIMIT 5;"
sqlite3 data\posture.db "SELECT key, value, updated_at FROM meta;"
```

---

## 版本历史

| 版本 | 日期 | 更新内容 |
|------|------|---------|
| **v2.0** | 2026-05-14 | 正式版完成，支持四种姿态检测、健康历史查看器、趋势图、会话导出 |
| **v1.0** | 2026-05-07 | 初始版本，基础姿态检测与数据记录 |

---

## 许可

MIT License
