# 🎬 Video-to-Markdown/PDF — LLM 视频智能分析系统

把教程视频、操作演示、工作流录屏自动整理成结构化步骤、关键截图、Markdown/PDF 文档和字幕。

## ✨ 功能

- **上传**：单文件 / 批量 / 分片续传 / URL 导入（B站、抖音、小红书等），单文件须 `<500MB`
- **风控**：上传时做指纹 / 黑名单与缓存预检；任务进入 `analyzing` 后、内容分析前先执行主视觉检测，必要时以备用视觉模型或字幕关键词兜底
- **分析**：Whisper 字幕 + 视频理解双模式，标准步骤 → 候选步骤 → 时间线摘要三级降级
- **任务**：持久化异步队列，覆盖 `queued` / `analyzing` / `completed` / `failed` / `cancelled` 五个分析状态，支持取消、重试和刷新恢复
- **字幕精度**：音频降噪、热词偏置 + 自学习词表、LLM 同音字纠错
- **输出**：结果 ZIP 包含 Markdown、生成成功时的 PDF、`steps.json`、步骤截图和字幕导出（SRT/VTT/TXT），不包含原视频
- **管理**：历史记录隔离、批量 ZIP 下载、自动清理（24h 上传 / 72h 历史），用于降低长期磁盘增长

<img width="2553" height="1224" alt="438dc3dcfa83ee7e9f24b6a5ecf0fc7f" src="https://github.com/user-attachments/assets/fe060649-bd21-449a-a4a4-a490b95069ba" />

<img width="2526" height="1217" alt="49ce0fc466b80577bbe0ceac75e0ee51" src="https://github.com/user-attachments/assets/60016c0a-a931-4ed2-869f-0db3f74e9065" />


## 🚀 快速开始

**环境**：Python 3.10+、Node.js 18+、ffmpeg（未装则自动用 `imageio-ffmpeg`）

```bash
# 1. 安装后端依赖
pip install -r requirements.txt

# 2. 配置 .env
cp .env.example .env

# 3. 启动后端
python app.py            # 默认 http://127.0.0.1:5000

# 4. 启动前端
cd web-react && npm install && npm run dev
```

### 配置模型（必填）

`.env` 中的这 3 项**必填且无默认值**，缺失时后端无法开始模型分析：

```env
MODEL_API_KEY=your_api_key
MODEL_NAME=your_vision_model        # 必须是视觉模型（VLM）
MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
```

> ⚠️ **必须使用视觉模型（VLM / 多模态，支持图片输入）**。视频理解、AI 看图增强和主视觉风控依赖图片输入；主视觉检测不可用时，风控才会尝试备用视觉模型或字幕关键词路径。
> 例：火山引擎 `doubao-*-vision`、OpenAI `gpt-4o`。

其余参数全部以 `.env` 为准，完整说明见 [.env.example](.env.example)。

## 🔄 处理流程

```
上传/导入 → 指纹/黑名单预检 → 持久队列（queued）→ 领取任务（analyzing）→ 内容分析前主视觉风控 → 长视频预处理 → Whisper/视频理解 → 字幕纠错 → 文档生成 → completed/failed/cancelled
```

- **字幕模式**（默认）：Whisper 生成字幕 → 按时间戳输出步骤，成本低，适合录屏
- **视频模式**（需 Ark）：直传视频给模型分析，可利用画面信息
- 标准步骤失败时自动降级：候选步骤 → 时间线摘要
- 异步任务由后端持久化；页面刷新后可凭 `task_id` 恢复 `queued` / `analyzing` / `completed` / `failed` / `cancelled` 五个分析状态，并按状态取消或重试
- 分片上传会话单独使用 `uploading` 状态，不属于分析任务队列

### 上传与续传边界

- 单文件必须 `<500MB`；达到或超过 500MB 会被拒绝，并提示先裁剪视频
- 分片与上传会话保存在后端磁盘，后端重启后仍可查询已收到的分片
- 浏览器刷新或重开后无法保留 `File` 字节；需要重新选择同一文件，客户端再按服务端清单续传缺失分片
- 网络或请求确认中断时，当前分片仍可能重传；续传只跳过服务端已经确认收到的分片

### 风控边界

- 上传预检只执行文件指纹 / 黑名单匹配与已有缓存判定；命中阻断时删除暂存上传，不移入隔离目录
- 任务进入 `analyzing` 后、内容分析前先执行主视觉检测；主检测不可用时，才尝试备用视觉模型或字幕关键词检查
- 分析阶段命中阻断的文件可进入隔离目录，判定结果会缓存以减少重复检测

## 🧩 项目结构

```text
app.py                  # Flask 主应用（上传/风控/分析/历史/导出）
video_analyzer_agent.py # 分析核心：Whisper / 截图 / 视觉增强 / 文档生成
config.py               # 集中配置（全部读自 .env）
llm_client/             # LLM 客户端抽象层（Ark / OpenAI / OpenAI 兼容三类路由）
asr/                    # ASR 抽象层（faster-whisper + 音频预处理 + 字幕纠错）
services/task_store.py  # SQLite 持久化任务状态
services/task_runner.py # 异步任务执行与取消协调
Scrapling_download/     # B站/抖音/小红书链接下载器
web-react/              # React 19 + TypeScript 前端工作台
```

所有模型调用走 `llm_client/` 统一抽象，分为 Ark、OpenAI、OpenAI 兼容三类路由。系统按 `MODEL_PROVIDER` 或 `MODEL_BASE_URL` 选择实现（`*.volces.com`→Ark，`api.openai.com`→OpenAI，其余→OpenAI 兼容）；DeepSeek、Qwen 可作为 OpenAI 兼容端点示例，不是独立 provider 实现。切换到非 Ark 路由时自动关闭视频理解和联网搜索，走字幕链路。

## 🔐 常用环境变量

完整列表见 [.env.example](.env.example)，以下为最常调整的项：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `MODEL_API_KEY` / `MODEL_NAME` / `MODEL_BASE_URL` | 模型主入口，**必填，须为视觉模型** | 无 |
| `WHISPER_MODE` | Whisper 级别：`tiny`/`base`/`small`/`medium`/`large` | `base` |
| `ANALYZE_USE_VIDEO` | 视频理解模式（仅 Ark） | `1` |
| `MAX_VISION` | 视觉增强次数上限 | `10` |
| `SUBTITLE_LLM_CORRECT` | LLM 同音字纠错开关 | `1` |
| `WHISPER_PREPROCESS_AUDIO` | ASR 前音频降噪 + 响度归一化 | `0` |
| `BATCH_ANALYZE_MAX_WORKERS` | 批量分析并发数 | `2` |
| `HOST` / `PORT` | 监听地址 / 端口 | `127.0.0.1` / `5000` |
| `RISK_FALLBACK_*` | 视觉风控兜底模型（可选，须为视觉模型） | - |

## 📡 主要 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/upload` `/upload_batch` `/upload_url` | 上传 / 批量 / URL 导入（含上传预检） |
| `POST` | `/upload_chunk_init` `/upload_chunk` `/upload_chunk_finalize` | 初始化、写入和完成磁盘分片续传 |
| `POST` | `/upload_chunk_cancel` | 取消上传并删除分片会话与暂存文件 |
| `POST` | `/analysis_tasks` | 创建持久化异步任务（`single` / `batch` / `url`） |
| `GET` | `/analysis_tasks/<task_id>` | 查询任务状态与进度 |
| `GET` | `/analysis_tasks/<task_id>/result` | 获取已完成结果或失败信息 |
| `POST` | `/analysis_tasks/<task_id>/cancel` `/analysis_tasks/<task_id>/retry` | 取消 / 重试任务 |
| `POST` | `/analyze` `/analyze_batch` `/analyze_url` | 兼容旧客户端的同步分析入口 |
| `GET` | `/single_progress` `/batch_progress` | 兼容旧客户端的进度查询 |
| `POST` | `/regenerate` | 编辑步骤后重生成文档 |
| `GET` | `/history` `/history/<id>` | 历史列表 / 详情（按 client-id 隔离） |
| `GET` | `/download_zip/<dir>` `/download_subtitle/<dir>` | 下载结果 / 字幕 |

旧版同步分析与进度端点继续保持兼容；新接入建议使用 `/analysis_tasks` 持久任务接口，以便在刷新或后端重启后恢复状态。

## 📂 输出目录

```text
outputs/<video_stem>_<timestamp>/
├─ operation_guide.md / .pdf   # 文档
├─ steps.json                  # 结构化步骤
├─ <字幕>.srt / .vtt / .txt
└─ images/step_XX.jpg          # 步骤截图
```

跨视频共享产物：`outputs/hotwords_glossary.txt`（自学习热词，下次转写自动回灌）、`outputs/subtitle_corrections.jsonl`（纠错复查日志）。

结果 ZIP 会收集 Markdown、生成成功时的 PDF、`steps.json`、`images/` 下的步骤截图和可用的 SRT/VTT/TXT 字幕导出；原视频不会打入结果 ZIP。

## 🧪 提示

- 先在 `.env` 配好模型参数，再调前端
- 字幕不准时：升级 `WHISPER_MODE` → 开 `WHISPER_PREPROCESS_AUDIO` → 配 `WHISPER_HOTWORDS`
- 超长视频优先裁剪，而非强行提高并发
- URL 导入遇风控页时补 cookies 或代理
- 可选：`pip install playwright && playwright install chromium` 增强动态页抓取
