# Video Insights · 静态效果展示页

这是一个用于"项目效果展示"的纯静态页面，零依赖，可直接双击 `index.html` 在浏览器打开，
也可以部署到 GitHub Pages / Netlify / 任何静态托管。

## 目录

```
showcase/
├─ index.html        # 单文件展示页
├─ assets/
│  ├─ step_01.svg    # 自制 UI 模拟图 · 账号登录
│  ├─ step_02.svg    # 自制 UI 模拟图 · 新建项目导入素材
│  ├─ step_03.svg    # 自制 UI 模拟图 · 分析参数配置
│  ├─ step_04.svg    # 自制 UI 模拟图 · 启动分析查看进度
│  ├─ step_05.svg    # 自制 UI 模拟图 · 历史抽屉
│  └─ step_06.svg    # 自制 UI 模拟图 · 编辑步骤后重生成
└─ README.md
```

## 包含内容

- Hero 标题、副标题、能力标签、CTA、关键统计数据
- 9 个核心能力卡片
- 工作台 UI 预览（顶栏、Hero、上传卡、URL 直达、文件列表、批量进度）
- 7 阶段端到端处理链路
- 真实输出样例：步骤列表 + Markdown 预览 + 字幕工作台 + 进度对话框
- 技术栈分组（前端 / 后端 / 视频处理 / 文档生成 / URL 导入 / LLM Provider）
- 平滑滚动 + IntersectionObserver 渐入动画

## 视觉与交互

- 完全沿用 `web-react` 的设计 token（`--vi-bg-*`, `--vi-accent-*`, `--vi-radius-*` 等）
- 渐变标题动画、深色玻璃质感卡片、状态标签、霓虹进度条
- 所有图片都是 SVG 矢量自制 UI 模拟，**不引用任何真实视频帧或截图**

## 如何打开

```bash
# 直接打开
start showcase\index.html

# 或起一个本地静态服务（任意一种）
python -m http.server 8000 -d showcase
# 然后访问 http://localhost:8000
```
