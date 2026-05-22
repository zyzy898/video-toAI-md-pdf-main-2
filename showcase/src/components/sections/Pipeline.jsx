import { ArrowRightIcon } from '../icons/Icons.jsx';
import { pipelineSteps } from '../../data/pipeline.js';

/**
 * 端到端处理链路：8 张卡 + 背后的 SVG 流光轨道。
 */
export default function Pipeline() {
  return (
    <section id="pipeline">
      <div className="container">
        <div className="section-head">
          <span className="section-tag">END-TO-END PIPELINE</span>
          <h2 className="section-title">从上传到导出 · 七步法处理链路</h2>
          <p className="section-sub">
            每一步都做了失败兜底与降级方案；长视频自动压缩切片，违规内容上传前就被拦下，最终交付清晰的文档与历史回看。
          </p>
        </div>

        <div className="pipeline-wrap">
          <div className="pipeline-rail" aria-hidden="true">
            <svg viewBox="0 0 1200 360" preserveAspectRatio="none">
              <defs>
                <linearGradient id="pipeRail" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="rgba(34,211,238,0)" />
                  <stop offset=".3" stopColor="rgba(34,211,238,0.35)" />
                  <stop offset=".7" stopColor="rgba(96,165,250,0.35)" />
                  <stop offset="1" stopColor="rgba(96,165,250,0)" />
                </linearGradient>
                <linearGradient id="pipeFlow" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0" stopColor="rgba(255,255,255,0)" />
                  <stop offset=".5" stopColor="rgba(186,230,253,0.95)" />
                  <stop offset="1" stopColor="rgba(255,255,255,0)" />
                </linearGradient>
              </defs>
              <path
                d="M 60 90 H 1140"
                stroke="url(#pipeRail)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="4 6"
                fill="none"
              />
              <path
                d="M 60 270 H 1140"
                stroke="url(#pipeRail)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="4 6"
                fill="none"
              />
              <path
                d="M 1140 90 C 1180 90 1180 270 1140 270"
                stroke="url(#pipeRail)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="4 6"
                fill="none"
              />
              <path
                d="M 60 270 C 20 270 20 90 60 90"
                stroke="url(#pipeRail)"
                strokeWidth="2"
                strokeLinecap="round"
                strokeDasharray="4 6"
                fill="none"
                opacity=".5"
              />
              <g className="pipeline-flow">
                <circle r="3" fill="url(#pipeFlow)">
                  <animateMotion
                    dur="8s"
                    repeatCount="indefinite"
                    rotate="auto"
                    path="M 60 90 H 1140 C 1180 90 1180 270 1140 270 H 60 C 20 270 20 90 60 90 Z"
                  />
                </circle>
                <circle r="2" fill="rgba(186,230,253,0.7)">
                  <animateMotion
                    dur="8s"
                    begin="-2.6s"
                    repeatCount="indefinite"
                    rotate="auto"
                    path="M 60 90 H 1140 C 1180 90 1180 270 1140 270 H 60 C 20 270 20 90 60 90 Z"
                  />
                </circle>
                <circle r="2" fill="rgba(167,139,250,0.7)">
                  <animateMotion
                    dur="8s"
                    begin="-5.2s"
                    repeatCount="indefinite"
                    rotate="auto"
                    path="M 60 90 H 1140 C 1180 90 1180 270 1140 270 H 60 C 20 270 20 90 60 90 Z"
                  />
                </circle>
              </g>
            </svg>
          </div>

          <div className="pipeline">
            {pipelineSteps.map((step, idx) => {
              const delayClass =
                idx % 4 === 1 ? ' delay-1' : idx % 4 === 2 ? ' delay-2' : idx % 4 === 3 ? ' delay-3' : '';
              const isLastInRow = idx === 3 || idx === pipelineSteps.length - 1;
              return (
                <div key={step.title} className={`step fade-up${delayClass}`}>
                  <div className="step-head">
                    <span className={`step-num${step.isFinal ? ' step-num--final' : ''}`}>{step.num}</span>
                    <span className={`step-stage-tag${step.isFinal ? ' step-stage-tag--final' : ''}`}>
                      {step.stage}
                    </span>
                  </div>
                  <h3 className="step-title">{step.title}</h3>
                  <p className="step-desc">{step.desc}</p>
                  {!isLastInRow && (
                    <span className="step-connector" aria-hidden="true">
                      <ArrowRightIcon />
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
