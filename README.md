# 🎬➡️📝 视频转文档（后端 API + web-react 独立前端）

将视频自动分析为结构化步骤文档，输出 Markdown 与 PDF，支持单视频与批量处理、历史记录、步骤编辑与重生成。

## 🧩 当前架构

- 后端：`Flask`（仅提供 API）
- 前端：`web-react/`（React + TypeScript + Vite + Tailwind v4）
- 运行方式：前后端分离，前端独立启动，通过 Vite 代理转发到后端 API

## 📁 目录说明（核心）

```text
.
├─ app.py                      # Flask API 入口
├─ video_analyzer_agent.py     # 视频分析核心逻辑
├─ requirements.txt            # Python 依赖
├─ web-react/
│  ├─ package.json             # React 前端依赖与脚本
│  ├─ vite.config.ts           # 前端代理与构建配置
│  └─ src/                     # 前端源码
├─ uploads/                    # 上传目录
├─ outputs/                    # 输出目录
└─ history.json                # 历史记录
```

## ✅ 环境要求

- Python 3.10+（建议）
- Node.js 18+（建议 20+）
- 可用的 ARK API Key
- 可用的 ffmpeg 运行环境（可系统安装，或由依赖自动提供）

## 📦 安装依赖

### 后端依赖

```bash
pip install -r requirements.txt
```

### 前端依赖

```bash
cd web-react
npm install
```

## 🚀 启动说明（开发模式）

需要两个终端同时运行：

### 终端 A：启动后端 API（端口 5000）

```bash
python app.py
```

### 终端 B：启动 React 前端（端口 5173）

```bash
cd web-react
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

访问地址：

- 前端页面：`http://127.0.0.1:5173`
- 后端 API：`http://127.0.0.1:5000`

说明：`web-react/vite.config.ts` 已配置 API 代理（如 `/upload`、`/analyze`、`/history` 等），前端开发时会自动转发到后端。

## 🏗️ 生产构建（前端）

```bash
cd web-react
npm run build
npm run preview
```

后端仍可单独以 API 方式运行：

```bash
python app.py
```

## 🛠️ 常用命令

### 后端

```bash
python app.py
```

### 前端

```bash
cd web-react
npm run dev
npm run build
npm run preview
```

## 🔄 迁移说明

本仓库已切换到“后端 API + `web-react` 独立前端”模式，旧的模板渲染前端链路（如 `templates/index.html`、`static/*`、根目录旧 Vite 前端配置）不再作为当前启动方式使用。

