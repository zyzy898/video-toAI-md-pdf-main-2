import { useEffect } from 'react';

/**
 * 给所有 .section-reveal 元素添加进入视口的滑入动画。
 * - 默认 hidden（CSS 里 opacity:0 + translateY/translateX）
 * - 进入视口后加 .is-visible 触发动画
 * - 仅触发一次（unobserve），避免反复抖动
 *
 * 想换方向：在元素上加 `.section-reveal--up | --left | --right | --scale`。
 */
export default function useSectionReveal() {
  useEffect(() => {
    const targets = document.querySelectorAll('.section-reveal');
    if (!targets.length) return;

    if (!('IntersectionObserver' in window)) {
      targets.forEach((el) => el.classList.add('is-visible'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      },
      {
        // 用 0 而不是 0.12：内容富集的 section（如 Result：6 步截图 + 117 行字幕，
        // 手机端 max-height 解除后高度可达 6000px+）在窄视口里最大可见比例都
        // 达不到 12%，会导致 isIntersecting 永远为 false → 永远停在 opacity:0。
        // 任何一部分进入视口就触发，杜绝"整段不显示"。
        threshold: 0,
        // 提前一点触发，让滚动节奏更自然
        rootMargin: '0px 0px -8% 0px'
      }
    );

    targets.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);
}
