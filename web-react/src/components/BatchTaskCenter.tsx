import { memo, useMemo, useState } from "react";
import { STAGE_LABELS } from "../constants/app";
import {
  TASK_STATUS_LABELS,
  selectBatchTaskCenterItems,
} from "../lib/task-lifecycle";
import type { AnalysisTaskQueueItem, AnalysisTaskStatus } from "../types/api";
import {
  CloseIcon,
  EyeIcon,
  RefreshIcon,
  StackIcon,
} from "./icons";

type TaskFilter = "all" | AnalysisTaskStatus;

type BatchTaskCenterProps = {
  tasks: AnalysisTaskQueueItem[];
  actionTaskId: string;
  notificationEnabled: boolean;
  notificationPermission: NotificationPermission | "unsupported";
  onToggleNotifications: () => void;
  onCancel: (task: AnalysisTaskQueueItem) => void;
  onRetry: (task: AnalysisTaskQueueItem) => void;
  onOpen: (task: AnalysisTaskQueueItem) => void;
};

const FILTERS: Array<{ key: TaskFilter; label: string }> = [
  { key: "all", label: "全部" },
  { key: "queued", label: "排队" },
  { key: "analyzing", label: "分析中" },
  { key: "completed", label: "已完成" },
  { key: "failed", label: "失败" },
  { key: "cancelled", label: "已取消" },
];

const permissionLabel = (
  enabled: boolean,
  permission: NotificationPermission | "unsupported",
) => {
  if (permission === "unsupported") return "浏览器不支持";
  if (permission === "denied") return "浏览器已拒绝";
  return enabled ? "系统通知已开启" : "系统通知未开启";
};

export const BatchTaskCenter = memo(function BatchTaskCenter({
  tasks,
  actionTaskId,
  notificationEnabled,
  notificationPermission,
  onToggleNotifications,
  onCancel,
  onRetry,
  onOpen,
}: BatchTaskCenterProps) {
  const [filter, setFilter] = useState<TaskFilter>("all");
  const allBatchTasks = useMemo(
    () => selectBatchTaskCenterItems(tasks),
    [tasks],
  );
  const visibleTasks = useMemo(
    () => selectBatchTaskCenterItems(tasks, filter),
    [filter, tasks],
  );
  const counts = useMemo(() => {
    const next = new Map<TaskFilter, number>([["all", allBatchTasks.length]]);
    for (const task of allBatchTasks) {
      next.set(task.status, (next.get(task.status) || 0) + 1);
    }
    return next;
  }, [allBatchTasks]);

  if (allBatchTasks.length === 0) return null;

  return (
    <section className="panel-card rounded-lg border border-neutral-800 bg-neutral-900/70 p-4" aria-label="批量任务中心">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className="vi-card-title-ico"><StackIcon className="h-4 w-4" /></span>
          <div>
            <h2 className="text-base font-semibold text-neutral-100">批量任务中心</h2>
            <p className="mt-0.5 text-xs text-neutral-400">共 {allBatchTasks.length} 个批次</p>
          </div>
        </div>
        <label className="inline-flex min-h-8 cursor-pointer items-center gap-2 text-xs text-neutral-300">
          <input
            type="checkbox"
            checked={notificationEnabled}
            onChange={onToggleNotifications}
            className="h-4 w-4 accent-cyan-500"
          />
          <span>{permissionLabel(notificationEnabled, notificationPermission)}</span>
        </label>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" role="tablist" aria-label="批量任务状态筛选">
        {FILTERS.map((item) => {
          const count = counts.get(item.key) || 0;
          if (item.key !== "all" && count === 0) return null;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={filter === item.key}
              className={`batch-filter-chip ${filter === item.key ? "batch-filter-chip--active" : ""}`}
              onClick={() => setFilter(item.key)}
            >
              {item.label} {count}
            </button>
          );
        })}
      </div>

      <div className="mt-3 space-y-2">
        {visibleTasks.map((task) => {
          const busy = actionTaskId === task.taskId;
          const canCancel = ["uploading", "queued", "analyzing"].includes(task.status);
          const canRetry = task.retryable && ["failed", "cancelled"].includes(task.status);
          const canOpen = task.status === "completed";
          const percent = Math.max(0, Math.min(100, Math.round(task.percent || 0)));
          return (
            <div
              key={task.taskId}
              className="vi-task-row rounded border border-neutral-800 bg-neutral-950/55 px-3 py-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-neutral-100" title={task.label}>
                    {task.label}
                  </p>
                  <p className="mt-0.5 text-xs text-neutral-400">
                    {TASK_STATUS_LABELS[task.status]}
                    {task.stage ? ` · ${STAGE_LABELS[task.stage] || task.stage}` : ""}
                    {task.total > 0 ? ` · ${task.current}/${task.total}` : ""}
                  </p>
                  {task.currentFile ? (
                    <p className="mt-1 truncate text-xs text-neutral-500" title={task.currentFile}>
                      当前：{task.currentFile}
                    </p>
                  ) : null}
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  <span
                    className={`vi-status ${task.status === "failed" ? "vi-status--fail" : ""} ${canCancel ? "vi-status--run" : ""}`}
                  >
                    {TASK_STATUS_LABELS[task.status]}
                  </span>
                  {canOpen ? (
                    <button
                      type="button"
                      className="vi-icon-btn"
                      title="查看批量结果"
                      aria-label={`查看 ${task.label} 的批量结果`}
                      onClick={() => onOpen(task)}
                    >
                      <EyeIcon />
                    </button>
                  ) : null}
                  {canRetry ? (
                    <button
                      type="button"
                      className="vi-icon-btn"
                      title="重试任务"
                      aria-label={`重试 ${task.label}`}
                      disabled={Boolean(actionTaskId)}
                      onClick={() => onRetry(task)}
                    >
                      <RefreshIcon className={busy ? "h-4 w-4 animate-spin" : "h-4 w-4"} />
                    </button>
                  ) : null}
                  {canCancel ? (
                    <button
                      type="button"
                      className="vi-icon-btn vi-icon-btn--danger"
                      title="取消任务"
                      aria-label={`取消 ${task.label}`}
                      disabled={Boolean(actionTaskId) || task.cancelRequested}
                      onClick={() => onCancel(task)}
                    >
                      <CloseIcon />
                    </button>
                  ) : null}
                </div>
              </div>
              {task.message ? (
                <p className={`mt-1.5 text-xs break-words ${task.status === "failed" ? "text-rose-300" : "text-neutral-300"}`}>
                  {task.message}
                </p>
              ) : null}
              {canCancel ? (
                <div className="vi-progress-track mt-2" aria-label={`任务进度 ${percent}%`}>
                  <div className="vi-progress-bar" style={{ width: `${percent}%` }} />
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </section>
  );
});

