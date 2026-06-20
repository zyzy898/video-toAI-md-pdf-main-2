import { memo, useEffect, useRef, useState } from "react";
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

  const [activeLineId, setActiveLineId] = useState<string | null>(null);
  const listScrollRef = useRef<HTMLDivElement | null>(null);
  const activeLineRef = useRef<HTMLButtonElement | null>(null);

  const lineId = (line: SubtitleLine, idx: number) =>
    `${line.index ?? idx}:${Number(line.start_seconds ?? -1)}`;

  // Track the subtitle line under the current playhead while the video plays.
  useEffect(() => {
    const videoEl = videoRef.current;
    if (!videoEl || subtitleLines.length === 0) return;

    const computeActiveLine = () => {
      const currentTime = videoEl.currentTime || 0;
      let matchedId: string | null = null;
      for (let idx = 0; idx < subtitleLines.length; idx += 1) {
        const line = subtitleLines[idx];
        const start = Number(line.start_seconds ?? NaN);
        if (Number.isNaN(start) || start > currentTime) continue;
        const next = subtitleLines[idx + 1];
        const end = Number(
          line.end_seconds ?? (next ? Number(next.start_seconds ?? NaN) : NaN),
        );
        const withinEnd = Number.isNaN(end) ? true : currentTime < end;
        if (withinEnd) {
          matchedId = lineId(line, idx);
          break;
        }
      }
      setActiveLineId((prev) => (prev === matchedId ? prev : matchedId));
    };

    // Defer the initial sync so we don't setState synchronously in the effect body.
    const rafId = window.requestAnimationFrame(computeActiveLine);
    videoEl.addEventListener("timeupdate", computeActiveLine);
    videoEl.addEventListener("seeked", computeActiveLine);
    return () => {
      window.cancelAnimationFrame(rafId);
      videoEl.removeEventListener("timeupdate", computeActiveLine);
      videoEl.removeEventListener("seeked", computeActiveLine);
    };
  }, [subtitleLines, videoRef]);

  // Keep the active subtitle line visible inside its own scroll container.
  useEffect(() => {
    if (!activeLineId) return;
    const target = activeLineRef.current;
    const container = listScrollRef.current;
    if (!target || !container) return;
    const targetTop = target.offsetTop;
    const targetBottom = targetTop + target.offsetHeight;
    const viewTop = container.scrollTop;
    const viewBottom = viewTop + container.clientHeight;
    if (targetTop < viewTop || targetBottom > viewBottom) {
      container.scrollTo({
        top: targetTop - container.clientHeight / 2 + target.offsetHeight / 2,
        behavior: "smooth",
      });
    }
  }, [activeLineId]);

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
            preload="metadata"
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
          <div ref={listScrollRef} className="history-scroll max-h-[340px] space-y-1 overflow-auto pr-1">
            {filteredSubtitleLines.slice(0, 1200).map((line, idx) => {
              const id = lineId(line, idx);
              const isActive = id === activeLineId;
              return (
                <button
                  type="button"
                  ref={isActive ? activeLineRef : null}
                  key={`sub-line-${line.index || idx}-${line.start_time || ""}`}
                  aria-current={isActive ? "true" : undefined}
                  className={`subtitle-line-row w-full rounded border px-2 py-1.5 text-left text-xs transition-colors ${
                    isActive
                      ? "subtitle-line-row--active border-teal-400/70 bg-teal-500/15"
                      : "border-neutral-800 bg-neutral-950/60 hover:border-teal-400/60 hover:bg-teal-500/10"
                  }`}
                  onClick={() => onSeek(Number(line.start_seconds || 0))}
                >
                  <p className="font-semibold text-teal-200/95">
                    {formatDisplayTime(line.start_time)} - {formatDisplayTime(line.end_time)}
                  </p>
                  <p className="mt-0.5 whitespace-pre-wrap text-neutral-200">{String(line.text || "")}</p>
                </button>
              );
            })}
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
