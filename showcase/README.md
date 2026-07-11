# Video Insights · 项目效果展示页

这是一个用于"项目效果展示"的 React 单页应用，沿用与 React Bits 的 `<DarkVeil />`
组件相同的技术栈（**React 19 + Vite + 原生 CSS + ogl + react-router-dom**），
首页是一个全屏 DarkVeil 的着陆页，提供「开始使用」（跳转工作台）与「观看演示」（进入完整演示内容）两个入口。

> 「开始使用」优先读取 Vite 构建变量 `VITE_APP_URL`；未配置时跳转可用的本地工作台 `http://localhost`。可在 `showcase/.env.local` 或部署环境中设置该变量。

## 路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | LandingPage | 首页着陆页：DarkVeil 全屏 + 品牌 + 主标语 + CTA（开始使用 / 观看演示） |
| `/showcase` | ShowcasePage | 详细演示：导览 / 能力 / 工作台 / Pipeline / Result / Tech |
| 其它 | → `/` | 兜底重定向 |

## 技术栈

- React 19（JSX，不引入 TypeScript，与 DarkVeil 的 JS+CSS 变体一致）
- react-router-dom 7（BrowserRouter，URL 干净）
- Vite 5
- 原生 CSS（保留原页面所有的 `--vi-*` 设计 token）
- [ogl](https://github.com/oframe/ogl) ─ DarkVeil 内部使用的 WebGL 库

## 目录结构

```
showcase/
├─ index.html                    # Vite 入口
├─ package.json
├─ vite.config.js
├─ public/
│  └─ assets/                    # 自制的步骤截图 SVG（运行时通过 /assets/... 引用）
│     ├─ step_01.svg
│     ├─ ...
│     └─ step_06.svg
└─ src/
   ├─ main.jsx
   ├─ App.jsx                    # 路由出口（BrowserRouter）
   ├─ pages/
   │  ├─ LandingPage.jsx          # /         着陆页：DarkVeil + CTA
   │  └─ ShowcasePage.jsx         # /showcase  完整演示
   ├─ styles/
   │  └─ index.css                # 全局样式 + 设计 token + 着陆页样式
   ├─ hooks/
   │  ├─ useFadeUpReveal.js       # IntersectionObserver 触发 .fade-up 动画
   │  └─ useSmoothAnchor.js       # ShowcasePage 内的锚点平滑滚动
   ├─ data/                        # 重复结构的纯数据（卡片、步骤、字幕、技术栈、工程化）
   │  ├─ capabilities.jsx
   │  ├─ pipeline.js
   │  ├─ steps.js
   │  ├─ tech.js
   │  ├─ engineering.jsx
   │  └─ nav.js
   └─ components/
      ├─ DarkVeil/                # React Bits DarkVeil 组件（JS + CSS 变体）
      │  ├─ DarkVeil.jsx
      │  └─ DarkVeil.css
      ├─ icons/
      │  └─ Icons.jsx              # 所有 inline SVG 图标
      ├─ Brand.jsx
      ├─ Nav.jsx                   # 顶栏（含返回首页 Link）
      ├─ Footer.jsx
      └─ sections/
         ├─ Hero.jsx
         ├─ Capabilities.jsx
         ├─ Workspace.jsx
         ├─ Pipeline.jsx
         ├─ Result.jsx
         └─ Tech.jsx
```

## 启动

```bash
# 安装依赖
npm install

# 开发模式（默认 http://localhost:5173）
npm run dev

# 生产构建
npm run build
npm run preview
```

## 关于 DarkVeil

`<DarkVeil />` 分别由 `LandingPage.jsx` 与 `ShowcasePage.jsx` 页面组件渲染为全屏
`position: fixed` 背景层，层级为 `z-index: 0`。演示页仅在移动端通过
`.darkveil-bg::after` 叠加一层弱暗罩，提高前景文字可读性。

可调参数（详见 React Bits 官方说明）：

| Prop | Type | 当前值 |
|------|------|--------|
| hueShift | number | 210（偏向青蓝主色调） |
| speed | number | 0.6 |
| warpAmount | number | 0.18 |
| noiseIntensity / scanlineIntensity | number | 0 |
| resolutionScale | number | 1 |

## 视觉与交互保留

- 渐变标题动画、深色玻璃质感卡片、状态标签、霓虹进度条
- 顶栏移动端汉堡菜单（带 backdrop 与 Esc 关闭）
- IntersectionObserver 驱动的 `.fade-up` 渐入动画
- Capabilities 卡片的鼠标位置 spotlight 跟随
- Pipeline 背后的 SVG 流光轨道
- 完全沿用 `web-react` 的设计 token（`--vi-bg-*`, `--vi-accent-*`, `--vi-radius-*`
  等），方便未来与主项目共享样式。
