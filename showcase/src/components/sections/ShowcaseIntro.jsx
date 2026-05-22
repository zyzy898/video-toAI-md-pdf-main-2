/**
 * /showcase 顶部的"导览"区域。
 * 作用：在不重复首页内容的前提下，给用户一个浏览路线 + 直达卡片。
 * 与 Landing 的 Hero 完全不同：没有大标题 / chips / stats，只有目录式的 5 张卡。
 */
const tourCards = [
  {
    num: '01',
    href: '#capabilities',
    title: '核心能力',
    desc: '9 张卡片速览输入 · 安全 · 分析 · 字幕 · 导出 · 模型 · 链接 · 历史 · 编辑'
  },
  {
    num: '02',
    href: '#workspace',
    title: '工作台预览',
    desc: '上传卡 · 链接直达 · 文件列表 · 进度面板 · 分析参数模拟界面'
  },
  {
    num: '03',
    href: '#pipeline',
    title: '处理链路',
    desc: '从上传到导出 · 七步法 + 终态卡 · 背后流光轨道'
  },
  {
    num: '04',
    href: '#result',
    title: '真实输出',
    desc: '识别步骤 · Markdown 文档 · 字幕工作台 · 进度对话框'
  },
  {
    num: '05',
    href: '#tech',
    title: '技术栈与工程化',
    desc: '6 张技术栈卡 + 12 张工程化优化卡片，覆盖端到端落地实践'
  }
];

export default function ShowcaseIntro() {
  return (
    <section id="intro" className="showcase-intro section-reveal section-reveal--up">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">DEMO TOUR</span>
          <h2 className="section-title">完整效果演示 · 跟我一起看</h2>
          <p className="section-sub">
            下面分 5 个模块呈现项目的核心能力、工作台界面、端到端处理链路、真实输出样例与底层技术栈。可依次往下浏览，也可点卡片直达任一模块。
          </p>
        </div>

        <div className="tour-grid">
          {tourCards.map((c) => (
            <a key={c.href} href={c.href} className="tour-card">
              <span className="tour-card-num">{c.num}</span>
              <h3 className="tour-card-title">{c.title}</h3>
              <p className="tour-card-desc">{c.desc}</p>
              <span className="tour-card-arrow" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="5" y1="12" x2="19" y2="12" />
                  <polyline points="13 6 19 12 13 18" />
                </svg>
              </span>
            </a>
          ))}
        </div>
      </div>
    </section>
  );
}
