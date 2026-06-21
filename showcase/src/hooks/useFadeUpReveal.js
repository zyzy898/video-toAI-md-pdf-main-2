import { useEffect } from 'react';

/**
 * 使用 IntersectionObserver 自动给所有 .fade-up 元素加 in-view 类。
 * 默认 .fade-up 用 animation-play-state: paused 等待此触发。
 */
export default function useFadeUpReveal() {
  useEffect(() => {
    if (!('IntersectionObserver' in window)) {
      // 不支持时直接全部展示
      document.querySelectorAll('.fade-up').forEach((el) => el.classList.add('in-view'));
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add('in-view');
            observer.unobserve(entry.target);
          }
        });
      },
      // threshold 0：任何一部分进入视口即触发，避免比视口高很多的元素
      // 永远达不到阈值而停在隐藏态（同 useSectionReveal）。
      { threshold: 0, rootMargin: '0px 0px -8% 0px' }
    );

    document.querySelectorAll('.fade-up').forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);
}
