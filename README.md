# 🎬 视频转文档（后端 API + web-react 独立前端）

将视频内容自动转为结构化步骤文档，输出 `Markdown`、`PDF` 与关键截图，支持单视频与批量处理。

## 📖 项目简介

本项目用于把“看视频学操作”的过程沉淀成“可复用、可检索、可编辑”的文档资产。  
系统会自动分析视频内容，识别关键步骤并生成总结文档；你也可以在前端编辑步骤后再次生成文档，形成持续迭代的知识库。

## ✨ 核心功能

- 单视频分析：上传一个视频后自动生成步骤、Markdown、PDF。
- 批量分析：多视频并行处理，统一查看结果与失败原因。
- 分片上传：支持大文件稳定上传与断点续传。
- 历史记录：支持查看、回显与删除历史分析结果。
- 文档再生成：编辑步骤后可重新生成总结文档。
- 模型连通性测试：在设置中校验 API Key、Base URL、模型名称是否可用。
- ZIP 打包下载：一键下载文档与截图资源。

## 🔄 工作流程

1. 在前端设置模型参数（API Key、Base URL、模型名称）。
2. 上传视频（单个或批量，支持分片上传）。
3. 后端执行音频转写、截图抽取与步骤分析。
4. 生成 `operation_guide.md` 与 `operation_guide.pdf`。
5. 如需优化内容，可编辑步骤并触发重新生成。
6. 在历史记录中回看结果，或下载 ZIP 归档。

## 🏗️ 当前架构

- 后端：`Flask API`（仅提供接口）
- 前端：`web-react/`（React + TypeScript + Vite + Tailwind CSS v4）
- 运行方式：前后端分离，前端通过 Vite 代理访问后端 API

## 📁 核心目录

```text
.
├─ app.py                       # Flask API 入口
├─ video_analyzer_agent.py      # 视频分析核心逻辑
├─ requirements.txt             # Python 依赖
├─ uploads/                     # 上传目录
├─ outputs/                     # 输出目录
├─ history.json                 # 历史记录
└─ web-react/
   ├─ package.json
   ├─ vite.config.ts
   └─ src/
```

## 🧰 环境要求

- Python `3.10+`
- Node.js `18+`（建议 `20+`）
- 可用的模型 API Key（ARK/OpenAI 兼容接口均可）
- ffmpeg（代码会优先使用 `imageio-ffmpeg` 自动提供的二进制）

## 🚀 快速启动

### 1) 安装后端依赖

```bash
pip install -r requirements.txt
```

### 2) 安装前端依赖

```bash
cd web-react
npm install
```

### 3) 启动后端（端口 5000）

```bash
python app.py
```

### 4) 启动前端（端口 5173）

```bash
cd web-react
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

访问地址：

- 前端页面：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:5000`

```

支持的 Key 读取优先级：

- `MODEL_API_KEY`
- `ARK_API_KEY`
- `OPENAI_API_KEY`

## 🧪 常用 API（前端已内置调用）

- `POST /upload`：单文件上传
- `POST /upload_chunk_init` / `POST /upload_chunk` / `POST /upload_chunk_finalize`：分片上传
- `POST /analyze`：单视频分析
- `POST /analyze_batch`：批量分析
- `POST /regenerate`：根据编辑后的步骤重生成文档
- `POST /test_model`：测试模型连接
- `GET /history`：历史记录列表
- `GET /history/<id>`：历史详情
- `DELETE /history/<id>`：删除历史记录
- `GET /single_progress` / `GET /batch_progress`：进度查询

## 📦 前端构建

```bash
cd web-react
npm run build
npm run preview
```

## 🛠️ 常见问题

1. 模型连接测试 404
   - 通常是 `Base URL` 填写错误。确保是提供商的 OpenAI 兼容地址（很多平台需要带 `/v1`）。
2. 生成失败或无步骤
   - 检查视频是否可解码、语音是否清晰，并确认模型可用额度与权限。


