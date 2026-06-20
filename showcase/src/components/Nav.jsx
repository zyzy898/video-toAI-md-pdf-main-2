import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronRightIcon, GithubIcon, SunIcon, MoonIcon } from './icons/Icons.jsx';
import { navLinks } from '../data/nav.js';
import useTheme from '../hooks/useTheme.js';

/** 项目源码仓库地址。 */
const REPO_URL = 'https://github.com/zyzy898/video-toAI-md-pdf-main-2';

/**
 * 顶栏 + 移动端抽屉。
 * - 左侧品牌点击回 / 首页（react-router Link）
 * - mode='full'    /showcase：展示锚点 pill + active 高亮
 * - mode='minimal' /：只展示一个 "进入演示" CTA pill
 * - activeId：当前命中的锚点 id（不含 #），命中的 pill 加 .is-active 触发动画
 */
export default function Nav({ activeId = null, mode = 'full' }) {
  const [open, setOpen] = useState(false);
  const [theme, toggleTheme] = useTheme();
  const isMinimal = mode === 'minimal';

  useEffect(() => {
    if (open) document.body.setAttribute('data-nav-open', 'true');
    else document.body.removeAttribute('data-nav-open');
  }, [open]);

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);

    const mq = window.matchMedia('(max-width: 768px)');
    const onMq = () => {
      if (!mq.matches) setOpen(false);
    };
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onMq);
    else if (typeof mq.addListener === 'function') mq.addListener(onMq);

    return () => {
      document.removeEventListener('keydown', onKey);
      if (typeof mq.removeEventListener === 'function') mq.removeEventListener('change', onMq);
      else if (typeof mq.removeListener === 'function') mq.removeListener(onMq);
    };
  }, []);

  const isActive = (href) => activeId && href === `#${activeId}`;

  return (
    <nav className="nav">
      <div className="nav-inner">
        <Link to="/" className="brand" aria-label="返回首页">
          <span className="brand-logo" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          </span>
          <span>VIDEO INSIGHTS</span>
        </Link>
        {/* minimal 模式（首页）下不渲染中间的链接组，让品牌单独靠左 */}
        {!isMinimal && (
          <div className="nav-links">
            {navLinks.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className={[
                  'nav-pill',
                  link.accent && 'nav-pill--accent',
                  isActive(link.href) && 'is-active'
                ]
                  .filter(Boolean)
                  .join(' ')}
                aria-current={isActive(link.href) ? 'true' : undefined}
              >
                {link.label}
              </a>
            ))}
          </div>
        )}
        <div className="nav-right">
          <button
            type="button"
            className="nav-theme-toggle"
            onClick={toggleTheme}
            aria-label={theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'}
            title={theme === 'dark' ? '切换到亮色主题' : '切换到暗色主题'}
          >
            {theme === 'dark' ? <SunIcon className="ico" /> : <MoonIcon className="ico" />}
          </button>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noreferrer"
            className="nav-github"
            aria-label="查看源码（GitHub）"
            title="查看源码"
          >
            <GithubIcon className="ico" />
          </a>
          {/* 移动端汉堡：只在 full 模式下展示（minimal 模式没有锚点抽屉的必要） */}
          {!isMinimal && (
            <button
              type="button"
              className="nav-toggle"
              aria-controls="nav-mobile-panel"
              aria-expanded={open ? 'true' : 'false'}
              aria-label={open ? '关闭菜单' : '打开菜单'}
              onClick={() => setOpen((v) => !v)}
            >
              <span className="nav-toggle-bars" aria-hidden="true">
                <span></span>
                <span></span>
                <span></span>
              </span>
            </button>
          )}
        </div>
      </div>
      {!isMinimal && (
        <div
          className="nav-mobile-panel"
          id="nav-mobile-panel"
          data-open={open ? 'true' : 'false'}
          aria-hidden={open ? 'false' : 'true'}
        >
          <ul className="nav-mobile-list">
            {navLinks.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  className={[
                    'nav-mobile-link',
                    link.accent && 'nav-mobile-link--accent',
                    isActive(link.href) && 'is-active'
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  onClick={() => setTimeout(() => setOpen(false), 80)}
                >
                  <span>{link.mobileLabel}</span>
                  <ChevronRightIcon className="nav-mobile-link-arrow" />
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </nav>
  );
}
