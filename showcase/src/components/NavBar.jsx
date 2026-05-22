import { useLocation } from 'react-router-dom';
import Nav from './Nav.jsx';
import useActiveSection from '../hooks/useActiveSection.js';
import { navLinks } from '../data/nav.js';

const sectionIds = navLinks.map((l) => l.href);

/**
 * 路由感知的常驻顶栏：
 * - 仅在 /showcase 启用 active section 跟踪与完整 nav 链接
 * - 其它路由（如 /）走精简模式：只展示品牌 + "进入演示" 入口
 * - 所有路由都会渲染 nav（即"常驻"），由 CSS 给页面 body 留出顶部空间
 */
export default function NavBar() {
  const { pathname } = useLocation();
  const isShowcase = pathname.startsWith('/showcase');

  // hook 内部已经做了"找不到目标元素"的兜底，可以无脑调用
  const activeId = useActiveSection(isShowcase ? sectionIds : []);

  return <Nav activeId={isShowcase ? activeId : null} mode={isShowcase ? 'full' : 'minimal'} />;
}
