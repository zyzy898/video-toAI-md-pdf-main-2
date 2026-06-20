import {
  PlayIcon,
  UploadIcon,
  ClockIcon,
  SettingsIcon,
  InboxIcon,
  CheckIcon,
  SubtitleIcon,
  EditIcon
} from '../icons/Icons.jsx';

const chips = ['Whisper ASR', '批量处理', 'Markdown · PDF', '链接直达'];

const kvProgress = [
  { label: '阶段', value: 'vision_enhance', help: '视觉增强标题与描述' },
  { label: '已完成', value: '2 个', help: '输出包就绪可下载', valueColor: '#6ee7b7' },
  { label: '失败', value: '0 个', help: '超长视频会自动降级', valueColor: '#fda4af' },
  {
    label: '当前文件',
    value: 'product_demo…',
    help: '视觉增强 · 第 4/6 步',
    valueStyle: { fontSize: '0.8rem', color: 'rgba(165, 243, 252, 0.95)' }
  }
];

const kvAnalysis = [
  { label: 'Provider', value: 'Ark · Doubao' },
  { label: 'Whisper', value: 'base' },
  { label: '视觉增强', value: '最多 10 次' },
  { label: '视频模式', value: '字幕分析' }
];

export default function Workspace() {
  return (
    <section id="workspace">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">WORKSPACE PREVIEW</span>
          <h2 className="section-title">前端工作台 · 实际界面预览</h2>
          <p className="section-sub">
            React 19 + TypeScript + Vite + Tailwind 4 构建。深色科技感视觉，支持移动性能模式自动降级。
          </p>
        </div>

        <div className="workspace fade-up">
          <div className="ws-titlebar">
            <div className="ws-traffic">
              <span></span>
              <span></span>
              <span></span>
            </div>
            <div className="ws-url">https://localhost — Video Insights · AI 视频理解工作台</div>
            <div style={{ width: '60px' }}></div>
          </div>
          <div className="ws-body">
            {/* Mocked nav */}
            <div className="ws-mock-nav">
              <span className="ws-mock-nav-brand">
                <span
                  className="brand-logo"
                  style={{ width: '1.6rem', height: '1.6rem', borderRadius: '0.45rem' }}
                >
                  <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </span>
                Video Insights
              </span>
              <div className="nav-links">
                <span className="nav-pill">
                  <SettingsIcon className="ico-sm" />
                  设置
                </span>
                <span className="nav-pill nav-pill--accent">
                  <ClockIcon className="ico-sm" />
                  历史
                </span>
              </div>
            </div>

            {/* Inner hero */}
            <div className="ws-hero">
              <span className="eyebrow">AI · 视频理解工作台</span>
              <h2 className="ws-hero-title">
                视频转文档，<span className="accent-text">不止提取，更是理解</span>
              </h2>
              <p className="ws-hero-sub">
                AI 自动分析视频内容，抓取关键截图，拆解核心步骤，输出结构清晰、重点明确的总结文档。
              </p>
              <div className="hero-chips" style={{ marginTop: '1.1rem' }}>
                {chips.map((c) => (
                  <span key={c} className="chip">
                    <span className="chip-dot"></span>
                    {c}
                  </span>
                ))}
              </div>
            </div>

            {/* Two-col grid */}
            <div className="ws-grid ws-grid--two">
              {/* Upload card */}
              <div className="panel" style={{ padding: '1.1rem' }}>
                <div className="card-head">
                  <div className="card-title">
                    <span className="card-title-ico">
                      <UploadIcon />
                    </span>
                    上传视频
                  </div>
                  <span className="card-sub">拖拽 · 点击 · 链接 · 批量</span>
                </div>

                <div className="url-bar" style={{ marginBottom: '0.85rem' }}>
                  <div className="url-bar-title">
                    <span aria-hidden="true">🔗</span> 视频链接直达分析
                  </div>
                  <div className="url-bar-row">
                    <input
                      className="input"
                      placeholder="粘贴视频链接（http/https）"
                      defaultValue="https://www.bilibili.com/video/BV1xx411c7mD"
                      readOnly
                    />
                    <button
                      className="btn"
                      style={{ fontSize: '0.78rem', padding: '0.5rem 0.85rem' }}
                    >
                      导入链接
                    </button>
                    <button
                      className="btn btn--primary"
                      style={{ fontSize: '0.78rem', padding: '0.5rem 0.85rem' }}
                    >
                      链接直达分析
                    </button>
                  </div>
                </div>

                <div className="drop">
                  <div className="drop-icon">
                    <InboxIcon />
                  </div>
                  <p className="drop-title">点击选择 · 或拖拽视频到这里</p>
                  <p className="drop-hint">支持 MP4 / AVI / MOV / MKV / WMV / FLV / WebM / M4V 等</p>
                </div>

                <div className="files" style={{ marginTop: '0.85rem' }}>
                  <FileRow
                    name="tutorial_setup_walkthrough.mp4"
                    info="分析完成 · 6 步骤 · 4 张截图 · 字幕 132 行"
                    state="ok"
                  />
                  <FileRow
                    name="product_demo_release_notes.mp4"
                    info="阶段：视觉增强中 · 进度 64%"
                    state="run"
                  />
                  <FileRow
                    name="onboarding_screencast_v3.mov"
                    info="已上传 · 等待批次启动"
                    state="idle"
                  />
                </div>

                <div className="cta-row">
                  <button className="btn btn--primary">
                    <PlayIcon />
                    开始分析（3 个文件）
                  </button>
                </div>
              </div>

              {/* Right col: progress + analysis params */}
              <div className="panel" style={{ padding: '1.1rem' }}>
                <div className="card-head">
                  <div className="card-title">
                    <span className="card-title-ico">
                      <ClockIcon />
                    </span>
                    分析进度
                  </div>
                  <span className="status status--run">运行中</span>
                </div>

                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '0.45rem'
                  }}
                >
                  <span style={{ fontSize: '0.84rem', color: 'var(--vi-text-1)', fontWeight: 600 }}>
                    批量分析进行中
                  </span>
                  <span
                    style={{
                      fontSize: '0.86rem',
                      color: 'rgba(165, 243, 252, 0.95)',
                      fontWeight: 600
                    }}
                  >
                    64%
                  </span>
                </div>
                <p style={{ margin: 0, color: 'var(--vi-text-2)', fontSize: '0.82rem' }}>
                  当前阶段：低置信度步骤视觉增强 · 2/3 文件
                </p>
                <div className="progress-track" style={{ marginTop: '0.85rem' }}>
                  <div className="progress-bar" style={{ width: '64%', animation: 'none' }}></div>
                </div>

                <div className="kv-grid" style={{ marginTop: '0.85rem' }}>
                  {kvProgress.map((kv) => (
                    <div key={kv.label} className="kv-cell">
                      <div className="kv-label">{kv.label}</div>
                      <div
                        className="kv-value"
                        style={kv.valueColor ? { color: kv.valueColor } : kv.valueStyle}
                      >
                        {kv.value}
                      </div>
                      <p className="kv-help">{kv.help}</p>
                    </div>
                  ))}
                </div>

                <div className="divider"></div>

                <div className="card-head" style={{ marginBottom: '0.7rem' }}>
                  <div className="card-title" style={{ fontSize: '0.92rem' }}>
                    <span className="card-title-ico">
                      <EditIcon />
                    </span>
                    分析参数
                  </div>
                </div>
                <div className="kv-grid">
                  {kvAnalysis.map((kv) => (
                    <div key={kv.label} className="kv-cell">
                      <div className="kv-label">{kv.label}</div>
                      <div className="kv-value">{kv.value}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

function FileRow({ name, info, state }) {
  const cls =
    state === 'ok' ? 'file-row file-row--ok' : state === 'run' ? 'file-row file-row--run' : 'file-row';
  return (
    <div className={cls}>
      <div className="file-meta">
        <SubtitleIcon className="file-meta-icon" />
        <div style={{ minWidth: 0, flex: 1 }}>
          <p className="file-name">{name}</p>
          <p className="file-info">{info}</p>
        </div>
      </div>
      {state === 'ok' && (
        <span className="status status--ok">
          <CheckIcon />
          成功
        </span>
      )}
      {state === 'run' && (
        <span className="status status--run pulse">
          <span className="status-dot"></span>处理中
        </span>
      )}
      {state === 'idle' && <span className="status">待处理</span>}
    </div>
  );
}
