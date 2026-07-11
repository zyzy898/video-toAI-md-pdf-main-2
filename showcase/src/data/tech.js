/**
 * 技术栈卡片 · 6 张。
 */
export const techCards = [
  {
    cls: 'tc-frontend',
    emoji: '🖥️',
    section: 'FRONTEND',
    name: '前端工作台',
    count: 9,
    summary: 'React 19 + TypeScript 构建工作台；Tailwind 4 与原生 CSS 变量并存的设计系统。',
    items: [
      { label: 'React 19', accent: true },
      { label: 'TypeScript 5', accent: true },
      { label: 'Vite 5' },
      { label: 'Tailwind CSS 4' },
      { label: 'marked' },
      { label: 'DOMPurify' },
      { label: 'motion / react' },
      { label: 'localStorage' },
      { label: 'X-Client-ID' }
    ]
  },
  {
    cls: 'tc-backend',
    emoji: '🧠',
    section: 'BACKEND',
    name: '后端 API 服务',
    count: 7,
    summary: 'Flask 主框架 + Waitress WSGI；提供分片续传、会话管理与定时清理。',
    items: [
      { label: 'Flask', accent: true },
      { label: 'Waitress', accent: true },
      { label: 'python-dotenv' },
      { label: '分片续传' },
      { label: '会话管理' },
      { label: '请求级隔离' },
      { label: '定时清理' }
    ]
  },
  {
    cls: 'tc-video',
    emoji: '🎞️',
    section: 'VIDEO',
    name: '视频处理引擎',
    count: 10,
    summary: 'faster-whisper（CTranslate2）常驻转写 + FFmpeg 抽帧 / 压缩 / 切片；音频降噪、热词自学习、LLM 同音字纠错多层提升字幕精度。',
    items: [
      { label: 'faster-whisper', accent: true },
      { label: 'CTranslate2', accent: true },
      { label: 'ffmpeg-python' },
      { label: 'imageio-ffmpeg' },
      { label: '动态抽帧' },
      { label: '音频降噪归一化' },
      { label: 'jieba 热词自学习' },
      { label: 'LLM 同音字纠错' },
      { label: '长视频压缩' },
      { label: '字幕缓存' }
    ]
  },
  {
    cls: 'tc-doc',
    emoji: '🧩',
    section: 'DOCUMENT',
    name: '文档生成',
    count: 6,
    summary: '输出 Markdown、字幕与步骤 JSON，并在 PDF 生成成功时附带 PDF；中文字体支持跨平台适配。',
    items: [
      { label: 'markdown', accent: true },
      { label: 'fpdf2', accent: true },
      { label: '中文字体自适配' },
      { label: 'steps.json' },
      { label: 'SRT · VTT · TXT' },
      { label: '确定性兜底' }
    ]
  },
  {
    cls: 'tc-url',
    emoji: '🌐',
    section: 'URL IMPORT',
    name: '智能链接导入',
    count: 6,
    summary: 'B 站 / 抖音 / 小红书专属解析；通用页面靠浏览器抓取 + 模型识别 + yt-dlp 多层兜底。',
    items: [
      { label: 'scrapling', accent: true },
      { label: 'yt-dlp', accent: true },
      { label: '平台下载器' },
      { label: 'Playwright 隐身会话' },
      { label: 'JSON-LD / meta 解析' },
      { label: 'Cookies / 代理' }
    ]
  },
  {
    cls: 'tc-llm',
    emoji: '🔌',
    section: 'LLM',
    name: '三类模型路由',
    count: 3,
    summary: '统一抽象按 Ark、OpenAI、OpenAI 兼容三类路由；DeepSeek、Qwen 可作为兼容端点示例。',
    items: [
      { label: 'Ark · Doubao', accent: true },
      { label: 'OpenAI', accent: true },
      { label: 'OpenAI 兼容（DeepSeek / Qwen 等）' }
    ]
  }
];
