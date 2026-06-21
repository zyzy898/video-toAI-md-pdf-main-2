import { techCards } from '../../data/tech.js';
import { engineeringCards } from '../../data/engineering.jsx';
import { techLogos } from '../../data/techLogos.jsx';
import LogoLoop from '../LogoLoop/LogoLoop.jsx';
import useTheme from '../../hooks/useTheme.js';

export default function Tech() {
  const [theme] = useTheme();
  // 跑马灯左右渐隐色需与外框背景一致，否则明主题下露出深色方块
  const logoFadeColor = theme === 'light' ? '#f8fafc' : '#0b0d14';
  return (
    <section id="tech">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">TECH STACK · ENGINEERING</span>
          <h2 className="section-title">技术栈与工程化</h2>
          <p className="section-sub">
            前端 React 19 + TypeScript + Tailwind 4；后端 Flask + faster-whisper + ffmpeg；多 LLM Provider 路由 + 多层降级。下面同时呈现真实落地的工程化优化点。
          </p>
        </div>

        {/* Tech badges */}
        <div className="tech-grid">
          {techCards.map((tc) => (
            <div key={tc.section} className={`tech-card ${tc.cls}`}>
              <div className="tech-head">
                <div className="tech-head-left">
                  <span className="tech-emoji" aria-hidden="true">
                    {tc.emoji}
                  </span>
                  <div>
                    <h3>{tc.section}</h3>
                    <p className="tech-card-name">{tc.name}</p>
                  </div>
                </div>
                <span className="tech-count">{tc.count}</span>
              </div>
              <p className="tech-summary">{tc.summary}</p>
              <ul className="tech-list">
                {tc.items.map((it) => (
                  <li key={it.label} className={it.accent ? 'accent' : ''}>
                    {it.label}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Logo loop · 在技术栈与"工程化细节"之间 */}
        <div className="tech-logos">
          <div className="tech-logos-head">
            <span className="tech-logos-tag">POWERED BY</span>
            <p className="tech-logos-sub"></p>
          </div>
          <div className="tech-logos-frame" aria-hidden="false">
            <LogoLoop
              logos={techLogos}
              speed={70}
              direction="left"
              logoHeight={36}
              gap={56}
              hoverSpeed={20}
              scaleOnHover
              fadeOut
              fadeOutColor={logoFadeColor}
              ariaLabel="Tech stack 品牌 logo 循环展示"
            />
          </div>
        </div>

        {/* Engineering optimizations */}
        <div className="engr-head">
          <span className="section-tag">ENGINEERING DETAILS</span>
          <h3>工程化优化与落地实践</h3>
          <p>从前端渲染、网络层、上传链路、长视频处理到 LLM 调用、风控与可观测性，每一处都做了真实的取舍与回退方案。</p>
        </div>

        <div className="engr-grid">
          {engineeringCards.map((card) => {
            const Icon = card.Icon;
            return (
              <div key={card.title} className="engr-card">
                <div className="engr-head-row">
                  <span className="engr-icon">
                    <Icon />
                  </span>
                  <span className="engr-title">{card.title}</span>
                </div>
                <ul>
                  {card.items.map((html, i) => (
                    <li key={i} dangerouslySetInnerHTML={{ __html: html }} />
                  ))}
                </ul>
                <div className="engr-tag-row">
                  {card.tags.map((t) => {
                    const cls = ['engr-tag', t.accent && 'accent', t.kind].filter(Boolean).join(' ');
                    return (
                      <span key={t.label} className={cls}>
                        {t.label}
                      </span>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
