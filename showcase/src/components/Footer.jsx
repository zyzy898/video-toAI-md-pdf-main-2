import Brand from './Brand.jsx';

export default function Footer() {
  return (
    <footer>
      <div className="container">
        <Brand as="div" />
        <p style={{ margin: '0.3rem 0' }}>AI 视频内容分析 · 自动生成结构化 Markdown / PDF 文档</p>
        <p style={{ margin: '0.3rem 0', color: 'var(--vi-text-3)' }}>
          基于 Flask + React 19 + Whisper + LLM 多 Provider 抽象 · 静态效果展示页面
        </p>
      </div>
    </footer>
  );
}
