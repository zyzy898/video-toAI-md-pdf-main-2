# 🎬 视频转 Markdown / PDF 智能分析系统

> 一个面向“教程视频 / 操作演示 / 工作流录屏”的全栈项目。  
> 它会在内容安全检测通过后，把视频自动整理成结构化步骤、关键截图、Markdown 文档、PDF、字幕导出和可下载结果包。

当前仓库的主干由三部分组成：

- 🧠 后端 API：`app.py`
- 🎞️ 视频分析核心：`video_analyzer_agent.py`
- 🖥️ 前端工作台：`web-react/`

---

## ✨ 项目能做什么

- 📤 支持单文件上传、批量上传、分片续传上传
- 🔗 支持通过视频链接导入内容，而不只依赖本地文件
- 🛡️ 在上传前和分析前各执行一次内容风控
- 🧾 自动生成 `Markdown`、`PDF`、步骤截图、`steps.json`
- 🗣️ 自动生成字幕，并导出 `SRT / VTT / TXT`
- 🧩 支持标准步骤、候选步骤、时间线摘要三种结果模式
- 🪄 支持对低置信度步骤做“截图视觉增强”
- 📝 支持前端手动编辑步骤后重新生成文档
- 🕘 支持历史记录、结果回看、批量下载 ZIP
- 🧹 支持上传视频 24h 自动清理、历史与输出 72h 自动清理

---

## 🏗️ 技术栈

### 后端

- `Flask`：API 服务
- `Waitress`：生产模式 WSGI 服务
- `python-dotenv`：`.env` 配置加载
- `openai-whisper`：字幕转写
- `ffmpeg-python` + `imageio-ffmpeg`：抽帧、转码、截图
- `markdown` + `fpdf2`：文档与 PDF 生成
- `yt-dlp`：平台播放页下载兜底
- `scrapling`：页面抓取与候选视频地址发现
- `volcengine-python-sdk[ark]`：模型调用客户端

### 前端

- `React 19`
- `TypeScript`
- `Vite`
- `Tailwind CSS 4`
- `motion`
- `marked` + `DOMPurify`

---

## 📁 项目结构

```text
.
├─ app.py                           # Flask 主应用，包含上传、风控、分析、历史、导出等主链路
├─ video_analyzer_agent.py          # Whisper、视频分析、截图、视觉增强、Markdown/PDF 生成
├─ Scrapling_download/              # B站 / 抖音 / 小红书平台链接下载器与共享 LLM 配置
├─ web-react/                       # React + TypeScript 前端工作台
├─ scripts/
│  ├─ check_py_compile.py           # Python 语法编译检查
│  └─ check_mojibake.py             # 文本编码异常检查辅助脚本
├─ risk_keyword_lexicon.json        # 文本风控关键词词库
├─ requirements.txt                 # Python 依赖
├─ updata.md                        # 项目变更记录
├─ uploads/                         # 运行期上传目录
├─ outputs/                         # 运行期输出目录
└─ history.json                     # 历史记录持久化文件
```

---

## 🔄 端到端处理流程

### 1. 上传或导入

- 本地文件可走单文件上传、批量上传或分片续传
- 远程视频可走 URL 导入链路
- 上传文件会先进入 `uploads/.staging`

### 2. 上传前风控

- 先做 SHA-256 黑名单指纹比对
- 再做视觉内容风控
- 如主视觉模型不可用，会尝试系统级视觉兜底模型
- 如视觉链路不可用，再回退到字幕关键词风控
- 命中高风险内容则直接拒绝上传，不进入正式 `uploads/`

### 3. 分析前风控

- 对正式上传成功的视频再次执行风控
- 命中策略时会直接阻断分析
- 被拦截视频会被移动到 `uploads/.quarantine/<reason_code>/`

### 4. 长视频预处理

- 系统会根据时长和体积判断是否需要预处理
- 长视频会自动压缩，必要时切片后再拼接
- 预处理副本会放在输出目录下的 `.analysis_proxy/`

### 5. 内容分析

- 默认可先跑 Whisper 生成字幕
- 可选择字幕分析模式，或直接走视频理解模式
- 标准步骤失败后，会自动降级为候选步骤或时间线摘要

### 6. 文档输出

- 生成 `images/step_XX.jpg`
- 生成 `operation_guide.md`
- 生成 `operation_guide.pdf`
- 保存 `steps.json`
- 若有字幕，自动生成 `SRT / VTT / TXT`

### 7. 结果管理

- 写入 `history.json`
- 前端可按客户端 ID 隔离查看历史
- 支持单结果或批量结果 ZIP 打包下载

---

## 🛡️ 风控实现细节

这个项目的风控不是“上传时走一次”这么简单，而是做了多层防护。

### 上传前与分析前双重校验

- 上传阶段会拦住危险内容，避免正式落盘
- 分析阶段再次校验，防止绕过上传路径的风险文件被处理

### 指纹黑名单

- 使用视频文件的 `SHA-256` 指纹做完全一致匹配
- 命中过黑名单的视频会被直接拦截
- 黑名单持久化在 `uploads/.risk_blocklist.json`

### 视觉风控

- 对视频做动态抽帧，不同长度的视频抽帧数会自动增长
- 风险维度包括：
  - `nudity`
  - `violence`
  - `gore`
- 结果会归一化成：
  - `decision`: `allow / restrict / block`
  - `risk_level`: `low / medium / high`
  - `reason_code`
  - `scores`

### 视觉兜底与文本兜底

- 主模型不支持图片输入时，会优先尝试 `.env` 中配置的系统级视觉风控兜底模型
- 仍不可用时，会用字幕和文件名执行关键词风控
- 文本风控词库来自 `risk_keyword_lexicon.json`

### 风控缓存

- 对“同一视频 + 同一模型配置”的分析前风控结果做缓存
- 缓存文件：`uploads/.risk_result_cache.json`
- 这样同一个视频重复分析时可减少重复风控开销

### 隔离区

- 被分析前风控拦截的视频会被移动到 `uploads/.quarantine/`
- 子目录按 `reason_code` 划分，方便排查和审计

---

## 🧠 分析与文档生成细节

### `VideoAnalyzerAgent` 负责什么

`video_analyzer_agent.py` 不是单一“调模型脚本”，而是整个分析链路的核心执行器，负责：

- Whisper 字幕生成
- 字幕解析
- 视频理解
- 关键截图生成
- 低置信度步骤视觉增强
- Markdown 文档生成
- PDF 生成

### 字幕模式 vs 视频模式

#### 字幕模式

- 先用 Whisper 生成字幕
- 再基于带时间戳字幕让模型输出步骤 JSON
- 成本更低，更适合多数录屏教程

#### 视频模式

- 直接上传视频给模型分析步骤
- 能利用画面信息
- 代价更高，且长视频会被后端自动限制或降级

### Whisper 设计

- 优先使用常驻 Whisper 模型，减少重复加载
- 常驻模式失败后，回退到 Whisper CLI
- 字幕会缓存到 `outputs/.subtitle_cache/`

### 截图与视觉增强

- 步骤截图按 `step_01.jpg`、`step_02.jpg` 命名
- 截图生成支持并行
- 对低置信度步骤可再调用模型看图，补强标题和描述

### 结果模式

后端并不是只有“成功 / 失败”。

- ✅ `steps`
  - 标准步骤结果
- ⚠️ `candidate_steps`
  - 未识别出标准步骤时，从字幕启发式抽取低置信度候选步骤
- 🧭 `timeline_summary`
  - 连候选步骤都不足时，自动生成时间线摘要保底结果
- 🚫 `blocked_notice`
  - 命中安全策略时返回阻断说明卡，而不是普通分析结果

### 质量分与降级原因

后端会给结果计算 `quality_score`，并返回：

- `fallback_used`
- `degrade_reason`
- `confidence_note`

质量分综合考虑：

- 步骤结构完整度
- 时间顺序合理性
- 置信度
- 步骤来源权重
- 步骤数量是否合理

### 文档重生成

当前端编辑步骤后，后端会：

- 按编辑后的步骤重新生成 Markdown
- 重新生成 PDF
- 覆盖更新 `steps.json`
- 如果模型生成的文档没有忠实反映用户编辑内容，会回退到确定性文档构造器，保证结果与编辑一致

### PDF 生成

- 先把 Markdown 转成 HTML
- 再用 `fpdf2` 渲染
- 会自动尝试 Windows / Linux 常见中文字体路径

---

## 🌐 URL 导入链路实现

这个项目的 URL 导入不是简单“下载直链”，而是多层回退链路。

### 处理顺序

1. 标准化 URL
2. 识别平台类型
3. 若命中 B 站 / 抖音 / 小红书，优先走平台下载器
4. 若平台下载器失败，走 `scrapling` 页面抓取
5. 从页面 HTML、`meta`、`script`、JSON-LD 中提取候选视频地址
6. 必要时调用模型辅助解析 HTML 中的视频候选
7. 优先使用 `yt-dlp`
8. 再回退到 HTTP 直链下载

### 平台下载器

`Scrapling_download/` 中包含：

- `bilibili_downloader_llm.py`
- `douyin_downloader_llm.py`
- `xiaohongshu_downloader_llm.py`
- `platform_link_downloader.py`

这些模块会在通用下载失败时，用平台特征和 LLM 分析页面结构，尝试恢复可下载地址。

### URL 导入链路的额外能力

- 自动补充候选地址
- 可检测疑似人机验证页面
- 对抖音类链接支持严格媒体 ID 匹配，减少误下错视频
- `yt-dlp` 支持浏览器 cookies、cookie 文件、Header cookies 等多来源兜底

---

## 🖥️ 前端工作台能力

前端位于 `web-react/`，不是一个简单上传页，而是完整工作台。

### 核心交互

- 🎯 拖拽上传 / 文件选择
- 📦 批量文件列表与状态标签
- 🔗 视频链接导入
- ⏳ 单文件 / 批量任务进度轮询
- 🧾 历史记录抽屉
- ⚙️ 设置抽屉
- ✍️ 步骤编辑后重生成
- 🗣️ 字幕工作台与关键词检索
- 📥 单结果 / 批量 ZIP 下载

### 前端状态管理上的实现特点

- 使用 `localStorage` 持久化用户设置
- 使用本地生成的 `X-Client-ID` 做历史隔离
- 通过 `/single_progress` 与 `/batch_progress` 轮询进度
- 通过 `marked + DOMPurify` 安全渲染 Markdown

### 关于“前端设置”和“后端真实行为”的重要说明

当前实现里，真正生效的模型与多数处理参数以 **后端 `.env`** 为准。

实际代码行为是：

- 后端统一读取共享模型配置：`MODEL_API_KEY / MODEL_NAME / MODEL_BASE_URL`
- 上传风控与分析都共用后端共享模型配置
- 前端不再在上传前强制执行模型连通性校验
- 请求体当前主要覆盖的选项是：
  - `web_search`
  - `max_vision`
  - `summary_only`
- `WHISPER_MODE / USE_VIDEO / FPS` 等默认由后端 `.env` 控制

也就是说，README 里如果只写“前端可以切换模型参数”会不准确。当前代码的真实设计是：**以后端管理员配置为准，前端更偏向工作台 UI 与少量运行时开关。**

---

## 📦 输出目录长什么样

每次分析会生成一个独立输出目录，名称类似：

```text
outputs/demo_video_20260323_114500/
```

典型内容如下：

```text
outputs/<video_stem>_<timestamp>/
├─ operation_guide.md
├─ operation_guide.pdf
├─ steps.json
├─ <原视频文件>
├─ <字幕文件>.srt
├─ <字幕文件>.vtt
├─ <字幕文件>.txt
└─ images/
   ├─ step_01.jpg
   ├─ step_02.jpg
   └─ ...
```

运行过程中还可能出现临时目录：

- `.analysis_proxy/`：长视频预处理副本
- `.risk_frames/`：风控抽帧目录
- `.risk_subtitles/`：文本风控字幕临时目录

---

## 📏 视频分段策略与长视频控制

后端会根据视频时长和文件大小，把视频划分为不同区域。

### 标准区

- 允许正常上传与分析
- 批量建议最多 5 个视频，且总时长尽量不超过 60 分钟

### 长视频区

- 允许处理
- 后端会自动：
  - 关闭 `use_video`
  - 将 `max_vision` 归零
- 包含长视频时，整批最多允许 2 个视频

### 超长区

- 不允许进入批量分析
- 后端会自动：
  - 关闭 `use_video`
  - 关闭 `web_search`
  - 启用 `summary_only=true`

### 裁剪优先区

- 会直接拒绝上传或分析
- 典型条件：
  - 单视频超过 90 分钟
  - 或文件接近 / 超过 500MB

---

## ⚙️ 环境要求

- `Python 3.10+`
- `Node.js 18+`
- 可用的兼容模型接口
- `ffmpeg`
  - 若系统未安装，代码会优先尝试使用 `imageio-ffmpeg`
- 如需增强平台链接下载兜底，建议额外准备：
  - `playwright`
  - `playwright install chromium`

---

## 🚀 快速启动

### 1. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2. 启动后端

```bash
python app.py
```

默认后端地址：

```text
http://127.0.0.1:5000
```

说明：

- `FLASK_DEBUG=1` 时走 Flask 开发服务器
- 默认走 Waitress 生产模式

### 3. 启动前端

```bash
cd web-react
npm install
npm run dev
```

当前 `Vite` 配置端口是：

```text
http://127.0.0.1:80
```

如果本机 `80` 端口被占用，请修改 `web-react/vite.config.ts` 中的 `server.port`。

---

## 🔐 推荐 `.env` 配置

下面是根据当前代码整理的常用配置项示例。

```env
# ===== 共享模型配置（后端真实生效的主入口） =====
MODEL_API_KEY=your_api_key
MODEL_NAME=doubao-seed-2-0-pro-260215
MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3

# ===== 分析默认参数 =====
WHISPER_MODE=base
ANALYZE_USE_VIDEO=1
VIDEO_ANALYZE_FPS=1
MAX_VISION=10
WEB_SEARCH=0

# ===== 性能相关 =====
WHISPER_THREADS=4
SCREENSHOT_MAX_WORKERS=2
BATCH_ANALYZE_MAX_WORKERS=2
LONG_VIDEO_PREPROCESS_ENABLED=1

# ===== 风控相关 =====
RISK_MAX_FRAMES=4
RISK_DYNAMIC_MAX_FRAMES=8
RISK_FALLBACK_API_KEY=
RISK_FALLBACK_MODEL_NAME=
RISK_FALLBACK_MODEL_BASE_URL=

# ===== URL 抓取 / 下载 =====
SCRAPE_FETCH_MODE=auto
SCRAPE_PROXY_URL=
SCRAPE_MODEL_PARSE_ENABLED=1
YTDLP_PREFER_BROWSER_COOKIES=1
YTDLP_COOKIES_FROM_BROWSER=chrome

# ===== 服务参数 =====
HOST=127.0.0.1
PORT=5000
WAITRESS_THREADS=4
WAITRESS_CONNECTION_LIMIT=100
```

### 配置说明

| 变量 | 作用 |
| --- | --- |
| `MODEL_API_KEY` | 后端共享模型密钥，风控与分析都会用到 |
| `MODEL_NAME` | 主模型名称 |
| `MODEL_BASE_URL` | 兼容接口的 Base URL |
| `WHISPER_MODE` | Whisper 模型级别：`tiny/base/small/medium/large` |
| `ANALYZE_USE_VIDEO` | 后端默认是否启用视频理解模式 |
| `VIDEO_ANALYZE_FPS` | 视频模式的抽帧频率 |
| `MAX_VISION` | 低置信度步骤的最大视觉增强次数 |
| `WEB_SEARCH` | 文档生成是否启用联网搜索 |
| `WHISPER_THREADS` | Whisper 推理线程数 |
| `SCREENSHOT_MAX_WORKERS` | 截图并发数 |
| `BATCH_ANALYZE_MAX_WORKERS` | 批量分析并发数 |
| `LONG_VIDEO_PREPROCESS_ENABLED` | 是否启用长视频预处理 |
| `RISK_MAX_FRAMES` | 基础风控抽帧数 |
| `RISK_DYNAMIC_MAX_FRAMES` | 动态抽帧上限 |
| `RISK_FALLBACK_*` | 系统级视觉风控兜底模型 |
| `SCRAPE_*` | 页面抓取、动态等待、代理、隐身会话等配置 |
| `YTDLP_*` | `yt-dlp` cookies 来源与策略 |
| `WAITRESS_*` | 生产服务线程和连接数 |

---

## 📡 主要接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/upload` | 单文件上传并执行上传前风控 |
| `POST` | `/upload_batch` | 批量上传并逐文件风控 |
| `POST` | `/upload_url` | 从 URL 下载视频并执行风控 |
| `POST` | `/upload_chunk_init` | 初始化分片上传会话 |
| `POST` | `/upload_chunk` | 上传单个分片 |
| `POST` | `/upload_chunk_finalize` | 合并分片并执行上传前风控 |
| `POST` | `/analyze` | 单文件分析 |
| `POST` | `/analyze_batch` | 批量分析 |
| `GET` | `/single_progress` | 查询单文件进度 |
| `GET` | `/batch_progress` | 查询批量进度 |
| `POST` | `/regenerate` | 根据编辑后的步骤重新生成文档 |
| `GET` | `/history` | 历史列表 |
| `GET` | `/history/<record_id>` | 历史详情 |
| `DELETE` | `/history/<record_id>` | 删除历史记录 |
| `GET` | `/subtitle_workbench` | 返回字幕工作台数据 |
| `GET` | `/download_subtitle/<output_dir>` | 下载字幕导出文件 |
| `GET` | `/download_zip/<output_dir>` | 下载单结果 ZIP |
| `POST` | `/download_batch_zip` | 下载批量结果 ZIP |
| `GET` | `/output/<path:filename>` | 访问输出目录内静态资源 |
| `POST` | `/test_model` | 测试模型连接 |

---

## 📂 分片续传实现说明

项目的分片上传不是简单“前端切片 + 后端拼文件”，而是做了会话管理。

- 默认分片大小：`8MB`
- 分片大小上限：`32MB`
- 单文件上传上限：`500MB`
- 小文件优先走内存缓冲
- 大文件走磁盘临时文件 `.part`
- 上传会话保存在 `uploads/.upload_sessions/`
- 前端会把 `upload_id` 保存到本地，实现断点续传

内存模式的阈值在当前代码中是：

- 单文件不超过 `64MB`
- 全部会话累计不超过 `256MB`

---

## 🕘 历史记录与自动清理

### 历史隔离

- 前端会生成本地客户端 ID
- 通过 `X-Client-ID` 请求头传给后端
- 后端也会补充一个 Cookie 做兜底
- `history.json` 会按 owner 隔离记录，不是完整登录鉴权系统

### 自动清理

- 上传视频：`24h` 自动清理
- 历史记录与输出目录：`72h` 自动清理
- 清理线程在请求进入时确保启动

---

## 🧪 开发与维护建议

- 🧷 如果你主要在本地单机运行，优先把 `.env` 配好，再考虑 UI 参数
- 🧵 `BATCH_ANALYZE_MAX_WORKERS` 和 `WHISPER_THREADS` 是最关键的性能旋钮
- ✂️ 遇到超长视频时，优先裁剪，而不是强行提高并发
- 🔐 如果要开启 `WEB_SEARCH`，确保模型平台已开通对应能力
- 🌐 如果 URL 导入经常遇到风控页，优先补 cookies、代理或浏览器会话

---

## 📌 当前实现中的真实约束

- 后端目前是一个“大单文件应用”风格，核心逻辑集中在 `app.py`
- 前端设置项很多，但不是所有设置都会真正进入后端请求
- 生产模式默认使用 Waitress，不是 Flask 自带开发服务器
- URL 导入链路很强，但它依赖站点结构、cookies、代理、`yt-dlp` 状态和平台反爬环境
- 项目内确实存在平台下载器脚本与若干工具脚本，但 README 应以 `app.py` 当前主链路为准

---

## 📝 变更记录

详细历史更新可查看：

- [`updata.md`](updata.md)

