import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'vi-showcase-theme';

/** 读取初始主题：localStorage 优先，其次跟随系统，默认 dark。 */
function readInitialTheme() {
  if (typeof window === 'undefined') return 'dark';
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === 'light' || stored === 'dark') return stored;
  } catch {
    // 忽略存储读取失败
  }
  if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
    return 'light';
  }
  return 'dark';
}

// —— 模块级共享状态：让 Nav（切换）与各页面（DarkVeil 配色）保持同步 ——
let currentTheme = readInitialTheme();
const listeners = new Set();

function applyTheme(next) {
  currentTheme = next;
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('data-theme', next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // 忽略存储写入失败
    }
  }
  listeners.forEach((fn) => fn(next));
}

/**
 * 全局明暗主题。任意组件订阅同一份状态：
 * - Nav 调用 toggleTheme 切换
 * - 页面读取 theme 传给 DarkVeil 决定配色
 * 返回 [theme, toggleTheme]。
 */
export default function useTheme() {
  const [theme, setTheme] = useState(currentTheme);

  useEffect(() => {
    const listener = (next) => setTheme(next);
    listeners.add(listener);
    // 挂载时把 data-theme 同步到 DOM（首个订阅者负责初始化）
    if (typeof document !== 'undefined' && document.documentElement.getAttribute('data-theme') !== currentTheme) {
      document.documentElement.setAttribute('data-theme', currentTheme);
    }
    setTheme(currentTheme);
    return () => {
      listeners.delete(listener);
    };
  }, []);

  const toggleTheme = useCallback(() => {
    applyTheme(currentTheme === 'dark' ? 'light' : 'dark');
  }, []);

  return [theme, toggleTheme];
}
