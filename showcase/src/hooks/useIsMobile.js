import { useEffect, useState } from 'react';

/**
 * 监听 (max-width: maxWidth) 媒体查询。
 * 主要用于在移动端给 DarkVeil 等 WebGL 组件降分辨率，节省 GPU / 电量。
 */
export default function useIsMobile(maxWidth = 768) {
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.matchMedia(`(max-width: ${maxWidth}px)`).matches;
  });

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${maxWidth}px)`);
    const onChange = () => setIsMobile(mq.matches);
    if (typeof mq.addEventListener === 'function') mq.addEventListener('change', onChange);
    else if (typeof mq.addListener === 'function') mq.addListener(onChange);
    return () => {
      if (typeof mq.removeEventListener === 'function') mq.removeEventListener('change', onChange);
      else if (typeof mq.removeListener === 'function') mq.removeListener(onChange);
    };
  }, [maxWidth]);

  return isMobile;
}
