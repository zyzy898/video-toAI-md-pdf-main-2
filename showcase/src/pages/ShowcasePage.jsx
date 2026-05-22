import { useEffect } from 'react';
import DarkVeil from '../components/DarkVeil/DarkVeil.jsx';
import Footer from '../components/Footer.jsx';
import ShowcaseIntro from '../components/sections/ShowcaseIntro.jsx';
import Capabilities from '../components/sections/Capabilities.jsx';
import Workspace from '../components/sections/Workspace.jsx';
import Pipeline from '../components/sections/Pipeline.jsx';
import Result from '../components/sections/Result.jsx';
import Tech from '../components/sections/Tech.jsx';
import useFadeUpReveal from '../hooks/useFadeUpReveal.js';
import useSmoothAnchor from '../hooks/useSmoothAnchor.js';
import useSectionReveal from '../hooks/useSectionReveal.js';
import useIsMobile from '../hooks/useIsMobile.js';

/**
 * /showcase · 详细演示页
 * - 顶栏由 App.jsx 中的 <NavBar /> 常驻渲染（active 高亮等行为已在那里处理）
 * - 每个大模块至少占满一屏（min-height: 100vh）+ scroll-snap，浏览时一次只看一个
 */
export default function ShowcasePage() {
  useFadeUpReveal();
  useSmoothAnchor();
  useSectionReveal();
  const isMobile = useIsMobile(768);

  // 给 body 临时加 .has-snap 类，启用整页 scroll-snap，离开 /showcase 路由时自动移除
  useEffect(() => {
    document.body.classList.add('has-snap');
    return () => document.body.classList.remove('has-snap');
  }, []);

  return (
    <div className="showcase-page">
      <div className="darkveil-bg" aria-hidden="true">
        <DarkVeil hueShift={43} speed={isMobile ? 0.5 : 0.7} />
      </div>

      <ShowcaseIntro />

      <SectionWrapper variant="up">
        <Capabilities />
      </SectionWrapper>

      <SectionWrapper variant="left">
        <Workspace />
      </SectionWrapper>

      <SectionWrapper variant="right">
        <Pipeline />
      </SectionWrapper>

      <SectionWrapper variant="up">
        <Result />
      </SectionWrapper>

      <SectionWrapper variant="scale">
        <Tech />
      </SectionWrapper>

      <Footer />
    </div>
  );
}

function SectionWrapper({ variant = 'up', children }) {
  return <div className={`section-reveal section-reveal--${variant}`}>{children}</div>;
}
