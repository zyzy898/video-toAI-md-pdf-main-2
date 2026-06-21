import { ArrowRightIcon, FileIcon, DownloadIcon } from '../icons/Icons.jsx';

/**
 * "输入视频 ↔ 输出文档" 对照模块。
 * 左：真实源视频（高效求职渠道讲解）；右：生成文档的要点缩略 + 下载入口。
 * 用最直观的方式回答"这个工具到底产出什么"。
 */
const outputHighlights = [
  '6 个结构化求职渠道步骤，含时间点定位',
  '6 张关键帧截图，自动抽取对齐步骤',
  'Markdown / PDF 双格式，排版即用',
  '字幕 SRT / VTT / TXT 全量导出'
];

export default function Showdown() {
  return (
    <section id="showdown">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">INPUT → OUTPUT</span>
          <h2 className="section-title">一段视频进，一份文档出</h2>
          <p className="section-sub">
            左边是真实的源视频，右边是 Video Insights 自动生成的成品文档。无需手动记录，AI 看一遍就帮你整理好。
          </p>
        </div>

        <div className="showdown-grid">
          {/* 输入：真实视频 */}
          <div className="showdown-card">
            <div className="showdown-card-head">
              <span className="showdown-badge showdown-badge--in">输入 · 源视频</span>
              <span className="showdown-meta">MP4 · 约 02:28</span>
            </div>
            <div className="showdown-video-wrap">
              <video
                className="showdown-video"
                src="/sample/sample_video.mp4"
                controls
                preload="metadata"
                playsInline
              />
            </div>
            <p className="showdown-caption">高效求职渠道讲解（真实样例）</p>
          </div>

          {/* 箭头 */}
          <div className="showdown-arrow" aria-hidden="true">
            <ArrowRightIcon />
          </div>

          {/* 输出：文档要点 */}
          <div className="showdown-card">
            <div className="showdown-card-head">
              <span className="showdown-badge showdown-badge--out">输出 · 成品文档</span>
              <span className="showdown-meta">Markdown · PDF</span>
            </div>
            <div className="showdown-doc">
              <div className="showdown-doc-title">
                <FileIcon className="ico-sm" />
                高效求职渠道操作指南
              </div>
              <ul className="showdown-doc-list">
                {outputHighlights.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            </div>
            <div className="showdown-actions">
              <a className="btn btn--primary" href="/sample/operation_guide.pdf" target="_blank" rel="noreferrer" download>
                <DownloadIcon />
                下载样例 PDF
              </a>
              <a className="btn" href="#result">
                查看完整结果
                <ArrowRightIcon />
              </a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
