import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RefObject } from "react";
import type { SingleResultData, SubtitleLine, SubtitleWorkbenchData } from "../types/api";
import { StepsIcon } from "./icons";

type SubtitlePanelProps = {
  resultData: SingleResultData;
  subtitleWorkbench: SubtitleWorkbenchData | null;
  subtitleLines: SubtitleLine[];
  filteredSubtitleLines: SubtitleLine[];
  subtitleKeyword: string;
  subtitleLoading: boolean;
  subtitleRefreshing: boolean;
  subtitleLoadError: string;
  subtitleAssetAvailable: boolean;
  videoRef: RefObject<HTMLVideoElement | null>;
  onKeywordChange: (value: string) => void;
  onRefresh: () => void;
  onDownload: () => void;
  onSeek: (seconds: number) => void;
  formatDisplayTime: (value: unknown) => string;
};

// Approximate height of one rendered subtitle row (timestamp + one text line).
// Used only to window the list; exact per-row height is not required.
const ESTIMATED_ROW_HEIGHT = 52;
const LIST_VIEWPORT_HEIGHT = 340;
const OVERSCAN_ROWS = 6;
const MAX_RENDERED_LINES = 5000;
// Throttle interval for the playhead -> active-line sync (ms).
const ACTIVE_SYNC_INTERVAL = 200;

const lineKey = (line: SubtitleLine, idx: number) =>
  `${line.index ?? idx}:${Number(line.start_seconds ?? -1)}`;

type SubtitleRowProps = {
  line: SubtitleLine;
  top: number;
  isActive: boolean;
  rowRef: ((el: HTMLButtonElement | null) => void) | null;
  onSeek: (seconds: number) => void;
  formatDisplayTime: (value: unknown) => string;
};

// Memoized so windowed rows only re-render when their own active state flips,
// not on every parent render or playhead tick.
const SubtitleRow = memo(function SubtitleRow({
  line,
  top,
  isActive,
  rowRef,
  onSeek,
  formatDisplayTime,
}: SubtitleRowProps) {
  return (
    <button
      type="button"
      ref={rowRef}
      aria-current={isActive ? "true" : undefined}
      style={{ position: "absolute", top, left: 0, right: 0 }}
      className={`subtitle-line-row block w-full rounded border px-2 py-1.5 text-left text-xs transition-colors ${
        isActive
          ? "subtitle-line-row--active border-teal-400/70 bg-teal-500/15"
          : "border-neutral-800 bg-neutral-950/60 hover:border-teal-400/60 hover:bg-teal-500/10"
      }`}
      onClick={() => onSeek(Number(line.start_seconds || 0))}
    >
      <p className="font-semibold text-teal-200/95">
        {formatDisplayTime(line.start_time)} - {formatDisplayTime(line.end_time)}
      </p>
      <p className="mt-0.5 truncate text-neutral-200">{String(line.text || "")}</p>
    </button>
  );
});

export const SubtitlePanel = memo(function SubtitlePanel({
  resultData,
  subtitleWorkbench,
  subtitleLines,
  filteredSubtitleLines,
  subtitleKeyword,
  subtitleLoading,
  subtitleRefreshing,
  subtitleLoadError,
  subtitleAssetAvailable,
  videoRef,
  onKeywordChange,
  onRefresh,
  onDownload,
  onSeek,
  formatDisplayTime,
}: SubtitlePanelProps) {
  const videoSrc = String(subtitleWorkbench?.video_preview_url || resultData?.video_preview_url || "").trim();
  const subtitleFile = String(subtitleWorkbench?.subtitle_file || resultData?.subtitle_file_name || "").trim();

  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [scrollTop, setScrollTop] = useState<number>(0);
  const listScrollRef = useRef<HTMLDivElement | null>(null);
  const activeLineRef = useRef<HTMLButtonElement | null>(null);

  const renderLines = useMemo(
    () => filteredSubtitleLines.slice(0, MAX_RENDERED_LINES),
    [filteredSubtitleLines],
  );

  // Active line is tracked against the (filtered) rendered list so highlighting
  // and auto-scroll stay aligned with what's actually on screen.
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || renderLines.length === 0) {
      // Defer the reset so we don't setState synchronously in the effect body.
      const resetId = window.requestAnimationFrame(() => setActiveIndex(-1));
      return () => window.cancelAnimationFrame(resetId);
    }

    let lastRun = 0;
    let rafId = 0;

    const computeActiveLine = () => {
      const currentTime = videoEl.currentTime || 0;
      let matchedIndex = -1;
      for (let idx = 0; idx < renderLines.length; idx += 1) {
        const line = renderLines[idx];
        const start = Number(line.start_seconds ?? NaN);
        if (Number.isNaN(start) || start > currentTime) continue;
        const next = renderLines[idx + 1];
        const end = Number(
          line.end_seconds ?? (next ? Number(next.start_seconds ?? NaN) : NaN),
        );
        const withinEnd = Number.isNaN(end) ? true : currentTime < end;
        if (withinEnd) {
          matchedIndex = idx;
          break;
        }
      }
      setActiveIndex((prev) => (prev === matchedIndex ? prev : matchedIndex));
    };

    // timeupdate fires ~4x/s; throttle so we never recompute more than needed.
    const onTimeUpdate = () => {
      const now = Date.now();
      if (now - lastRun < ACTIVE_SYNC_INTERVAL) return;
      lastRun = now;
      computeActiveLine();
    };

    rafId = window.requestAnimationFrame(computeActiveLine);
    videoEl.addEventListener("timeupdate", onTimeUpdate);
    videoEl.addEventListener("seeked", computeActiveLine);
    return () => {
      window.cancelAnimationFrame(rafId);
      videoEl.removeEventListener("timeupdate", onTimeUpdate);
      videoEl.removeEventListener("seeked", computeActiveLine);
    };
  }, [renderLines, videoRef]);

  const onListScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  // Keep the active subtitle line centered within its scroll container.
  useEffect(() => {
    if (activeIndex < 0) return;
    const container = listScrollRef.current;
    if (!container) return;
    const targetTop = activeIndex * ESTIMATED_ROW_HEIGHT;
    const targetBottom = targetTop + ESTIMATED_ROW_HEIGHT;
    const viewTop = container.scrollTop;
    const viewBottom = viewTop + container.clientHeight;
    if (targetTop < viewTop || targetBottom > viewBottom) {
      container.scrollTo({
        top: Math.max(0, targetTop - container.clientHeight / 2 + ESTIMATED_ROW_HEIGHT / 2),
        behavior: "smooth",
      });
    }
  }, [activeIndex]);

  // Windowing: only mount the rows visible in the viewport (+ overscan).
  const totalHeight = renderLines.length * ESTIMATED_ROW_HEIGHT;
  const firstVisible = Math.max(
    0,
    Math.floor(scrollTop / ESTIMATED_ROW_HEIGHT) - OVERSCAN_ROWS,
  );
  const lastVisible = Math.min(
    renderLines.length,
    Math.ceil((scrollTop + LIST_VIEWPORT_HEIGHT) / ESTIMATED_ROW_HEIGHT) + OVERSCAN_ROWS,
  );
  const windowedLines = renderLines.slice(firstVisible, lastVisible);

  return (
    <section className="panel-card motion-enter result-heavy-surface rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StepsIcon className="h-4 w-4 text-neutral-300" />
          <h2 className="text-base font-semibold">字幕工作台</h2>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={subtitleRefreshing}
            onClick={onRefresh}
          >
            {subtitleRefreshing ? "重新加载中..." : "重新加载字幕"}
          </button>
          <button
            type="button"
            className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={subtitleLoading || subtitleRefreshing}
            onClick={onDownload}
          >
            下载字幕
          </button>
        </div>
      </div>

      {videoSrc ? (
        <div className="mb-2 overflow-hidden rounded border border-neutral-800 bg-black/40">
          <video
            ref={videoRef}
            controls
            preload="auto"
            playsInline
            className="max-h-[300px] w-full bg-black"
            src={videoSrc}
          />
        </div>
      ) : null}

      {subtitleRefreshing ? (
        <div className="subtitle-refresh-anim mb-2" role="status" aria-label="正在重新加载字幕">
          <span className="subtitle-refresh-anim__dot" />
          <span className="subtitle-refresh-anim__dot" />
          <span className="subtitle-refresh-anim__dot" />
          <span className="subtitle-refresh-anim__track" />
        </div>
      ) : null}

      {subtitleLoading ? (
        <p className="rounded border border-neutral-800 bg-neutral-950/60 px-3 py-2 text-sm text-neutral-300">
          正在加载字幕...
        </p>
      ) : subtitleLines.length > 0 ? (
        <>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <input
              type="text"
              className="subtitle-search-input w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-500 sm:max-w-xs"
              placeholder="搜索字幕内容或时间点"
              value={subtitleKeyword}
              onChange={(e) => onKeywordChange(e.target.value)}
            />
            <p className="text-xs text-neutral-400">
              共 {subtitleLines.length} 行，匹配 {filteredSubtitleLines.length} 行
            </p>
          </div>
          <div
            ref={listScrollRef}
            onScroll={onListScroll}
            className="history-scroll max-h-[340px] overflow-auto pr-1"
          >
            <div style={{ position: "relative", height: totalHeight }}>
              {windowedLines.map((line, localIdx) => {
                const idx = firstVisible + localIdx;
                const isActive = idx === activeIndex;
                return (
                  <SubtitleRow
                    key={lineKey(line, idx)}
                    line={line}
                    top={idx * ESTIMATED_ROW_HEIGHT}
                    isActive={isActive}
                    rowRef={isActive ? (el) => (activeLineRef.current = el) : null}
                    onSeek={onSeek}
                    formatDisplayTime={formatDisplayTime}
                  />
                );
              })}
            </div>
          </div>
        </>
      ) : subtitleAssetAvailable ? (
        <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          <p>已检测到字幕文件，但当前未加载到字幕行。你可以点击“重新加载字幕”，或直接下载字幕压缩包。</p>
          {subtitleFile ? (
            <p className="mt-1 text-xs text-amber-200/90">
              字幕文件：{subtitleFile}
              {Number(resultData?.subtitle_line_count || 0) > 0
                ? `（约 ${Number(resultData?.subtitle_line_count || 0)} 行）`
                : ""}
            </p>
          ) : null}
          {subtitleLoadError ? (
            <p className="mt-1 text-xs text-amber-200/90">加载原因：{subtitleLoadError}</p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-amber-400/50 bg-amber-500/15 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/25 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={subtitleRefreshing}
              onClick={onRefresh}
            >
              {subtitleRefreshing ? "重新加载中..." : "重新加载字幕"}
            </button>
            <button
              type="button"
              className="rounded border border-amber-400/50 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:bg-amber-500/15 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={subtitleLoading || subtitleRefreshing}
              onClick={onDownload}
            >
              下载字幕压缩包
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded border border-neutral-800 bg-neutral-950/60 px-3 py-2 text-sm text-neutral-300">
          <p>当前结果未检测到可用字幕。你可以切换字幕模式重新分析，或检查音频质量后重试。</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded border border-neutral-700 px-2.5 py-1 text-xs font-medium text-neutral-200 transition-colors hover:border-teal-400/60 hover:text-teal-100 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={subtitleRefreshing}
              onClick={onRefresh}
            >
              {subtitleRefreshing ? "重新加载中..." : "重试加载字幕"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
});
