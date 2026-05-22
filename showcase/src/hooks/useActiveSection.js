import { useEffect, useState } from 'react';

/**
 * 跟踪当前最大可见的 section id（基于 IntersectionObserver）。
 * 用法：
 *   const active = useActiveSection(['#intro', '#capabilities', ...]);
 * 返回值：当前命中（不包含 # 前缀）的 id；无命中时为 null。
 */
export default function useActiveSection(hashes) {
  const [active, setActive] = useState(null);

  useEffect(() => {
    if (!('IntersectionObserver' in window)) return;
    const ids = hashes.map((h) => (h.startsWith('#') ? h.slice(1) : h));
    const els = ids
      .map((id) => document.getElementById(id))
      .filter(Boolean);
    if (!els.length) return;

    // 保存每个目标的最新 ratio，挑 ratio 最大的作为 active。
    const ratios = new Map();
    ids.forEach((id) => ratios.set(id, 0));

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          ratios.set(entry.target.id, entry.intersectionRatio);
        });
        let best = null;
        let bestRatio = 0;
        ratios.forEach((ratio, id) => {
          if (ratio > bestRatio) {
            bestRatio = ratio;
            best = id;
          }
        });
        // 只在用户已经滚到某个 section 才高亮，否则保持 null
        setActive(bestRatio > 0.15 ? best : null);
      },
      {
        // 多档 threshold 让"最显眼"的判断更稳定
        threshold: [0, 0.15, 0.3, 0.5, 0.7, 0.9, 1],
        rootMargin: '-15% 0px -25% 0px'
      }
    );

    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [hashes]);

  return active;
}
