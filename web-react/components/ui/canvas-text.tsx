"use client";
import { cn } from "@/lib/utils";
import { useEffect, useRef, useState, useCallback } from "react";

interface CanvasTextProps {
  text: string;
  className?: string;
  backgroundClassName?: string;
  colors?: string[];
  animationDuration?: number;
  lineWidth?: number;
  lineGap?: number;
  curveIntensity?: number;
  overlay?: boolean;
  animating?: boolean;
}

const MOBILE_MEDIA_QUERY = "(max-width: 768px)";
const REDUCED_MOTION_MEDIA_QUERY = "(prefers-reduced-motion: reduce)";
const DESKTOP_TARGET_FPS = 18;
const MOBILE_TARGET_FPS = 10;
const MAX_DESKTOP_DPR = 1.75;
const MAX_MOBILE_DPR = 1.25;

function resolveColor(color: string): string {
  if (color.startsWith("var(")) {
    const varName = color.slice(4, -1).trim();
    const resolved = getComputedStyle(document.documentElement)
      .getPropertyValue(varName)
      .trim();
    return resolved || color;
  }
  return color;
}

function isSameStringArray(left: string[], right: string[]): boolean {
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

export function CanvasText({
  text,
  className = "",
  backgroundClassName = "bg-white dark:bg-neutral-950",
  colors = ["#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#ffeaa7", "#dfe6e9"],
  animationDuration = 5,
  lineWidth = 1.5,
  lineGap = 10,
  curveIntensity = 60,
  overlay = false,
  animating = true,
}: CanvasTextProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textRef = useRef<HTMLSpanElement>(null);
  const bgRef = useRef<HTMLSpanElement>(null);
  const animationRef = useRef<number>(0);
  const startTimeRef = useRef<number>(0);
  const [bgColor, setBgColor] = useState("#0a0a0a");
  const [resolvedColors, setResolvedColors] = useState<string[]>([]);

  const updateColors = useCallback(() => {
    if (bgRef.current) {
      const computed = window.getComputedStyle(bgRef.current);
      const nextBgColor = computed.backgroundColor || "#0a0a0a";
      setBgColor((prev) => (prev === nextBgColor ? prev : nextBgColor));
    }
    const nextColors = colors.map(resolveColor);
    setResolvedColors((prev) =>
      isSameStringArray(prev, nextColors) ? prev : nextColors,
    );
  }, [colors]);

  useEffect(() => {
    updateColors();

    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => observer.disconnect();
  }, [updateColors]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const textEl = textRef.current;
    if (!canvas || !textEl || resolvedColors.length === 0) return;

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) return;

    const isMobileViewport = window.matchMedia(MOBILE_MEDIA_QUERY).matches;
    const prefersReducedMotion = window
      .matchMedia(REDUCED_MOTION_MEDIA_QUERY)
      .matches;
    const targetFps = isMobileViewport ? MOBILE_TARGET_FPS : DESKTOP_TARGET_FPS;
    const frameIntervalMs = 1000 / Math.max(1, targetFps);
    const dprCap = isMobileViewport ? MAX_MOBILE_DPR : MAX_DESKTOP_DPR;
    const shouldAnimate = animating && !prefersReducedMotion;

    let width = 1;
    let height = 1;
    let numLines = 1;
    let lastRenderTime = 0;
    let isInView = true;
    let isPageVisible = document.visibilityState !== "hidden";
    let rafId = 0;
    let currentPhase = 0;

    const updateMetrics = () => {
      const rect = textEl.getBoundingClientRect();
      const nextWidth = Math.max(1, Math.ceil(rect.width));
      const nextHeight = Math.max(1, Math.ceil(rect.height));
      const pixelRatio = Math.min(window.devicePixelRatio || 1, dprCap);

      if (
        nextWidth === width &&
        nextHeight === height &&
        canvas.width > 0 &&
        canvas.height > 0
      ) {
        return;
      }

      width = nextWidth;
      height = nextHeight;
      numLines = Math.max(1, Math.floor(height / lineGap) + 4);
      canvas.width = Math.max(1, Math.round(width * pixelRatio));
      canvas.height = Math.max(1, Math.round(height * pixelRatio));
      ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
      textEl.style.backgroundSize = `${width}px ${height}px`;
    };

    const renderFrame = (phase: number) => {
      ctx.fillStyle = bgColor;
      ctx.fillRect(0, 0, width, height);
      ctx.lineWidth = lineWidth;

      const curve1 = Math.sin(phase) * curveIntensity;
      const curve2 = Math.sin(phase + 0.5) * curveIntensity * 0.6;
      const controlX1 = width * 0.33;
      const controlX2 = width * 0.66;

      for (let i = 0; i < numLines; i += 1) {
        const y = i * lineGap;
        const colorIndex = i % resolvedColors.length;
        ctx.strokeStyle = resolvedColors[colorIndex];
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.bezierCurveTo(controlX1, y + curve1, controlX2, y + curve2, width, y);
        ctx.stroke();
      }

      textEl.style.backgroundImage = `url(${canvas.toDataURL()})`;
    };

    const redraw = (phase: number) => {
      updateMetrics();
      renderFrame(phase);
    };

    const onVisibilityChange = () => {
      isPageVisible = document.visibilityState !== "hidden";
      if (isPageVisible) {
        lastRenderTime = 0;
      }
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    let intersectionObserver: IntersectionObserver | null = null;
    if (typeof IntersectionObserver !== "undefined") {
      intersectionObserver = new IntersectionObserver(
        (entries) => {
          isInView = Boolean(entries[0]?.isIntersecting);
          if (isInView) {
            lastRenderTime = 0;
          }
        },
        { threshold: 0 },
      );
      intersectionObserver.observe(textEl);
    }

    const handleResize = () => {
      redraw(currentPhase);
      lastRenderTime = 0;
    };

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(textEl);
    } else {
      window.addEventListener("resize", handleResize);
    }

    redraw(0);

    const cleanup = () => {
      if (rafId) {
        window.cancelAnimationFrame(rafId);
      }
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (!resizeObserver) {
        window.removeEventListener("resize", handleResize);
      }
    };

    if (!shouldAnimate) {
      return cleanup;
    }

    startTimeRef.current = performance.now();

    const animate = (currentTime: number) => {
      if (!isInView || !isPageVisible) {
        rafId = window.requestAnimationFrame(animate);
        animationRef.current = rafId;
        return;
      }

      if (lastRenderTime > 0 && currentTime - lastRenderTime < frameIntervalMs) {
        rafId = window.requestAnimationFrame(animate);
        animationRef.current = rafId;
        return;
      }

      lastRenderTime = currentTime;
      const elapsed = (currentTime - startTimeRef.current) / 1000;
      currentPhase = (elapsed / animationDuration) * Math.PI * 2;
      renderFrame(currentPhase);
      rafId = window.requestAnimationFrame(animate);
      animationRef.current = rafId;
    };

    rafId = window.requestAnimationFrame(animate);
    animationRef.current = rafId;

    return cleanup;
  }, [
    bgColor,
    resolvedColors,
    animationDuration,
    lineWidth,
    lineGap,
    curveIntensity,
    animating,
  ]);

  return (
    <span className={cn("relative inline", overlay && "absolute inset-0")}>
      <span
        ref={bgRef}
        className={cn(
          "pointer-events-none absolute h-0 w-0 opacity-0",
          backgroundClassName,
        )}
        aria-hidden="true"
      />
      <canvas
        ref={canvasRef}
        className="pointer-events-none absolute h-0 w-0 opacity-0"
        aria-hidden="true"
      />
      <span
        ref={textRef}
        className={cn(
          "bg-clip-text text-transparent",
          overlay ? "absolute inset-0" : "inline",
          className,
        )}
        style={{
          WebkitBackgroundClip: "text",
        }}
      >
        {text}
      </span>
    </span>
  );
}
