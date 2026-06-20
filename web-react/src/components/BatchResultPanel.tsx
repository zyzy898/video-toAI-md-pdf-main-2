import { memo, useMemo, useState } from "react";
import type { BatchResultData, BatchResultItem } from "../types/api";
import {
  DownloadSingleIcon,
  DownloadZipIcon,
  StackIcon,
  StatusFailedIcon,
  StatusSuccessIcon,
} from "./icons";
import { CONTENT_POLICY_BLOCK_MESSAGE } from "../constants/app";

type BatchStatus = "success" | "degraded" | "blocked" | "failed";

type BatchResultPanelProps = {
  data: BatchResultData;
  onDownloadAll: () => void;
  onDownloadItem: (outputDir: string | undefined, filename: string | undefined) => void;
  onOpenItem: (item: BatchResultItem) => void;
};

const classifyItem = (item: BatchResultItem): BatchStatus => {
  if (item.success) {
    return item.result_mode === "candidate_steps" || item.result_mode === "timeline_summary"
      ? "degraded"
      : "success";
  }
  if (item.result_mode === "blocked_notice" || item.code === "content_policy_violation") {
    return "blocked";
  }
  return "failed";
};

const STATUS_META: Record<BatchStatus, { label: string; tone: string }> = {
  success: { label: "成功", tone: "batch-status--ok" },
  degraded: { label: "已完成（降级）", tone: "batch-status--warn" },
  blocked: { label: "已拦截", tone: "batch-status--warn" },
  failed: { label: "失败", tone: "batch-status--fail" },
};

const FILTERS: Array<{ key: "all" | BatchStatus; label: string }> = [
  { key: "all", label: "全部" },
  { key: "success", label: "成功" },
  { key: "degraded", label: "降级" },
  { key: "blocked", label: "拦截" },
  { key: "failed", label: "失败" },
];

// PLACEHOLDER_BODY
export const BatchResultPanel = memo(function BatchResultPanel({
  data,
  onDownloadAll,
  onDownloadItem,
  onOpenItem,
}: BatchResultPanelProps) {
  const [filter, setFilter] = useState<"all" | BatchStatus>("all");
  const [keyword, setKeyword] = useState("");

  const results = useMemo(() => data.results || [], [data.results]);

  const counts = useMemo(() => {
    const base = { total: results.length, success: 0, degraded: 0, blocked: 0, failed: 0 };
    for (const item of results) {
      base[classifyItem(item)] += 1;
    }
    return base;
  }, [results]);

  const downloadable = useMemo(
    () => results.filter((item) => item.success && item.output_dir).length,
    [results],
  );

  const visibleResults = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    return results.filter((item) => {
      if (filter !== "all" && classifyItem(item) !== filter) return false;
      if (kw && !String(item.filename || "").toLowerCase().includes(kw)) return false;
      return true;
    });
  }, [results, filter, keyword]);

  const warnings = data.batch_policy_warnings || [];

  return (
    <section className="panel-card motion-enter rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <StackIcon className="h-4 w-4 text-neutral-300" />
          <h2 className="text-base font-semibold">批量处理结果</h2>
        </div>
        <button
          className="zip-download-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs disabled:cursor-not-allowed disabled:opacity-50"
          disabled={downloadable === 0}
          onClick={onDownloadAll}
        >
          <DownloadZipIcon className="h-3.5 w-3.5" />
          下载批量 ZIP{downloadable > 0 ? `（${downloadable}）` : ""}
        </button>
      </div>

      <div className="batch-stat-grid mb-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <BatchStatCard label="总计" value={counts.total} tone="total" />
        <BatchStatCard label="成功" value={counts.success + counts.degraded} tone="ok" />
        <BatchStatCard label="拦截" value={counts.blocked} tone="warn" />
        <BatchStatCard label="失败" value={counts.failed} tone="fail" />
      </div>

      {warnings.length > 0 ? (
        <div className="mb-3 rounded border border-amber-400/35 bg-amber-500/10 p-2 text-xs text-amber-200/95">
          <p className="font-semibold">批次策略提醒</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {warnings.slice(0, 3).map((tip, idx) => (
              <li key={`batch-policy-warning-${idx}`}>{tip}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1.5">
          {FILTERS.map((f) => {
            const count =
              f.key === "all"
                ? counts.total
                : f.key === "success"
                  ? counts.success
                  : f.key === "degraded"
                    ? counts.degraded
                    : f.key === "blocked"
                      ? counts.blocked
                      : counts.failed;
            if (f.key !== "all" && count === 0) return null;
            return (
              <button
                key={f.key}
                type="button"
                aria-pressed={filter === f.key}
                className={`batch-filter-chip ${filter === f.key ? "batch-filter-chip--active" : ""}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label} {count}
              </button>
            );
          })}
        </div>
        {results.length > 6 ? (
          <input
            type="text"
            className="batch-search-input ml-auto w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-xs text-neutral-100 placeholder:text-neutral-500 sm:w-44"
            placeholder="搜索文件名"
            value={keyword}
            onChange={(e) => setKeyword(e.target.value)}
          />
        ) : null}
      </div>

      {visibleResults.length === 0 ? (
        <p className="rounded border border-neutral-800 bg-neutral-950/60 px-3 py-4 text-center text-sm text-neutral-400">
          没有符合条件的结果
        </p>
      ) : (
        <div className="space-y-2">
          {visibleResults.map((item, i) => (
            <BatchResultRow
              key={`${item.filename}-${item.index ?? i}`}
              item={item}
              onDownload={() => onDownloadItem(item.output_dir, item.filename)}
              onOpen={() => onOpenItem(item)}
            />
          ))}
        </div>
      )}
    </section>
  );
});

// PLACEHOLDER_SUBCOMPONENTS
const BatchStatCard = memo(function BatchStatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "total" | "ok" | "warn" | "fail";
}) {
  return (
    <div className={`batch-stat-card batch-stat-card--${tone}`}>
      <span className="batch-stat-value">{value}</span>
      <span className="batch-stat-label">{label}</span>
    </div>
  );
});

const BatchResultRow = memo(function BatchResultRow({
  item,
  onDownload,
  onOpen,
}: {
  item: BatchResultItem;
  onDownload: () => void;
  onOpen: () => void;
}) {
  const status = classifyItem(item);
  const meta = STATUS_META[status];
  const isBlocked = status === "blocked";
  const isDownloadable = item.success && Boolean(item.output_dir);
  const canOpen = item.success && Boolean(item.output_dir);

  return (
    <div className={`batch-result-row batch-result-row--${status} rounded border border-neutral-800 bg-neutral-950/60 p-2.5`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2">
          {status === "failed" ? (
            <StatusFailedIcon className="mt-0.5 h-4 w-4 shrink-0 text-rose-300" />
          ) : status === "success" || status === "degraded" ? (
            <StatusSuccessIcon className="mt-0.5 h-4 w-4 shrink-0 text-emerald-300" />
          ) : (
            <StatusFailedIcon className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
          )}
          <div className="min-w-0">
            {canOpen ? (
              <button
                type="button"
                className="batch-row-title-btn truncate text-left text-sm font-medium text-neutral-100"
                title={`查看「${item.filename}」详情`}
                onClick={onOpen}
              >
                {item.filename}
              </button>
            ) : (
              <p className="truncate text-sm font-medium text-neutral-100" title={item.filename}>
                {item.filename}
              </p>
            )}
            {item.content_title && item.content_title !== item.filename ? (
              <p className="truncate text-xs text-neutral-400" title={item.content_title}>
                {item.content_title}
              </p>
            ) : null}
          </div>
        </div>
        <span className={`batch-status ${meta.tone} shrink-0`}>{meta.label}</span>
      </div>

      {isDownloadable ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <button
            className="batch-open-btn flex items-center gap-1 rounded border px-2 py-1 text-xs font-medium"
            onClick={onOpen}
          >
            查看详情
          </button>
          <button
            className="zip-download-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
            onClick={onDownload}
          >
            <DownloadSingleIcon className="h-3.5 w-3.5" />
            下载
          </button>
          {typeof item.steps_count === "number" && item.steps_count > 0 ? (
            <span className="text-xs text-neutral-500">步骤 {item.steps_count}</span>
          ) : null}
          {item.fallback_used ? (
            <span className="text-xs text-amber-300/90">
              {(item.analysis_note || "未识别到标准步骤，已自动生成候选内容。") +
                `（质量分：${Number(item.quality_score || 0).toFixed(2)}）`}
            </span>
          ) : null}
        </div>
      ) : isBlocked ? (
        <div className="mt-2 rounded border border-rose-500/45 bg-rose-500/10 p-2 text-xs text-rose-200/95">
          <p className="font-semibold">{item.blocked_notice?.title || "安全检测未通过（已拦截）"}</p>
          <p className="mt-1">
            等级：{String(item.blocked_notice?.risk_level || item.risk?.risk_level || "high")} · 规则：
            {String(item.blocked_notice?.reason_code || item.risk?.reason_code || "CONTENT_POLICY_VIOLATION")}
          </p>
          <p className="mt-1 break-words">
            {String(item.blocked_notice?.reason || item.risk?.reason || item.error || CONTENT_POLICY_BLOCK_MESSAGE)}
          </p>
          {(item.blocked_notice?.suggestions || []).length > 0 ? (
            <ul className="mt-1 list-disc space-y-1 pl-4">
              {(item.blocked_notice?.suggestions || []).slice(0, 3).map((tip, idx) => (
                <li key={`b-tip-${idx}`}>{tip}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : (
        <p className="mt-2 text-xs text-rose-300 break-words">{item.error || "处理失败"}</p>
      )}
    </div>
  );
});

