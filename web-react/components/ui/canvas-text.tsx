"use client";
import { cn } from "@/lib/utils";
import { useEffect, useRef, useState, useCallback, useMemo, type CSSProperties } from "react";

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
const MOBILE_TARGET_FPS = 10;
const MAX_DESKTOP_DPR = 1.75;
const MAX_MOBILE_DPR = 1.25;

type RenderMode = "canvas" | "static";

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

function supportsTextBackgroundClip(): boolean {
  if (typeof window === "undefined") return false;
  if (typeof CSS === "undefined" || typeof CSS.supports !== "function") return false;
  return (
    CSS.supports("background-clip", "text") ||
    CSS.supports("-webkit-background-clip", "text")
  );
}

function isDesktopPlatform(): boolean {
  if (typeof window === "undefined" || typeof navigator === "undefined") return true;

  const uaData = (
    navigator as Navigator & { userAgentData?: { mobile?: boolean } }
  ).userAgentData;
  if (uaData && typeof uaData.mobile === "boolean") {
    return !uaData.mobile;
  }

  const ua = navigator.userAgent || "";
  const isMobileUa = /android|iphone|ipad|ipod|mobile|windows phone|blackberry|opera mini/i.test(
    ua,
  );
  const isIpadDesktopUa = /macintosh/i.test(ua) && (navigator.maxTouchPoints || 0) > 1;
  return !isMobileUa && !isIpadDesktopUa;
}
function buildStaticGradient(colors: string[]): string {
  const palette = colors.length > 0 ? colors : ["#38bdf8", "#60a5fa", "#22d3ee"];
  if (palette.length === 1) {
    return `linear-gradient(90deg, ${palette[0]}, ${palette[0]})`;
  }
  const lastIndex = Math.max(1, palette.length - 1);
  const stops = palette
    .map((color, index) => `${color} ${(index / lastIndex) * 100}%`)
    .join(", ");
  return `linear-gradient(90deg, ${stops})`;
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
  const hasReportedRenderErrorRef = useRef(false);

  const [bgColor, setBgColor] = useState("#0a0a0a");
  const [resolvedColors, setResolvedColors] = useState<string[]>([]);
  const [isDesktop, setIsDesktop] = useState<boolean>(() => isDesktopPlatform());
  const [supportsTextClip, setSupportsTextClip] = useState<boolean>(() =>
    supportsTextBackgroundClip(),
  );
  const [renderMode, setRenderMode] = useState<RenderMode>(() =>
    supportsTextBackgroundClip() || isDesktopPlatform() ? "canvas" : "static",
  );
  const shouldEnableFallback = !isDesktop;

  const fallbackToStatic = useCallback(() => {
    setRenderMode((prev) => (prev === "static" ? prev : "static"));
  }, []);

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
    const frame = window.requestAnimationFrame(() => {
      const desktop = isDesktopPlatform();
      setIsDesktop((prev) => (prev === desktop ? prev : desktop));
      const supports = supportsTextBackgroundClip();
      setSupportsTextClip((prev) => (prev === supports ? prev : supports));
      if (!desktop && !supports) {
        fallbackToStatic();
      }
    });

    return () => window.cancelAnimationFrame(frame);
  }, [fallbackToStatic]);

  useEffect(() => {
    const frame = window.requestAnimationFrame(updateColors);

    const observer = new MutationObserver(updateColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [updateColors]);

  useEffect(() => {
    if (renderMode !== "canvas") return;

    let fallbackFrame = 0;
    const scheduleFallback = () => {
      if (!shouldEnableFallback || fallbackFrame) return;
      fallbackFrame = window.requestAnimationFrame(() => {
        fallbackFrame = 0;
        fallbackToStatic();
      });
    };
    const cancelFallback = () => {
      if (fallbackFrame) {
        window.cancelAnimationFrame(fallbackFrame);
        fallbackFrame = 0;
      }
    };

    const canvas = canvasRef.current;
    const textEl = textRef.current;
    if (!canvas || !textEl || resolvedColors.length === 0) {
      scheduleFallback();
      return cancelFallback;
    }

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
      scheduleFallback();
      return cancelFallback;
    }

    hasReportedRenderErrorRef.current = false;
    let renderFailed = false;

    const reportRenderError = (error: unknown, stage: string) => {
      if (renderFailed) return;
      renderFailed = true;
      if (!hasReportedRenderErrorRef.current) {
        hasReportedRenderErrorRef.current = true;
        console.warn(`[CanvasText] fallback to static mode at ${stage}`, error);
      }
      scheduleFallback();
    };

    const isMobileViewport = window.matchMedia(MOBILE_MEDIA_QUERY).matches;
    const prefersReducedMotion = window
      .matchMedia(REDUCED_MOTION_MEDIA_QUERY)
      .matches;
    const frameIntervalMs = isMobileViewport
      ? 1000 / Math.max(1, MOBILE_TARGET_FPS)
      : 0;
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

    const redraw = (phase: number): boolean => {
      try {
        updateMetrics();
        renderFrame(phase);
        return true;
      } catch (error) {
        reportRenderError(error, "redraw");
        return false;
      }
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
      if (!redraw(currentPhase)) return;
      lastRenderTime = 0;
    };

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(handleResize);
      resizeObserver.observe(textEl);
    } else {
      window.addEventListener("resize", handleResize);
    }

    if (!redraw(0)) {
      resizeObserver?.disconnect();
      intersectionObserver?.disconnect();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      if (!resizeObserver) {
        window.removeEventListener("resize", handleResize);
      }
      return cancelFallback;
    }

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
      cancelFallback();
    };

    if (!shouldAnimate) {
      return cleanup;
    }

    startTimeRef.current = performance.now();

    const animate = (currentTime: number) => {
      if (renderFailed) {
        return;
      }

      if (!isInView || !isPageVisible) {
        rafId = window.requestAnimationFrame(animate);
        animationRef.current = rafId;
        return;
      }

      if (
        frameIntervalMs > 0 &&
        lastRenderTime > 0 &&
        currentTime - lastRenderTime < frameIntervalMs
      ) {
        rafId = window.requestAnimationFrame(animate);
        animationRef.current = rafId;
        return;
      }

      lastRenderTime = currentTime;
      const elapsed = (currentTime - startTimeRef.current) / 1000;
      currentPhase = (elapsed / animationDuration) * Math.PI * 2;

      try {
        renderFrame(currentPhase);
      } catch (error) {
        reportRenderError(error, "animate");
        return;
      }

      if (renderFailed) return;
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
    renderMode,
    fallbackToStatic,
    shouldEnableFallback,
  ]);

  const staticGradient = useMemo(
    () => buildStaticGradient(resolvedColors),
    [resolvedColors],
  );

  const textClassName = cn(
    renderMode === "canvas" || supportsTextClip
      ? "bg-clip-text text-transparent"
      : "text-sky-300",
    overlay ? "absolute inset-0" : "inline",
    className,
  );

  const textStyle = useMemo<CSSProperties>(() => {
    if (renderMode === "canvas") {
      return {
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        WebkitTextFillColor: "transparent",
      };
    }

    if (supportsTextClip) {
      return {
        backgroundImage: staticGradient,
        backgroundSize: "100% 100%",
        WebkitBackgroundClip: "text",
        backgroundClip: "text",
        WebkitTextFillColor: "transparent",
        color: "transparent",
      };
    }

    return {
      color: resolvedColors[0] || "#7dd3fc",
    };
  }, [renderMode, resolvedColors, staticGradient, supportsTextClip]);

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
      <span ref={textRef} className={textClassName} style={textStyle}>
        {text}
      </span>
    </span>
  );
}
