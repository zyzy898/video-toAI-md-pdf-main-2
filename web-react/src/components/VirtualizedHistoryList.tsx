import { memo, useCallback, useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import {
  HISTORY_VIRTUAL_ITEM_HEIGHT,
  HISTORY_VIRTUAL_OVERSCAN,
} from "../constants/app";
import type { HistoryItem } from "../types/api";
import { HistoryEmptyIllustration, TrashIcon } from "./icons";

type VirtualizedHistoryListProps = {
  active: boolean;
  history: HistoryItem[];
  clearingHistory: boolean;
  deletingHistoryId: string;
  onOpenRecord: (id: string) => void;
  onDeleteRecord: (record: HistoryItem) => void;
};

export const VirtualizedHistoryList = memo(function VirtualizedHistoryList({
  active,
  history,
  clearingHistory,
  deletingHistoryId,
  onOpenRecord,
  onDeleteRecord,
}: VirtualizedHistoryListProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  const totalHeight = useMemo(
    () => history.length * HISTORY_VIRTUAL_ITEM_HEIGHT,
    [history.length],
  );

  const startIndex = useMemo(
    () =>
      Math.max(
        0,
        Math.floor(scrollTop / HISTORY_VIRTUAL_ITEM_HEIGHT) - HISTORY_VIRTUAL_OVERSCAN,
      ),
    [scrollTop],
  );

  const endIndex = useMemo(() => {
    const visibleCount =
      Math.ceil((viewportHeight || 1) / HISTORY_VIRTUAL_ITEM_HEIGHT) +
      HISTORY_VIRTUAL_OVERSCAN * 2;
    return Math.min(history.length, startIndex + visibleCount);
  }, [history.length, startIndex, viewportHeight]);

  const visibleItems = useMemo(
    () => history.slice(startIndex, endIndex),
    [endIndex, history, startIndex],
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const syncHeight = () => setViewportHeight(el.clientHeight);
    syncHeight();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => syncHeight());
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!active) return;
    const frame = window.requestAnimationFrame(() => {
      if (containerRef.current) setViewportHeight(containerRef.current.clientHeight);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [active, history.length]);

  useEffect(() => {
    const maxScroll = Math.max(0, totalHeight - viewportHeight);
    if (scrollTop <= maxScroll) return;
    setScrollTop(maxScroll);
    if (containerRef.current) containerRef.current.scrollTop = maxScroll;
  }, [scrollTop, totalHeight, viewportHeight]);

  const handleScroll = useCallback((event: UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  if (history.length === 0) {
    return (
      <div className="history-scroll history-scroll-empty flex-1 overflow-auto px-4 py-3">
        <div className="history-empty-state">
          <div className="history-empty-art">
            <HistoryEmptyIllustration className="h-24 w-24" />
          </div>
          <p className="history-empty-title">还没有历史记录</p>
          <p className="history-empty-desc">
            上传并分析视频后，结果会自动保存在这里。
            <br />
            你可以随时回看、继续编辑或下载文档。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="history-scroll flex-1 overflow-auto px-4 py-3"
      onScroll={handleScroll}
    >
      <div className="relative" style={{ height: `${totalHeight}px` }}>
        {visibleItems.map((record, offset) => {
          const index = startIndex + offset;
          return (
            <div
              key={record.id}
              className="history-virtual-item absolute left-0 right-0"
              style={{
                top: `${index * HISTORY_VIRTUAL_ITEM_HEIGHT}px`,
                paddingBottom: "8px",
              }}
            >
              <div className="list-item-pop rounded border border-neutral-800 bg-neutral-950/60 p-2">
                <div className="flex items-start justify-between gap-2">
                  <button
                    className="min-w-0 flex-1 text-left"
                    onClick={() => onOpenRecord(record.id)}
                  >
                    <p className="truncate text-sm font-medium">{record.video_name}</p>
                    <p className="truncate text-xs text-neutral-500">
                      {record.mode === "video" ? "视频模式" : "字幕模式"} ·{" "}
                      {record.steps_count || 0} 步 · {record.timestamp || ""}
                    </p>
                  </button>
                  <button
                    type="button"
                    title="删除记录"
                    aria-label="删除记录"
                    className="inline-flex h-7 w-7 items-center justify-center rounded border border-rose-500/40 text-rose-300 transition-colors hover:bg-rose-500/10 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => onDeleteRecord(record)}
                    disabled={clearingHistory || Boolean(deletingHistoryId)}
                  >
                    <TrashIcon />
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});
