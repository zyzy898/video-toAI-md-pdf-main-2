import { useMemo, useRef, useState, useCallback } from 'react';
import {
  CheckListIcon,
  CheckIcon,
  FileIcon,
  DownloadIcon,
  SubtitleIcon
} from '../icons/Icons.jsx';
import { resultSteps, subtitleRows } from '../../data/steps.js';

/**
 * 把一段文本按关键词拆成片段：匹配的会单独包到一个 mark 节点中。
 * 关键词为空 / 文本不含关键词时，原样返回单一片段（mark=false）。
 */
function splitByKeyword(text, keyword) {
  if (!keyword) return [{ text, mark: false }];
  const parts = [];
  let i = 0;
  const lower = text.toLowerCase();
  const k = keyword.toLowerCase();
  while (i < text.length) {
    const found = lower.indexOf(k, i);
    if (found === -1) {
      parts.push({ text: text.slice(i), mark: false });
      break;
    }
    if (found > i) parts.push({ text: text.slice(i, found), mark: false });
    parts.push({ text: text.slice(found, found + keyword.length), mark: true });
    i = found + keyword.length;
  }
  return parts;
}

export default function Result() {
  const [keyword, setKeyword] = useState('点击');
  const [activeStepId, setActiveStepId] = useState(null);
  const mdContainerRef = useRef(null);

  // 字幕匹配统计：有匹配的整行数
  const matchedCount = useMemo(() => {
    if (!keyword) return 0;
    const k = keyword.toLowerCase();
    return subtitleRows.reduce(
      (acc, r) => acc + (r.text.toLowerCase().includes(k) ? 1 : 0),
      0
    );
  }, [keyword]);

  // 把每行字幕预先拆成 parts，避免每次 render 都计算
  const decoratedSubs = useMemo(
    () => subtitleRows.map((row) => ({ ...row, parts: splitByKeyword(row.text, keyword) })),
    [keyword]
  );

  // 点击左侧步骤 → 平滑滚动右侧 Markdown 内对应 heading
  const onStepClick = useCallback((step) => {
    const container = mdContainerRef.current;
    if (!container) return;
    const target = container.querySelector(`[data-anchor="${step.id}"]`);
    if (!target) return;
    setActiveStepId(step.id);
    // 用 container 的 scrollTop 而不是 scrollIntoView，避免触发整页滚动
    const containerRect = container.getBoundingClientRect();
    const targetRect = target.getBoundingClientRect();
    const offset = targetRect.top - containerRect.top + container.scrollTop - 8;
    container.scrollTo({ top: offset, behavior: 'smooth' });
  }, []);

  // 用键盘 Enter / Space 也能触发
  const onStepKeyDown = (e, step) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onStepClick(step);
    }
  };

  return (
    <section id="result">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">REAL OUTPUT SAMPLE</span>
          <h2 className="section-title">分析结果 · 真实输出样例</h2>
          <p className="section-sub">
            一份典型的"产品操作演示"分析结果：步骤、截图、Markdown 文档与字幕工作台一站式呈现。
          </p>
        </div>

        <div className="result-grid">
          {/* Steps + thumbnails */}
          <div className="result-card">
            <div className="card-head">
              <div className="card-title">
                <span className="card-title-ico">
                  <CheckListIcon />
                </span>
                识别到的步骤
              </div>
              <span className="status status--ok">
                <CheckIcon />
                质量分 0.92
              </span>
            </div>

            <div className="steps-list">
              {resultSteps.map((s) => (
                <div
                  key={s.id}
                  className={`step-item${activeStepId === s.id ? ' is-active' : ''}`}
                  role="button"
                  tabIndex={0}
                  aria-label={`定位到步骤：${s.title}`}
                  onClick={() => onStepClick(s)}
                  onKeyDown={(e) => onStepKeyDown(e, s)}
                >
                  <img className="step-thumb" src={s.thumb} alt={s.alt} loading="lazy" />
                  <div>
                    <div className="step-meta">
                      <span className="step-tag">{s.tag}</span>
                      <span className="step-time">{s.time}</span>
                    </div>
                    <h4 className="step-h">{s.title}</h4>
                    <p className="step-p">{s.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Markdown preview */}
          <div className="result-card">
            <div className="card-head">
              <div className="card-title">
                <span className="card-title-ico">
                  <FileIcon />
                </span>
                生成的总结文档
              </div>
              <button className="btn" style={{ fontSize: '0.76rem', padding: '0.4rem 0.7rem' }}>
                <DownloadIcon />
                下载 ZIP
              </button>
            </div>
            <div className="md" ref={mdContainerRef}>
              <h1>产品操作演示 · 完整使用指南</h1>
              <blockquote>
                本文档由 <strong>Video Insights</strong> 自动生成。原视频时长约 <code>03:24</code>，识别 6
                个核心操作步骤，附 4 张关键截图。
              </blockquote>

              <h2>📖 概述</h2>
              <p>
                本视频演示了如何使用客户端从零完成首次项目分析，覆盖账号登录、项目创建、分析参数配置、结果回看与编辑导出五个主要场景。
              </p>

              <h2>🎯 关键要点</h2>
              <ul>
                <li>
                  登录后建议立即在设置中开启 <strong>多设备绑定</strong>，避免后续切换设备频繁验证。
                </li>
                <li>
                  素材导入后会自动生成预览缩略图，<strong>缩略图加载即代表素材就绪</strong>。
                </li>
                <li>
                  分析参数中"视频理解"成本更高但准确度更好，<strong>建议短视频开启</strong>。
                </li>
                <li>历史抽屉按客户端隔离，本机历史不会与其他设备混淆。</li>
              </ul>

              <h2>📝 操作步骤</h2>

              {resultSteps.map((s) => (
                <div
                  key={s.id}
                  data-anchor={s.id}
                  className={`md-step${activeStepId === s.id ? ' md-step--active' : ''}`}
                >
                  <h3>{s.heading}</h3>
                  <p>{s.desc}</p>
                  <p>
                    <code>📍 时间点：{s.time}</code>
                  </p>
                </div>
              ))}

              <hr />

              <h2>🧾 文档信息</h2>
              <ul>
                <li>
                  生成时间：<code>2026-05-13 21:54</code>
                </li>
                <li>分析模式：字幕模式 + 视觉增强</li>
                <li>
                  输出目录：<code>{'outputs/<video>_<timestamp>/'}</code>
                </li>
                <li>包含资源：operation_guide.md · operation_guide.pdf · steps.json · 4 张截图 · 字幕 SRT / VTT / TXT</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Subtitle workbench */}
        <div className="result-card" style={{ marginTop: '1.4rem' }}>
          <div className="card-head">
            <div className="card-title">
              <span className="card-title-ico">
                <SubtitleIcon />
              </span>
              字幕工作台
            </div>
            <div style={{ display: 'flex', gap: '0.45rem' }}>
              {['SRT', 'VTT', 'TXT'].map((fmt) => (
                <button
                  key={fmt}
                  className="btn"
                  style={{ fontSize: '0.74rem', padding: '0.36rem 0.65rem' }}
                >
                  导出 {fmt}
                </button>
              ))}
            </div>
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.7rem',
              marginBottom: '0.7rem',
              flexWrap: 'wrap'
            }}
          >
            <input
              className="input"
              style={{ maxWidth: '320px', minWidth: '200px' }}
              placeholder="搜索字幕内容或时间点"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
            />
            <p style={{ margin: 0, color: 'var(--vi-text-3)', fontSize: '0.78rem' }}>
              共 {subtitleRows.length} 行 · 匹配{' '}
              <span style={{ color: 'rgba(165, 243, 252, 0.95)', fontWeight: 600 }}>
                {matchedCount}
              </span>{' '}
              行
            </p>
          </div>
          <div className="subtitles">
            {decoratedSubs.map((row) => {
              const hasMatch = row.parts.some((p) => p.mark);
              return (
                <div key={row.time} className={`sub-row${hasMatch ? ' sub-row--matched' : ''}`}>
                  <span className="sub-time">{row.time}</span>
                  <p className="sub-text">
                    {row.parts.map((p, i) =>
                      p.mark ? <mark key={i}>{p.text}</mark> : <span key={i}>{p.text}</span>
                    )}
                  </p>
                </div>
              );
            })}
          </div>
        </div>

        {/* Progress dialog */}
        <div className="progress-card">
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '0.6rem'
            }}
          >
            <h3 style={{ margin: 0, fontSize: '0.98rem', fontWeight: 600, color: 'var(--vi-text-0)' }}>
              处理中...
            </h3>
            <span className="status status--run">72%</span>
          </div>
          <p style={{ margin: '0.3rem 0 0', color: 'var(--vi-text-2)', fontSize: '0.86rem' }}>
            正在执行视觉增强 · 提升低置信度步骤的标题与描述...
          </p>
          <div className="progress-track">
            <div className="progress-bar"></div>
          </div>
          <div style={{ display: 'grid', gap: '0.3rem', fontSize: '0.78rem', color: 'var(--vi-text-3)' }}>
            <p style={{ margin: 0 }}>阶段：vision_enhance · 第 4/6 步</p>
            <p style={{ margin: 0, color: 'rgba(94, 234, 212, 0.9)' }}>
              当前文件：tutorial_setup_walkthrough.mp4
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
