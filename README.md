# 🎬 视频转文档项目（API + web-react）

将视频自动整理为结构化步骤文档，输出 `Markdown`、`PDF` 和关键截图。  
本仓库支持两种使用方式：

1. 页面使用（后端 API + web-react 前端）
2. 单代码调用（直接使用 `video_analyzer_agent.py`）

---

## 📦 环境要求

- Python `3.10+`
- Node.js `18+`（建议 `20+`）
- 可用的模型 API Key（Ark/OpenAI 兼容接口）
- `ffmpeg`（代码会优先使用 `imageio-ffmpeg` 自动提供的二进制）

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

---

## 方式一：页面使用方法（推荐）

### 1) 安装前端依赖

```bash
cd web-react
npm install
```

### 2) 启动后端 API（5000）

```bash
python app.py
```

### 3) 启动前端（5173）

```bash
cd web-react
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

### 4) 打开页面

- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:5000`

### 5) 页面操作流程

1. 右上角进入「设置」，填写：
   - 模型 API Key
   - 模型 Base URL（自定义模式必填）
   - 模型名称（必填）
2. 上传视频（支持单个/批量、分片上传）。
3. 点击分析，等待步骤、文档和截图生成。
4. 可在页面编辑步骤并重新生成文档。
5. 在历史记录中查看、删除、下载 ZIP。

---

## 方式二：单代码 `video_analyzer_agent.py` 使用方法

适合你在脚本/服务中直接集成，不依赖前端页面。

### 1) 准备配置（可选 `.env`）

可在项目根目录创建 `.env`：

```env
MODEL_API_KEY=your_api_key
MODEL_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
MODEL_NAME=doubao-seed-2-0-pro-260215
```

`VideoAnalyzerAgent` 会按优先级读取：

- 传入参数 `api_key`
- `MODEL_API_KEY`
- `ARK_API_KEY`
- `OPENAI_API_KEY`

### 2) 最小可运行示例

新建 `run_agent_example.py`：

```python
import asyncio
from pathlib import Path

from video_analyzer_agent import VideoAnalyzerAgent


async def main():
    video_path = "demo.mp4"  # 改成你的视频路径
    out_dir = Path("outputs/demo_manual")
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"

    agent = VideoAnalyzerAgent(
        api_key=None,  # 优先从 .env 读取；也可直接传字符串
        whisper_model="base",
        model_name=None,      # 可留空，使用默认或 .env
        model_base_url=None,  # 可留空，使用默认或 .env
    )

    # 1) 生成字幕
    srt_path = agent.generate_subtitles(video_path, output_dir=str(out_dir))

    # 2) 基于字幕提取步骤（更省）
    steps = await agent.analyze_subtitles(srt_path)

    # 如果你想直接让模型看视频，可改用：
    # steps = await agent.analyze_video(video_path, fps=1.0)

    # 3) 生成步骤截图
    agent.generate_screenshots_from_steps(video_path, steps, output_dir=str(images_dir))

    # 4) 可选：低置信度步骤看图增强
    steps = await agent.enhance_steps_with_vision(
        steps=steps,
        image_dir=str(images_dir),
        srt_path=srt_path,
        max_calls=10,
    )

    # 5) 生成 Markdown
    md_path = out_dir / "operation_guide.md"
    await agent.generate_step_document(
        steps=steps,
        output_path=str(md_path),
        srt_path=srt_path,
        image_dir="images",   # markdown 中图片相对目录
        web_search=False,     # 开启需平台支持联网搜索
        respect_step_content=False,
    )

    # 6) 生成 PDF + 保存步骤 JSON
    pdf_path = out_dir / "operation_guide.pdf"
    agent.generate_pdf(str(md_path), str(pdf_path))
    agent.save_results(steps, str(out_dir / "steps.json"))

    print("完成：", out_dir.resolve())


if __name__ == "__main__":
    asyncio.run(main())
```

运行：

```bash
python run_agent_example.py
```

### 3) 常用方法说明（`VideoAnalyzerAgent`）

- `generate_subtitles(video_path, output_dir)`：视频转 SRT
- `analyze_subtitles(srt_path)`：从字幕提取步骤
- `analyze_video(video_path, fps=1.0)`：直接看视频提取步骤
- `generate_screenshots_from_steps(video_path, steps, output_dir)`：按步骤截图
- `enhance_steps_with_vision(steps, image_dir, srt_path, max_calls)`：低置信度步骤增强
- `generate_step_document(...)`：生成 Markdown 文档
- `generate_pdf(md_path, pdf_path)`：Markdown 转 PDF
- `save_results(steps, output_path)`：保存步骤 JSON

---

## 🧪 前端构建命令

```bash
cd web-react
npm run build
npm run preview
```

---

## ❗常见问题

1. 模型连接 401 / invalid_api_key
   - API Key 无效，或 Key 与 Base URL 不匹配。
2. 模型连接 404 / model not found
   - 模型名或 Base URL 错误，或账号无权限访问该模型。
3. “请输入 API Key”
   - 在页面设置中填写，或在 `.env` 配置 `MODEL_API_KEY`。
4. 字幕/截图失败
   - 检查视频格式、ffmpeg/whisper 是否可用。
