import { capabilities } from '../../data/capabilities.jsx';

/**
 * 9 个能力卡片，配合鼠标位置驱动的 spotlight 效果。
 */
export default function Capabilities() {
  const onPointerMove = (e) => {
    const card = e.currentTarget;
    const rect = card.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * 100;
    const y = ((e.clientY - rect.top) / rect.height) * 100;
    card.style.setProperty('--mx', x + '%');
    card.style.setProperty('--my', y + '%');
  };
  const onPointerLeave = (e) => {
    const card = e.currentTarget;
    card.style.removeProperty('--mx');
    card.style.removeProperty('--my');
  };

  return (
    <section id="capabilities">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">CORE CAPABILITIES</span>
          <h2 className="section-title">围绕"教程视频与操作录屏"打造</h2>
          <p className="section-sub">从上传、风控、分析到导出，每一步都为长流程视频做了优化。</p>
        </div>
        <div className="caps-wrap">
          <div className="caps-bg" aria-hidden="true"></div>
          <div className="caps">
            {capabilities.map((cap, i) => {
              const Icon = cap.Icon;
              const delayClass = i % 3 === 1 ? ' delay-1' : i % 3 === 2 ? ' delay-2' : '';
              return (
                <div
                  key={cap.title}
                  className={`cap fade-up${delayClass}`}
                  onPointerMove={onPointerMove}
                  onPointerLeave={onPointerLeave}
                >
                  <span className="cap-tag">{cap.tag}</span>
                  <div className="cap-icon">
                    <Icon />
                  </div>
                  <h3>{cap.title}</h3>
                  <p>{cap.desc}</p>
                  <div className="cap-meta">
                    {cap.tags.map((t) => (
                      <span key={t.label} className={t.accent ? 'accent' : ''}>
                        {t.label}
                      </span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
