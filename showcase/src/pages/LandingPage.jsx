import { Link } from 'react-router-dom';
import DarkVeil from '../components/DarkVeil/DarkVeil.jsx';
import TextType from '../components/TextType/TextType.jsx';
import { PlayIcon, ArrowRightIcon } from '../components/icons/Icons.jsx';
import useFadeUpReveal from '../hooks/useFadeUpReveal.js';
import useIsMobile from '../hooks/useIsMobile.js';
import useTheme from '../hooks/useTheme.js';

/**
 * 「开始使用」按钮跳转的线上工作台地址。
 * TODO: 部署完成后替换为真实的线上地址（例如 https://your-app.example.com）。
 */
const APP_URL = '#';

const heroChips = [
  'AI 视频理解',
  'Whisper ASR',
  '多模型路由',
  'Markdown · PDF',
  '链接直达分析'
];

const heroStats = [
  { num: '8+', label: '支持视频格式' },
  { num: '4', label: 'LLM Provider' },
  { num: '500MB', label: '单文件上限' },
  { num: '72h', label: '历史自动清理' }
];

/**
 * / · 着陆页（首页）
 * 全屏 DarkVeil + 品牌 + 主标语 + CTA。点击"开始演示"才进入 /showcase。
 */
export default function LandingPage() {
  useFadeUpReveal();
  const isMobile = useIsMobile(768);
  const [theme] = useTheme();

  return (
    <div className="landing">
      {/* DarkVeil 占满整个 landing：明主题下传 lightMix 让背景反相为浅色 */}
      <div className="landing-bg" aria-hidden="true">
        <DarkVeil hueShift={43} speed={isMobile ? 0.5 : 0.7} lightMix={theme === 'light' ? 1 : 0} />
      </div>

      <main className="landing-main">
        <span className="eyebrow fade-up">AI · 视频理解工作台</span>
        <h1 className="landing-title fade-up delay-1">
          视频转文档，
          <br />
          <TextType
            as="span"
            text={[
              '不止提取，更是理解',
              '看懂教程视频的每一步',
              '让信息沉淀更高效'
            ]}
            typingSpeed={75}
            pauseDuration={1500}
            deletingSpeed={40}
            cursorCharacter="|"
            showCursor={true}
          />
        </h1>
        <p className="landing-lead fade-up delay-2">
          AI 自动分析视频内容，抓取关键截图、拆解操作步骤，
          <br />
          输出结构清晰、重点明确的 Markdown / PDF 总结文档。
        </p>

        <div className="landing-chips fade-up delay-3">
          {heroChips.map((c) => (
            <span key={c} className="chip">
              <span className="chip-dot"></span>
              {c}
            </span>
          ))}
        </div>

        <div className="landing-cta fade-up delay-3">
          <a
            href={APP_URL}
            target="_blank"
            rel="noreferrer"
            className="btn btn--primary btn--xl"
          >
            <PlayIcon />
            开始使用
          </a>
          <Link to="/showcase" className="btn btn--xl btn--ghost">
            观看演示
            <ArrowRightIcon />
          </Link>
        </div>

        <div className="landing-stats fade-up delay-3">
          {heroStats.map((s) => (
            <div key={s.label} className="landing-stat">
              <div className="landing-stat-num">{s.num}</div>
              <div className="landing-stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </main>

      <footer className="landing-foot">
        <span>© Video Insights · React 19 + Vite + DarkVeil</span>
      </footer>
    </div>
  );
}
