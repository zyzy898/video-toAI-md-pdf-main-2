# 视频总结项目（Flask API + React 前端）

将视频自动提炼为结构化步骤，并输出 `Markdown`、`PDF` 与关键截图。

项目由两部分组成：
- 后端：`app.py`（Flask，负责上传、风控、分析、导出）
- 前端：`web-react/`（React + TypeScript + Vite）

---

## 核心能力

- 视频上传：单文件、批量、分片续传
- 上传前风控：黑名单指纹 + 视觉风控 + 文本兜底
- 分析前风控：同样执行内容检测，命中策略直接阻断
- 字幕提取与步骤分析：支持 Whisper 模型选择
- 文档输出：Markdown/PDF/截图
- 历史记录与自动清理

---

## 运行架构

当前默认是单进程 Flask 应用，生产模式使用 Waitress（不是 Flask 内置开发服务器）。

- 开发模式：`FLASK_DEBUG=1` 时走 Flask dev server
- 生产模式：默认走 Waitress

启动日志示例：

```text
Starting production server with Waitress: host=127.0.0.1 port=5000 threads=4 connection_limit=100
```

含义：
- `host` / `port`：监听地址和端口
- `threads`：Waitress 处理请求的线程数
- `connection_limit`：最大并发连接数

---

## 环境要求

- Python 3.10+
- Node.js 18+（建议 20+）
- 可用模型 API Key（OpenAI 兼容接口）
- `ffmpeg`（代码会优先尝试 `imageio-ffmpeg`）

---

## 快速启动

### 1) 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2) 启动后端

```bash
python app.py
```

默认地址：`http://127.0.0.1:5000`

### 3) 启动前端

```bash
cd web-react
npm install
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

前端地址：`http://127.0.0.1:5173`

---

## 关键配置（.env）

你项目里可直接调节的核心参数如下：

```env
# 主分析
WHISPER_MODE=base
MAX_VISION=10
WEB_SEARCH=0

# 系统资源/处理
WHISPER_THREADS=4
LONG_VIDEO_PREPROCESS_ENABLED=1
SCREENSHOT_MAX_WORKERS=2

# 风控抽帧
RISK_MAX_FRAMES=4
RISK_DYNAMIC_MAX_FRAMES=8

# 批量分析并行度（新增）
BATCH_ANALYZE_MAX_WORKERS=2

# 生产服务
WAITRESS_THREADS=4
WAITRESS_CONNECTION_LIMIT=100
```

### 参数优先级（非常重要）

同一参数的生效顺序：
1. 请求体显式传参
2. `.env` 默认值

例如：
- 主分析：`whisper_model/whisper_mode`、`max_vision`、`web_search`
- 批量并行：`BATCH_ANALYZE_MAX_WORKERS` 仅由 `.env` 管理员配置生效（不支持请求体临时覆盖）

---

## 风控流程（当前实现）

### 上传前风控

1. 文件进入 `uploads/.staging`
2. 黑名单指纹比对（SHA-256）
3. 命中则直接拒绝
4. 未命中继续视觉风控
5. 视觉不可用时先尝试系统级视觉兜底
6. 兜底也不可用时，触发文本兜底（字幕关键词）
7. 通过后才移动到正式 `uploads/`

### 分析前风控

分析接口在正式分析前同样执行风控，命中拦截直接返回，不继续后续文档生成。

---

## 批量分析并行（新增）

`/analyze_batch` 已从串行改为并行执行，并发仅由 `.env` 控制：

- 环境变量：`BATCH_ANALYZE_MAX_WORKERS`
- 实际值会自动限制在：
  - 最小 1
  - 最大 16
  - 不超过 CPU 核心数
  - 不超过本次文件数

响应中会返回本次实际并发值：

```json
{
  "batch_parallel_workers": 2
}
```

---

## 资源建议（4 核 CPU / 8G 内存）

建议默认值：
- `BATCH_ANALYZE_MAX_WORKERS=2`
- `WHISPER_THREADS=2~4`（更稳建议 2）
- `SCREENSHOT_MAX_WORKERS=2`
- `RISK_MAX_FRAMES=4`
- `RISK_DYNAMIC_MAX_FRAMES=8`

如果出现 CPU 长时间 90%+：
1. 先把 `BATCH_ANALYZE_MAX_WORKERS` 降到 1~2
2. 再把 `WHISPER_THREADS` 降到 2
3. 保持风控抽帧在 4/8

---

## 常见接口

- `POST /upload`：单文件上传（含风控）
- `POST /upload_batch`：批量上传（逐文件风控）
- `POST /upload_chunk_init` / `POST /upload_chunk` / `POST /upload_chunk_finalize`：分片上传
- `POST /analyze`：单文件分析
- `POST /analyze_batch`：批量分析（并行）
- `GET /single_progress` / `GET /batch_progress`：进度查询
- `POST /download_batch_zip`：批量结果打包下载

---

## 常见问题

1. 上传被拦截（`content_policy_violation`）
- 表示命中风控策略，不会入正式上传目录。

2. 模型鉴权失败（401/403）
- 检查 `api_key`、`model_name`、`model_base_url` 是否匹配。

3. 批量分析机器卡顿
- 优先降低 `BATCH_ANALYZE_MAX_WORKERS` 与 `WHISPER_THREADS`。

4. `risk_keyword_lexicon.json` 词库异常
- 文件格式错误会导致文本风控回退默认空词库，建议保持 UTF-8 且 JSON 合法。

---

## 版本记录

详细变更请查看：[updata.md](updata.md)
