# 🎬 Video-to-Markdown/PDF — LLM 视频智能分析系统

面向教程视频、操作演示、工作流录屏的全栈分析工具。通过内容安全检测后，将视频自动整理为结构化步骤、关键截图、Markdown/PDF 文档、字幕导出和可下载结果包。

---

## ✨ 功能概览

| 模块 | 能力 |
| --- | --- |
| 📤 上传 | 单文件 / 批量 / 分片续传 / URL 导入 |
| 🛡️ 风控 | 上传前 + 分析前双重校验（SHA-256 黑名单、视觉检测、关键词兜底） |
| 🧠 分析 | Whisper 字幕 + 视频理解双模式，标准步骤 → 候选步骤 → 时间线摘要三级降级 |
| 🎯 字幕精度 | 音频降噪/响度归一化（Plan B）、热词偏置 + 自学习词表（Plan A）、LLM 同音字上下文纠错 |
| 📄 输出 | Markdown、PDF、步骤截图、`steps.json`、字幕（SRT/VTT/TXT） |
| 🪄 增强 | 低置信度步骤截图视觉增强、前端编辑步骤后重新生成文档 |
| 📦 管理 | 历史记录（client-id 隔离）、批量 ZIP 下载、24h 上传 / 72h 历史自动清理 |

---

## 🚀 快速启动

### 环境要求

- **Python 3.10+**  /  **Node.js 18+**  /  **ffmpeg**（未安装时自动使用 `imageio-ffmpeg`）
- 可用的 LLM 接口（默认定向火山引擎 Ark）

### 1. 安装后端

```bash
pip install -r requirements.txt
```

`faster-whisper` 与中文分词库 `jieba`（用于字幕纠错词表提炼）已包含在依赖中，无需额外安装。

### 2. 配置 `.env`

在项目根目录创建 `.env`，至少填写：

```env
MODEL_API_KEY=your_api_key
MODEL_NAME=doubao-seed-2-0-pro-260215
MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

其余参数见 [环境变量参考](#-环境变量参考)。

### 3. 启动后端

```bash
python app.py
```

- `FLASK_DEBUG=1` 时走 Flask 开发服务器，否则默认走 **Waitress** 生产模式
- 默认地址：`http://127.0.0.1:5000`

### 4. 启动前端

```bash
cd web-react
npm install
npm run dev
```

默认端口 `80`（如需更改，编辑 `web-react/vite.config.ts` 中的 `server.port`）。
> Windows 下 80 端口可能被占用；Linux/macOS 使用 80 端口需要 root 权限，建议改为 `3000` 或其他端口。

---

## 🏗️ 项目结构

```text
.
├─ app.py                              # Flask 主应用（上传/风控/分析/历史/导出）
├─ video_analyzer_agent.py             # 分析核心：Whisper/截图/视觉增强/文档生成
├─ llm_client/                         # LLM 客户端抽象层
│  ├─ base.py                          #   抽象基类 + Capability 枚举 + 错误类型
│  ├─ ark_client.py                    #   火山引擎 Ark 实现（支持全能力）
│  ├─ openai_compat_client.py          #   OpenAI/DeepSeek/Qwen 兼容实现
│  └─ factory.py                       #   根据 MODEL_PROVIDER / BASE_URL 路由
├─ asr/                                # ASR 抽象层
│  ├─ base.py / factory.py             #   TranscriberBackend 抽象 + 构建工厂
│  ├─ faster_whisper_backend.py        #   faster-whisper (CTranslate2) 实现
│  ├─ audio_preprocess.py              #   Plan B：ffmpeg 降噪 + 响度归一化
│  ├─ subtitle_correct.py              #   LLM 同音字纠错（纯函数：构造提示/解析/护栏）
│  ├─ correction_log.py                #   纠错复查日志 + 自学习热词词表（Plan A 反馈环）
│  ├─ zh_simplify.py                   #   繁→简中文归一化
│  └─ srt_writer.py                    #   SRT 序列化
├─ Scrapling_download/                 # B站/抖音/小红书平台链接下载器
├─ web-react/                          # React 19 + TypeScript 前端工作台
├─ showcase/                           # 独立的展示/落地页项目
├─ scripts/                            # 辅助脚本（编译检查/编码检查）
├─ risk_keyword_lexicon.json           # 文本风控关键词库
├─ requirements.txt                    # Python 依赖
└─ updata.md                           # 版本变更记录
```

---

## 🔄 处理流程

```
上传/导入 → 上传前风控 → 分析前风控 → 预处理(长视频) → Whisper/视频理解 → 字幕纠错 → 文档生成 → 结果保存
```

### 1. 上传
本地文件支持单文件、批量、分片续传（8MB 分片，最大 500MB）；远程视频走 URL 导入链路。

### 2. 风控（双重校验）
- **上传前**：SHA-256 黑名单指纹 → 视觉风控（动态抽帧，nudity/violence/gore）→ 关键词兜底
- **分析前**：再次风控，命中则移入 `uploads/.quarantine/<reason_code>/` 隔离区
- 视觉模型不可用时依次尝试系统级兜底模型 → 字幕关键词风控

### 3. 长视频预处理
根据时长和体积自动压缩/切片，预处理副本放在 `outputs/.analysis_proxy/`。

### 4. 内容分析
- **字幕模式**（默认）：Whisper 生成字幕 → 基于时间戳字幕输出步骤 JSON（成本低，适合录屏）
- **视频模式**（需 Ark）：直传视频给模型分析（可利用画面信息，长视频自动限制或降级）
- 标准步骤失败后自动降级：候选步骤 → 时间线摘要

#### 4.1 字幕精度增强（字幕模式）

- **音频预处理（Plan B）**：ASR 前用 ffmpeg 做高通滤波 + FFT 降噪 + EBU R128 响度归一化（`WHISPER_PREPROCESS_AUDIO`，默认关闭）；失败时回退原始音轨，绝不阻断转写
- **解码质量调优**：beam search、`best_of`、温度回退梯队、关闭跨段条件化以抑制长静音段幻觉，默认值即提升准确率
- **热词偏置（Plan A）**：`WHISPER_HOTWORDS` / `WHISPER_INITIAL_PROMPT` 在解码阶段就把识别偏向正确的领域术语
- **LLM 同音字纠错**：转写后把字幕分批送模型，仅修正同音/近音错别字（如「铁子」→「帖子」），长度比例护栏拒绝任何疑似改写（`SUBTITLE_LLM_CORRECT`，默认开启）
- **自学习反馈环**：每次纠错都用 jieba 切词提炼 `(错→对)` 词对，写入 `outputs/subtitle_corrections.jsonl` 复查日志，并把正确术语沉淀进 `outputs/hotwords_glossary.txt`；该词表在下一个视频转写时即被重新读取为热词，无需重启进程

### 5. 文档输出
生成 `images/step_XX.jpg`、`operation_guide.md`、`operation_guide.pdf`、`steps.json`，有字幕时附加 SRT/VTT/TXT。

### 6. 结果管理
写入 `history.json`，前端按 client-id 隔离查看，支持单结果和批量 ZIP 下载。

---

## 🔌 LLM 客户端抽象

所有模型调用走 `llm_client/` 统一抽象，`VideoAnalyzerAgent` 不直接依赖任何 provider SDK。

### 能力声明

| 能力 | 说明 | Ark | OpenAI/DeepSeek/Qwen |
| --- | --- | :-: | :-: |
| `CHAT_COMPLETIONS` | 文本对话 | ✅ | ✅ |
| `FILE_UPLOAD` | 视频文件上传到平台 | ✅ | ❌ |
| `VIDEO_UNDERSTANDING` | 原生视频理解 | ✅ | ❌ |
| `WEB_SEARCH_TOOL` | 联网搜索工具 | ✅ | ❌ |

### Provider 路由

1. 显式 `provider` 参数 → 2. `.env` `MODEL_PROVIDER` → 3. 按 `MODEL_BASE_URL` 推断：
   - `*.volces.com` → `ark`
   - `api.openai.com` → `openai`
   - 其他 HTTPS → `openai_compatible`

### 自动降级

切换到非 Ark 平台时，后端自动关闭 `use_video` 和 `web_search`，走字幕分析链路。若运行时触碰到不支持的能力，返回 `HTTP 400` + `code=provider_feature_unsupported`。

---

## 🎙️ ASR 字幕识别

统一走 `faster-whisper`（CTranslate2，CPU/显存友好），通过 `asr/` 抽象层调用。输出经繁→简归一化。

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `WHISPER_MODE` / `WHISPER_MODEL` | `base` | 模型：`tiny` / `base` / `small` / `medium` / `large` |
| `WHISPER_THREADS` | CPU 核数（1-8） | 推理线程数 |
| `WHISPER_DEVICE` | `auto` | `cpu` / `cuda` / `auto` |
| `WHISPER_COMPUTE_TYPE` | `int8` | 精度：`int8` / `int8_float16` / `float16` / `float32` |
| `WHISPER_BEAM_SIZE` | `5` | beam search 宽度（1-10） |
| `WHISPER_BEST_OF` | `5` | 候选采样数（1-10） |
| `WHISPER_VAD_FILTER` | `1` | 是否启用 VAD 过滤静音段 |
| `WHISPER_CONDITION_ON_PREVIOUS_TEXT` | `0` | 跨段条件化；关闭可抑制长静音段循环幻觉 |
| `WHISPER_TEMPERATURES` | `0.0,0.2,0.4` | 温度回退梯队（低置信度解码自动重试） |
| `WHISPER_COMPRESSION_RATIO_THRESHOLD` | `2.4` | 压缩比阈值（1.0-10.0） |
| `WHISPER_NO_SPEECH_THRESHOLD` | `0.6` | 无语音判定阈值（0.0-1.0） |
| `WHISPER_INITIAL_PROMPT` | - | 解码上下文种子提示（Plan A） |
| `WHISPER_HOTWORDS` | - | 静态领域热词（Plan A，与自学习词表合并） |
| `WHISPER_HOTWORDS_FILE` | `outputs/hotwords_glossary.txt` | 自学习热词词表路径 |
| `WHISPER_PREPROCESS_AUDIO` | `0` | Plan B：ASR 前 ffmpeg 降噪 + 响度归一化 |

字幕缓存到 `outputs/.subtitle_cache/`，缓存键含模型大小、精度、beam size、best_of、跨段条件化、压缩比/无语音阈值、initial_prompt/热词/音频预处理开关、VAD 等参数，调参后不会错误复用。

### 字幕精度三层方案

| 方案 | 阶段 | 机制 | 默认 |
| --- | --- | --- | --- |
| **Plan B** | 转写前 | ffmpeg `highpass`+`afftdn`+`loudnorm` 清理音频，输出 16kHz 单声道 | 关 |
| **Plan A** | 解码时 | `hotwords` + `initial_prompt` 把识别偏向正确术语 | 静态热词需手动配置 |
| **LLM 纠错** | 转写后 | 上下文同音字纠错（长度比例护栏防改写） | 开 |

**自学习反馈环**：LLM 纠错产生的每处改动会经 jieba 切词提炼为 `(错→对)` 词对——

1. **记录**：完整 before/after 行 + 双侧分词 + 词对写入 `outputs/subtitle_corrections.jsonl`，供人工复查
2. **沉淀**：正确术语累加进 `outputs/hotwords_glossary.txt`（去重有序的纯文本词表）
3. **回灌**：`asr.factory` 在每次 `transcribe()` 时重新读取该词表作为 Plan A 热词，本次进程内累积的纠错对下一个视频立即生效，无需重启

整条链路 best-effort：jieba 缺失时退化为字符级切分，任何写入失败都不会中断转写。

---

## 🛡️ 风控策略

| 层级 | 机制 |
| --- | --- |
| 指纹黑名单 | 视频 SHA-256 完全匹配，黑名单存于 `uploads/.risk_blocklist.json` |
| 视觉风控 | 动态抽帧（`RISK_MAX_FRAMES`→`RISK_DYNAMIC_MAX_FRAMES`），检测 nudity/violence/gore |
| 视觉兜底 | 主模型不支持图片时尝试系统级兜底模型 (`RISK_FALLBACK_*`) |
| 文本兜底 | 字幕关键词匹配（`risk_keyword_lexicon.json`）+ 文件名检测 |
| 风控缓存 | 同一视频+同一模型的结果缓存到 `uploads/.risk_result_cache.json` |

---

## 📏 视频分段策略

| 区间 | 条件 | 行为 |
| --- | --- | --- |
| **标准区** | 正常视频 | 正常分析，批量 ≤5 个、总时长 ≤60min |
| **长视频区** | 超阈值 | `use_video` 关闭，`max_vision` 归零，批量 ≤2 个 |
| **超长区** | 更长/更大 | 仅 `summary_only`，禁止批量分析 |
| **裁剪优先区** | >90min 或 ≥500MB | 直接拒绝 |

---

## 📄 结果模式与文档生成

### 结果分级

| 模式 | 说明 |
| --- | --- |
| `steps` ✅ | 标准步骤结果（含 `quality_score` / `fallback_used` / `degrade_reason`） |
| `candidate_steps` ⚠️ | 低置信度候选步骤（字幕启发式抽取） |
| `timeline_summary` 🧭 | 时间线摘要保底结果 |
| `blocked_notice` 🚫 | 风控阻断说明卡 |

### 文档重生成

前端编辑步骤后，后端按编辑后的步骤重新生成 Markdown 和 PDF，覆盖 `steps.json`。若模型输出不忠实反映编辑内容，回退到确定性文档构造器。

### PDF 生成

Markdown → HTML → `fpdf2` 渲染，自动探测 Windows / Linux 常见中文字体路径。

---

## 🌐 URL 导入链路

多级回退策略：

1. 标准化 URL → 识别平台类型
2. B站/抖音/小红书 → 平台下载器
3. 失败 → `scrapling` 页面抓取 → 提取候选视频地址 → 模型辅助解析
4. `yt-dlp` 下载（支持浏览器 cookies/Netscape 文件/Header cookies 多源兜底）
5. HTTP 直链下载兜底

---

## 🖥️ 前端工作台

`web-react/` —— 基于 React 19 + TypeScript + Vite + Tailwind CSS 4 的完整工作台。

**核心交互**：拖拽上传、批量文件列表、URL 导入、进度轮询、历史记录抽屉、步骤编辑重生成、字幕工作台、ZIP 下载。

**状态管理**：`localStorage` 持久化设置、`X-Client-ID` 历史隔离、`/single_progress` 与 `/batch_progress` 轮询、`marked` + `DOMPurify` 安全渲染 Markdown。

> **重要**：真正生效的模型与处理参数以 **后端 `.env`** 为准。前端设置偏向工作台 UI 与少量运行时开关（`web_search`、`max_vision`、`summary_only`），`WHISPER_MODE`、`USE_VIDEO`、`FPS` 等由后端控制。

---

## 📡 API 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/upload` | 单文件上传 + 风控 |
| `POST` | `/upload_batch` | 批量上传 + 逐文件风控 |
| `POST` | `/upload_url` | URL 下载 + 风控 |
| `POST` | `/upload_chunk_init` | 初始化分片上传 |
| `POST` | `/upload_chunk` | 上传分片 |
| `POST` | `/upload_chunk_finalize` | 合并分片 + 风控 |
| `POST` | `/analyze` | 单文件分析 |
| `POST` | `/analyze_batch` | 批量分析（ThreadPoolExecutor 并行） |
| `GET` | `/single_progress` | 单文件进度 |
| `GET` | `/batch_progress` | 批量进度 |
| `POST` | `/regenerate` | 编辑步骤后重生成文档 |
| `POST` | `/test_model` | 测试模型连接 |
| `GET` | `/history` | 历史列表（按 client-id 隔离） |
| `GET` | `/history/<record_id>` | 历史详情 |
| `DELETE` | `/history/<record_id>` | 删除历史记录 |
| `GET` | `/subtitle_workbench` | 字幕工作台数据 |
| `GET` | `/download_subtitle/<output_dir>` | 下载字幕文件 |
| `GET` | `/download_zip/<output_dir>` | 下载单结果 ZIP |
| `POST` | `/download_batch_zip` | 下载批量结果 ZIP |
| `GET` | `/output/<path:filename>` | 访问输出目录静态资源 |

---

## 📦 输出目录结构

```text
outputs/<video_stem>_<timestamp>/
├─ operation_guide.md
├─ operation_guide.pdf
├─ steps.json
├─ <原视频文件>
├─ <字幕>.srt / .vtt / .txt
└─ images/
   ├─ step_01.jpg
   ├─ step_02.jpg
   └─ ...
```

运行时临时目录：`.analysis_proxy/`（预处理副本）、`.risk_frames/`（风控抽帧）、`.risk_subtitles/`（文本风控字幕）、`.subtitle_cache/`（字幕缓存）。

字幕精度反馈环产物（位于 `outputs/` 根目录，跨视频共享）：

- `subtitle_corrections.jsonl` —— LLM 同音字纠错复查日志（每行一条改动）
- `hotwords_glossary.txt` —— 自学习热词词表，下次转写自动作为 Plan A 热词回灌

---

## 📂 分片续传

- 分片大小 8MB（上限 32MB），单文件上限 500MB
- 小文件（≤64MB）走内存缓冲，大文件走磁盘临时文件 `.part`
- 会话保存在 `uploads/.upload_sessions/`，前端保存 `upload_id` 实现断点续传
- 全部会话累计内存 ≤256MB

---

## 🕘 自动清理

- 上传视频：**24h** 后自动删除
- 历史记录与输出目录：**72h** 后自动清理
- 清理守护线程在首次请求时启动

---

## 🔐 环境变量参考

### 模型主入口

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MODEL_API_KEY` | 共享模型密钥（风控+分析共用） | - |
| `MODEL_NAME` | 主模型名称 | `doubao-seed-2-0-pro-260215` |
| `MODEL_BASE_URL` | 兼容接口 Base URL | `https://ark.cn-beijing.volces.com/api/v3` |
| `MODEL_PROVIDER` | 强制指定 provider（`ark` / `openai` / `openai_compatible`） | 按 URL 推断 |

### 分析参数

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `WHISPER_MODE` | Whisper 模型级别 | `base` |
| `ANALYZE_USE_VIDEO` | 视频理解模式（仅 Ark） | `1` |
| `VIDEO_ANALYZE_FPS` | 视频模式抽帧频率 | `1` |
| `MAX_VISION` | 视觉增强次数上限 | `10` |
| `WEB_SEARCH` | 联网搜索（仅 Ark） | `0` |

### 字幕精度

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `WHISPER_PREPROCESS_AUDIO` | Plan B：ASR 前 ffmpeg 降噪 + 响度归一化 | `0` |
| `WHISPER_BEST_OF` | 候选采样数（1-10） | `5` |
| `WHISPER_CONDITION_ON_PREVIOUS_TEXT` | 跨段条件化（关闭抑制幻觉） | `0` |
| `WHISPER_TEMPERATURES` | 温度回退梯队 | `0.0,0.2,0.4` |
| `WHISPER_COMPRESSION_RATIO_THRESHOLD` | 压缩比阈值（1.0-10.0） | `2.4` |
| `WHISPER_NO_SPEECH_THRESHOLD` | 无语音判定阈值（0.0-1.0） | `0.6` |
| `WHISPER_INITIAL_PROMPT` | Plan A：解码上下文种子提示 | - |
| `WHISPER_HOTWORDS` | Plan A：静态领域热词 | - |
| `WHISPER_HOTWORDS_FILE` | 自学习热词词表路径 | `outputs/hotwords_glossary.txt` |
| `SUBTITLE_LLM_CORRECT` | LLM 同音字纠错开关 | `1` |
| `SUBTITLE_CORRECT_GLOSSARY` | 纠错时提供给模型的正确术语提示 | - |
| `SUBTITLE_CORRECTION_LOG` | 纠错复查日志路径 | `outputs/subtitle_corrections.jsonl` |

### 性能

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `WHISPER_THREADS` | Whisper 推理线程数 | CPU 核数（≤8） |
| `WHISPER_DEVICE` | `cpu` / `cuda` / `auto` | `auto` |
| `WHISPER_COMPUTE_TYPE` | `int8` / `int8_float16` / `float16` / `float32` | `int8` |
| `WHISPER_BEAM_SIZE` | beam search 宽度（1-10） | `5` |
| `WHISPER_VAD_FILTER` | 语音活动检测 | `1` |
| `SCREENSHOT_MAX_WORKERS` | 截图并发数 | `2` |
| `BATCH_ANALYZE_MAX_WORKERS` | 批量分析并发数（1-16） | `2` |
| `LONG_VIDEO_PREPROCESS_ENABLED` | 长视频预处理开关 | `1` |

### 风控

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `RISK_MAX_FRAMES` | 基础抽帧数 | `4` |
| `RISK_DYNAMIC_MAX_FRAMES` | 动态抽帧上限 | `8` |
| `RISK_FALLBACK_API_KEY` | 视觉风控兜底模型 Key | - |
| `RISK_FALLBACK_MODEL_NAME` | 视觉风控兜底模型名 | - |
| `RISK_FALLBACK_MODEL_BASE_URL` | 视觉风控兜底 Base URL | - |

### URL 抓取（Scrapling）

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `SCRAPE_FETCH_MODE` | `auto` / `static` / `dynamic` | `auto` |
| `SCRAPE_TIMEOUT_SECONDS` | 抓取超时 | `45` |
| `SCRAPE_RETRIES` | 重试次数 | `3` |
| `SCRAPE_MODEL_PARSE_ENABLED` | 模型辅助解析 HTML 候选视频 | `1` |
| `SCRAPE_STRICT_MEDIA_ID_MATCH` | 抖音严格媒体 ID 匹配 | `1` |
| `SCRAPE_PROXY_URL` / `SCRAPE_USER_AGENT` / `SCRAPE_COOKIES_JSON` | 代理/UA/Cookies | - |
| `SCRAPE_STEALTH_*` | 隐身会话（dynamic 模式）参数组 | 见 `.env` |
| `SCRAPE_MODEL_API_KEY` / `_NAME` / `_BASE_URL` | 抓取专用模型凭证（回退到 `MODEL_*`） | - |

### yt-dlp

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `YTDLP_PREFER_BROWSER_COOKIES` | 优先从浏览器导入 cookies | `1` |
| `YTDLP_COOKIES_FROM_BROWSER` | 浏览器来源（如 `chrome`） | - |
| `YTDLP_BROWSER_FALLBACKS` | 候选浏览器列表 | `chrome,edge` |
| `YTDLP_COOKIES_FILE` | Netscape 格式 cookies 文件 | - |

### 服务

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `HOST` | 监听地址 | `127.0.0.1` |
| `PORT` | 监听端口 | `5000` |
| `FLASK_DEBUG` | `1`=Flask 开发服务器，否则 Waitress | `0` |
| `WAITRESS_THREADS` | Waitress 工作线程数 | `4` |
| `WAITRESS_CONNECTION_LIMIT` | 最大并发连接 | `100` |

### 安全

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `FLASK_SECRET_KEY` | Flask 会话签名密钥（缺失时启动随机生成） | 随机 |
| `URL_IMPORT_ALLOW_PRIVATE_HOSTS` | 允许 URL 导入访问内网/保留地址（SSRF 防护开关，仅信任内网部署设 `1`） | `0` |

---

## 🧪 开发建议

- 先在 `.env` 配好模型参数，再调整前端 UI
- `BATCH_ANALYZE_MAX_WORKERS` 和 `WHISPER_THREADS` 是核心性能旋钮
- 字幕识别不准时优先：升级 `WHISPER_MODE` → 开启 `WHISPER_PREPROCESS_AUDIO` → 配置 `WHISPER_HOTWORDS` 领域术语；纠错词表会随使用自动增长
- 超长视频优先裁剪，而非强行提高并发
- URL 导入遇风控页时优先补 cookies 或代理
- 可选依赖：`pip install playwright && playwright install chromium` 可增强动态页面抓取

---

## 📌 实现约束

- 后端为单体 Flask 应用，核心逻辑在 `app.py`（约 8000+ 行）
- 生产模式默认 Waitress，非 Flask 开发服务器
- 前端设置中存在不进入后端请求的项
- URL 导入链路依赖站点结构、cookies、代理和 `yt-dlp` 状态
- `showcase/` 是独立的展示/落地页项目，非主应用的一部分

---

## 📝 变更记录

详见 [`updata.md`](updata.md)
