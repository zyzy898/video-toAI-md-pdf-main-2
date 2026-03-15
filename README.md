# 视频总结项目（Flask API + React 前端）

将视频自动提取为结构化步骤，并输出 `Markdown`、`PDF` 与关键截图。

项目由两部分组成：
- 后端：`app.py`（Flask，上传/分析/风控/下载）
- 前端：`web-react/`（React + TypeScript + Vite）

---

## 核心能力

- 视频上传（单文件、批量、分片续传）
- 字幕分析 / 画面分析
- 自动生成步骤文档（Markdown + PDF）
- 历史记录查看、重生成文档、批量打包下载

---

## v2.0.0 新增与升级

### 1) 无人工复审风控链路（自动分级）
- 后端增加自动风控分级：`allow / restrict / block`
- 风控结果标准化返回：`decision`、`risk_level`、`reason_code`、`reason`、`scores`
- 命中策略时返回 `403`，并附 `code=content_policy_violation` 与结构化 `risk` 数据

### 2) 上传前置风控（阻止入库）
- 上传先进入 `uploads/.staging`，风控通过后才移动到正式 `uploads/`
- 命中风控直接拒绝，不进入正式上传目录
- 支持单文件、分片 finalize、批量上传的统一拒绝策略

### 3) 分片上传“内存优先”
- 分片会话增加 `storage_mode`：`memory` / `disk`
- 小文件优先内存缓存，减少中间 `.part` 落盘
- 超过阈值自动回退到磁盘模式

默认阈值（见 `app.py`）：
- 单文件内存模式上限：`64MB`
- 全局内存缓冲上限：`256MB`

### 4) 前端风控提示增强
- 前端统一解析 `error/code/risk`
- 单个分析、批量分析、上传失败场景都会展示可读风控信息

### 5) pre-commit 自动检查（提交前）
- 新增 `.pre-commit-config.yaml`
- 新增自定义检查脚本：
  - `scripts/check_mojibake.py`（中文乱码/编码异常扫描）
  - `scripts/check_py_compile.py`（Python 语法编译检查）

---

## 项目结构

```text
.
├─ app.py
├─ video_analyzer_agent.py
├─ requirements.txt
├─ .pre-commit-config.yaml
├─ scripts/
│  ├─ check_mojibake.py
│  └─ check_py_compile.py
└─ web-react/
   ├─ src/
   ├─ components/
   ├─ package.json
   └─ vite.config.ts
```

---

## 环境要求

- Python `3.10+`
- Node.js `18+`（建议 `20+`）
- 可用模型 API Key（ARK/OpenAI 兼容接口）
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

## 模型配置

前端设置页或请求参数中可配置：
- `api_key`
- `model_name`
- `model_base_url`

`VideoAnalyzerAgent` 的 Key 读取优先级：
1. 显式传入参数
2. `MODEL_API_KEY`
3. `ARK_API_KEY`
4. `OPENAI_API_KEY`

---

## 风控流程说明（无人工复审）

### 单文件上传
1. 文件先写入 `uploads/.staging`
2. 后端执行风控
3. 命中策略：删除暂存并 `403` 拒绝
4. 通过：移动到 `uploads/`

### 分片上传
1. `upload_chunk_init` 建立会话并决定 `storage_mode`
2. `upload_chunk` 写入内存或 `.part`
3. `upload_chunk_finalize` 组装到 `.staging`
4. 执行风控后决定拒绝或入库

### 分析接口
1. `process_video` 先执行风控抽帧判定
2. 命中策略直接返回 `403`
3. 通过后才继续字幕/步骤/文档流程

---

## pre-commit 使用（建议启用）

### 安装

```bash
pip install pre-commit
```

如果系统 Python 权限受限，建议在项目本地虚拟环境中安装：

```bash
python -m venv .venv
.venv\Scripts\python -m pip install pre-commit
```

### 启用 Git Hook

```bash
pre-commit install
```

如果使用本地虚拟环境：

```bash
.venv\Scripts\pre-commit install
```

### 手动执行全部检查

```bash
pre-commit run --all-files
```

---

## 常见问题

1. `401 invalid_api_key`
- API Key 无效，或与 `Base URL` / 模型平台不匹配

2. `404 model not found`
- 模型名称或 Base URL 错误，或账号无权限

3. 上传被风控拒绝（`content_policy_violation`）
- 视频命中自动风控策略，系统按无人工复审流程直接拒绝

4. 分片会话过期
- 内存模式下服务重启后无法恢复缓存，需要重新上传

---

## 构建前端

```bash
cd web-react
npm run build
npm run preview
```
