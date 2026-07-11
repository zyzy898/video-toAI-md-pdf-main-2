import type {
  AnalysisTaskFileProgress,
  AnalysisTaskKind,
  AnalysisTaskListItem,
  AnalysisTaskPayload,
  AnalysisTaskQueueItem,
  AnalysisTaskStatus,
  AnalysisTaskStatusResponse,
  BatchFileItem,
  BatchResultItem,
  FileStatus,
} from "../types/api.ts";

export const TASK_LIFECYCLE_STORAGE_KEY = "video-analysis-lifecycle-v1";

export const TASK_STATUS_LABELS: Record<AnalysisTaskStatus, string> = {
  uploading: "上传中",
  queued: "排队中",
  analyzing: "分析中",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export type PersistedLifecycleState = {
  version: 1;
  tasks: AnalysisTaskQueueItem[];
  uploads: BatchFileItem[];
};

export type ResultPresentationToken = {
  taskId: string;
  revision: number;
};

export type CachedTaskResult<TSingle = unknown, TBatch = unknown> =
  | { taskId: string; kind: "single" | "url"; data: TSingle }
  | { taskId: string; kind: "batch"; data: TBatch };

type StorageLike = {
  getItem: (key: string) => string | null;
  setItem: (key: string, value: string) => void;
  removeItem: (key: string) => void;
};
type StorageSource<T extends keyof StorageLike> = Pick<StorageLike, T> | (() => Pick<StorageLike, T>);

const resolveStorage = <T extends keyof StorageLike>(
  source: StorageSource<T> | null | undefined,
): Pick<StorageLike, T> | null | undefined =>
  typeof source === "function" ? source() : source;

const EMPTY_STATE: PersistedLifecycleState = { version: 1, tasks: [], uploads: [] };
const TASK_KINDS = new Set<AnalysisTaskKind>(["single", "batch", "url"]);
const TASK_STATUSES = new Set<AnalysisTaskStatus>([
  "uploading",
  "queued",
  "analyzing",
  "completed",
  "failed",
  "cancelled",
]);
const FILE_STATUSES = new Set<FileStatus>([
  "pending",
  "uploading",
  "processing",
  "success",
  "failed",
  "cancelled",
]);
const TASK_FILE_STATUSES = new Set<AnalysisTaskFileProgress["status"]>([
  "waiting",
  "analyzing",
  "success",
  "failed",
]);

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const safeString = (value: unknown) => String(value ?? "").trim();
const safeNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const sanitizeFileProgress = (value: unknown): AnalysisTaskFileProgress[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map((entry) => {
      const raw = asRecord(entry);
      const index = Math.floor(safeNumber(raw.index));
      const status = safeString(raw.status) as AnalysisTaskFileProgress["status"];
      if (index < 1 || !TASK_FILE_STATUSES.has(status)) return null;
      return {
        index,
        filename: safeString(raw.filename),
        status,
        stage: safeString(raw.stage),
        message: safeString(raw.message),
      };
    })
    .filter((entry): entry is AnalysisTaskFileProgress => Boolean(entry));
};

const sanitizeTaskPayload = (kind: AnalysisTaskKind, value: unknown): AnalysisTaskPayload => {
  const raw = asRecord(value);
  const payload: AnalysisTaskPayload = {};
  if (kind === "single") {
    const filepath = safeString(raw.filepath);
    if (filepath) payload.filepath = filepath;
  } else if (kind === "batch") {
    const filepaths = Array.isArray(raw.filepaths)
      ? raw.filepaths.map(safeString).filter(Boolean)
      : [];
    if (filepaths.length > 0) payload.filepaths = filepaths;
  } else {
    const url = safeString(raw.url);
    const filename = safeString(raw.filename);
    if (url) payload.url = url;
    if (filename) payload.filename = filename;
  }
  if (typeof raw.summary_only === "boolean") payload.summary_only = raw.summary_only;
  if (typeof raw.web_search === "boolean") payload.web_search = raw.web_search;
  if (Number.isFinite(Number(raw.max_vision))) payload.max_vision = Number(raw.max_vision);
  if (raw.output_template === "operation_guide" || raw.output_template === "content_summary") {
    payload.output_template = raw.output_template;
  }
  return payload;
};

const sanitizeTask = (value: unknown): AnalysisTaskQueueItem | null => {
  const raw = asRecord(value);
  const taskId = safeString(raw.taskId);
  const kind = safeString(raw.kind) as AnalysisTaskKind;
  const status = safeString(raw.status) as AnalysisTaskStatus;
  if (!taskId || !TASK_KINDS.has(kind) || !TASK_STATUSES.has(status)) return null;
  return {
    taskId,
    kind,
    status,
    stage: safeString(raw.stage),
    message: safeString(raw.message),
    percent: Math.max(0, Math.min(100, safeNumber(raw.percent))),
    total: Math.max(0, safeNumber(raw.total)),
    current: Math.max(0, safeNumber(raw.current)),
    currentFile: safeString(raw.currentFile),
    fileProgress: sanitizeFileProgress(raw.fileProgress),
    retryable: Boolean(raw.retryable),
    cancelRequested: Boolean(raw.cancelRequested),
    attemptCount: Math.max(0, safeNumber(raw.attemptCount)),
    recoveryCount: Math.max(0, safeNumber(raw.recoveryCount)),
    payload: sanitizeTaskPayload(kind, raw.payload),
    label: safeString(raw.label) || "分析任务",
    clientId: safeString(raw.clientId) || undefined,
    createdAt: safeString(raw.createdAt) || new Date(0).toISOString(),
  };
};

const sanitizeUpload = (value: unknown): BatchFileItem | null => {
  const raw = asRecord(value);
  const filename = safeString(raw.filename);
  const filepath = safeString(raw.filepath);
  const rawStatus = safeString(raw.status) as FileStatus;
  if (!filename || !FILE_STATUSES.has(rawStatus)) return null;
  const interrupted = !filepath && rawStatus === "uploading";
  return {
    filename,
    filepath,
    status: interrupted ? "uploading" : rawStatus,
    error: interrupted
      ? "刷新后需重新选择同一文件以继续上传。"
      : safeString(raw.error),
    clientId: safeString(raw.clientId) || undefined,
    sourceKey: safeString(raw.sourceKey) || undefined,
    resumeKey: safeString(raw.resumeKey) || undefined,
    size: Math.max(0, safeNumber(raw.size)) || undefined,
    lastModified: Math.max(0, safeNumber(raw.lastModified)) || undefined,
    needsReselect: interrupted || Boolean(raw.needsReselect),
  };
};

const normalizeLifecycleState = (value: unknown): PersistedLifecycleState => {
  const raw = asRecord(value);
  const tasks = Array.isArray(raw.tasks)
    ? raw.tasks.map(sanitizeTask).filter((task): task is AnalysisTaskQueueItem => Boolean(task))
    : [];
  const uploads = Array.isArray(raw.uploads)
    ? raw.uploads.map(sanitizeUpload).filter((upload): upload is BatchFileItem => Boolean(upload))
    : [];
  const taskClientIds = new Set(tasks.map((task) => task.clientId).filter(Boolean));
  const restoredUploads = uploads.map((upload) => {
    const orphanedProcessingRow =
      !upload.filepath &&
      upload.status === "processing" &&
      (!upload.clientId || !taskClientIds.has(upload.clientId));
    if (!orphanedProcessingRow) return upload;
    return {
      ...upload,
      status: "failed" as const,
      error: "页面刷新后链接导入已中断，请重新提交。",
    };
  });
  return { version: 1, tasks, uploads: restoredUploads };
};

export const serializeLifecycleState = (value: unknown): string =>
  JSON.stringify(normalizeLifecycleState(value));

export const parseLifecycleState = (raw: string | null): PersistedLifecycleState => {
  if (!raw) return { ...EMPTY_STATE, tasks: [], uploads: [] };
  try {
    return normalizeLifecycleState(JSON.parse(raw));
  } catch {
    return { ...EMPTY_STATE, tasks: [], uploads: [] };
  }
};

export const mergeTaskStatus = (
  task: AnalysisTaskQueueItem,
  status: AnalysisTaskStatusResponse,
): AnalysisTaskQueueItem => ({
  ...task,
  taskId: safeString(status.task_id) || task.taskId,
  kind: TASK_KINDS.has(status.kind) ? status.kind : task.kind,
  status: TASK_STATUSES.has(status.status) ? status.status : task.status,
  stage: safeString(status.stage),
  message: safeString(status.message),
  percent: Math.max(0, Math.min(100, safeNumber(status.percent))),
  total: Math.max(0, safeNumber(status.total)),
  current: Math.max(0, safeNumber(status.current)),
  currentFile: safeString(status.current_file),
  fileProgress: Array.isArray(status.file_progress)
    ? sanitizeFileProgress(status.file_progress)
    : task.fileProgress,
  retryable: Boolean(status.retryable),
  cancelRequested: Boolean(status.cancel_requested),
  attemptCount: Math.max(0, safeNumber(status.attempt_count)),
  recoveryCount: Math.max(0, safeNumber(status.recovery_count)),
});

export const createTaskQueueItem = (
  status: AnalysisTaskStatusResponse,
  metadata: {
    payload: AnalysisTaskPayload;
    label: string;
    clientId?: string;
    createdAt?: string;
  },
): AnalysisTaskQueueItem =>
  mergeTaskStatus(
    {
      taskId: safeString(status.task_id),
      kind: status.kind,
      status: status.status,
      stage: "",
      message: "",
      percent: 0,
      total: 0,
      current: 0,
      currentFile: "",
      fileProgress: [],
      retryable: false,
      cancelRequested: false,
      attemptCount: 0,
      recoveryCount: 0,
      payload: sanitizeTaskPayload(status.kind, metadata.payload),
      label: safeString(metadata.label) || "分析任务",
      clientId: safeString(metadata.clientId) || undefined,
      createdAt: safeString(metadata.createdAt) || new Date().toISOString(),
    },
    status,
  );

const taskLabelFromPayload = (
  kind: AnalysisTaskKind,
  payload: AnalysisTaskPayload,
): string => {
  if (kind === "batch") {
    const count = payload.filepaths?.length || 0;
    return count > 0 ? `${count} 个视频` : "批量分析任务";
  }
  const rawPath = kind === "url" ? payload.filename || payload.url : payload.filepath;
  const parts = safeString(rawPath).split(/[\\/]/u).filter(Boolean);
  return parts.pop() || (kind === "url" ? "链接分析任务" : "视频分析任务");
};

const taskCreatedAtIso = (value: unknown): string => {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return "";
  const milliseconds = numeric >= 1_000_000_000_000 ? numeric : numeric * 1000;
  const date = new Date(milliseconds);
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
};

export const mergeServerTaskQueue = (
  localTasks: AnalysisTaskQueueItem[],
  serverTasks: AnalysisTaskListItem[],
): AnalysisTaskQueueItem[] => {
  const merged = new Map(localTasks.map((task) => [task.taskId, task]));
  for (const status of serverTasks) {
    const taskId = safeString(status.task_id);
    if (!taskId || !TASK_KINDS.has(status.kind) || !TASK_STATUSES.has(status.status)) continue;
    const local = merged.get(taskId);
    const payload = sanitizeTaskPayload(status.kind, status.payload);
    const task = createTaskQueueItem(status, {
      payload,
      label: local?.label || taskLabelFromPayload(status.kind, payload),
      clientId: local?.clientId,
      createdAt: local?.createdAt || taskCreatedAtIso(status.created_at),
    });
    merged.set(taskId, task);
  }
  return [...merged.values()].sort((left, right) => {
    const leftTime = Date.parse(left.createdAt) || 0;
    const rightTime = Date.parse(right.createdAt) || 0;
    return leftTime - rightTime;
  });
};

export const shouldPollTask = (task: Pick<AnalysisTaskQueueItem, "status">): boolean =>
  task.status === "uploading" || task.status === "queued" || task.status === "analyzing";

const analysisTaskMessage = (task: AnalysisTaskQueueItem): string =>
  task.message ||
  (task.status === "queued"
    ? "正在排队等待分析..."
    : task.status === "analyzing"
      ? "正在分析视频..."
      : TASK_STATUS_LABELS[task.status]);

const updateFileRow = (
  item: BatchFileItem,
  status: FileStatus,
  error: string,
): BatchFileItem =>
  item.status === status && item.error === error ? item : { ...item, status, error };

export const reconcileTaskFiles = (
  files: BatchFileItem[],
  task: AnalysisTaskQueueItem,
): BatchFileItem[] => {
  const targetPaths =
    task.kind === "batch"
      ? task.payload.filepaths || []
      : task.kind === "single" && task.payload.filepath
        ? [task.payload.filepath]
        : [];
  const targetPathSet = new Set(targetPaths);
  const progressByPath = new Map<string, AnalysisTaskFileProgress>();
  const currentFileMatches = task.currentFile
    ? targetPaths.filter((filepath) => {
        if (filepath === task.currentFile) return true;
        const basename = filepath.split(/[\\/]/u).filter(Boolean).pop();
        return basename === task.currentFile;
      })
    : [];
  const currentFilePath = currentFileMatches.length === 1 ? currentFileMatches[0] : "";
  const resetsTerminalRows =
    task.kind === "batch" &&
    task.status === "queued" &&
    task.current === 0 &&
    task.fileProgress.length === 0;
  if (task.kind === "batch") {
    for (const progress of task.fileProgress) {
      const filepath = targetPaths[progress.index - 1];
      if (filepath) progressByPath.set(filepath, progress);
    }
  }

  let changed = false;
  const next = files.map((item) => {
    const matches =
      (task.clientId && item.clientId === task.clientId) ||
      (item.filepath && targetPathSet.has(item.filepath));
    if (!matches) return item;

    if (task.kind === "batch") {
      const progress = progressByPath.get(item.filepath);
      if (progress?.status === "success") {
        const updated = updateFileRow(item, "success", progress.message || "分析完成");
        if (updated !== item) changed = true;
        return updated;
      }
      if (progress?.status === "failed") {
        const updated = updateFileRow(item, "failed", progress.message || "分析失败");
        if (updated !== item) changed = true;
        return updated;
      }
      if (task.status === "failed" || task.status === "cancelled") {
        if (["success", "failed", "cancelled"].includes(item.status)) return item;
        const updated = updateFileRow(
          item,
          task.status,
          analysisTaskMessage(task),
        );
        if (updated !== item) changed = true;
        return updated;
      }
      if (progress) {
        const updated = updateFileRow(
          item,
          "processing",
          progress.message ||
            (progress.status === "waiting" ? "正在等待分析..." : "正在分析视频..."),
        );
        if (updated !== item) changed = true;
        return updated;
      }
      if (task.status === "completed") return item;

      const isCurrentFile = Boolean(currentFilePath && currentFilePath === item.filepath);
      if (isCurrentFile && ["done", "failed", "moderation"].includes(task.stage)) {
        const updated = updateFileRow(
          item,
          task.stage === "done" ? "success" : "failed",
          analysisTaskMessage(task),
        );
        if (updated !== item) changed = true;
        return updated;
      }
      if (isCurrentFile) {
        const updated = updateFileRow(item, "processing", analysisTaskMessage(task));
        if (updated !== item) changed = true;
        return updated;
      }
      if (
        !resetsTerminalRows &&
        ["success", "failed", "cancelled"].includes(item.status)
      ) {
        return item;
      }
      const updated = updateFileRow(
        item,
        "processing",
        task.status === "queued" ? analysisTaskMessage(task) : "正在分析视频...",
      );
      if (updated !== item) changed = true;
      return updated;
    } else if (task.status === "completed") {
      return item;
    }

    const status: FileStatus =
      task.status === "failed"
        ? "failed"
        : task.status === "cancelled"
          ? "cancelled"
          : "processing";
    const updated = updateFileRow(item, status, analysisTaskMessage(task));
    if (updated !== item) changed = true;
    return updated;
  });
  return changed ? next : files;
};

export const upsertTaskQueueItem = <T extends { taskId: string }>(
  tasks: T[],
  task: T,
): T[] => [...tasks.filter((candidate) => candidate.taskId !== task.taskId), task];

export const runExclusiveTaskSubmission = async <T>(
  gate: { current: boolean },
  submit: () => Promise<T>,
): Promise<T | undefined> => {
  if (gate.current) return undefined;
  gate.current = true;
  try {
    return await submit();
  } finally {
    gate.current = false;
  }
};

export const pendingCompletedTasks = <T extends { taskId: string; status: AnalysisTaskStatus }>(
  tasks: T[],
  loadedTaskIds: Iterable<string> = [],
  loadingTaskIds: Iterable<string> = [],
  deferredTaskIds: Iterable<string> = [],
  targetTaskId = "",
): T[] => {
  const targetId = String(targetTaskId || "").trim();
  if (!targetId) return [];
  const loaded = new Set(loadedTaskIds);
  const loading = new Set(loadingTaskIds);
  const deferred = new Set(deferredTaskIds);
  return tasks.filter(
    (task) =>
      task.taskId === targetId &&
      task.status === "completed" &&
      !loaded.has(task.taskId) &&
      !loading.has(task.taskId) &&
      !deferred.has(task.taskId),
  );
};

export const canPresentTaskResult = (
  request: ResultPresentationToken | undefined,
  current: ResultPresentationToken,
): boolean =>
  Boolean(
    request &&
      request.taskId &&
      request.taskId === current.taskId &&
      request.revision === current.revision,
  );

export const cachedTaskResultForPresentation = <TSingle, TBatch>(
  cache: ReadonlyMap<string, CachedTaskResult<TSingle, TBatch>>,
  request: ResultPresentationToken | undefined,
  current: ResultPresentationToken,
): CachedTaskResult<TSingle, TBatch> | undefined => {
  if (!request || !canPresentTaskResult(request, current)) return undefined;
  const cached = cache.get(request.taskId);
  return cached?.taskId === request.taskId ? cached : undefined;
};

export const classifyResultLoadFailure = (httpStatus: number | undefined): "unavailable" | "retry" =>
  httpStatus === 404 ? "unavailable" : "retry";

export const resultLoadRetryDelayMs = (
  attempt: number,
  baseDelayMs = 1000,
  maxDelayMs = 30000,
): number => {
  const safeAttempt = Math.max(0, Math.floor(Number(attempt) || 0));
  const safeBase = Math.max(1, Number(baseDelayMs) || 1000);
  const safeMax = Math.max(safeBase, Number(maxDelayMs) || 30000);
  return Math.min(safeMax, safeBase * 2 ** Math.min(safeAttempt, 30));
};

export const safeStorageGet = (
  storage: StorageSource<"getItem"> | null | undefined,
  key: string,
  fallback = "",
): string => {
  try {
    return resolveStorage(storage)?.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
};

export const safeStorageSet = (
  storage: StorageSource<"setItem"> | null | undefined,
  key: string,
  value: string,
): boolean => {
  try {
    const resolved = resolveStorage(storage);
    resolved?.setItem(key, value);
    return Boolean(resolved);
  } catch {
    return false;
  }
};

export const safeStorageRemove = (
  storage: StorageSource<"removeItem"> | null | undefined,
  key: string,
): boolean => {
  try {
    const resolved = resolveStorage(storage);
    resolved?.removeItem(key);
    return Boolean(resolved);
  } catch {
    return false;
  }
};

export const markTaskUnavailable = (task: AnalysisTaskQueueItem): AnalysisTaskQueueItem => ({
  ...task,
  status: "failed",
  stage: "unavailable",
  message: "任务不存在或已被清理，请重新提交分析。",
  retryable: false,
  cancelRequested: false,
});

export const findReselectableUpload = <
  T extends Pick<BatchFileItem, "sourceKey" | "status" | "needsReselect">
>(uploads: T[], sourceKey: string): T | undefined =>
  uploads.find(
    (upload) =>
      upload.sourceKey === sourceKey &&
      Boolean(upload.needsReselect) &&
      (upload.status === "uploading" || upload.status === "cancelled" || upload.status === "failed"),
  );

export const runUploadCancellation = async (options: {
  uploadId: string;
  abort: () => void;
  cancel: (uploadId: string) => Promise<unknown>;
  clearResume: () => void;
}): Promise<{ confirmed: boolean; error?: unknown }> => {
  options.abort();
  if (!options.uploadId) {
    return {
      confirmed: false,
      error: new Error("上传初始化尚未返回 upload_id，服务端取消未确认。"),
    };
  }
  try {
    await options.cancel(options.uploadId);
  } catch (error) {
    return { confirmed: false, error };
  }
  try {
    options.clearResume();
  } catch {
    // Server cancellation is already confirmed; local cleanup is best-effort.
  }
  return { confirmed: true };
};

export const failedBatchFilepaths = (
  filepaths: string[],
  results: Pick<BatchResultItem, "index" | "filename" | "success" | "code" | "result_mode">[],
): string[] => {
  const normalizedPaths = filepaths.map(safeString);
  const failedPaths = new Set<string>();
  for (const result of results) {
    if (
      result.success ||
      result.result_mode === "blocked_notice" ||
      result.code === "content_policy_violation"
    ) {
      continue;
    }
    const resultIndex = Number(result.index);
    if (Number.isInteger(resultIndex) && resultIndex >= 1 && resultIndex <= normalizedPaths.length) {
      const filepath = normalizedPaths[resultIndex - 1];
      if (filepath) failedPaths.add(filepath);
      continue;
    }
    const filename = safeString(result.filename);
    if (!filename) continue;
    const matchingPaths = normalizedPaths.filter(
      (filepath) => filepath.split(/[\\/]/u).filter(Boolean).pop() === filename,
    );
    if (matchingPaths.length === 1) failedPaths.add(matchingPaths[0]);
  }
  return [...failedPaths];
};

export const batchRetryFilepathsForTask = (
  tasks: Pick<AnalysisTaskQueueItem, "taskId" | "kind" | "status" | "payload">[],
  taskId: string,
  results: Pick<BatchResultItem, "index" | "filename" | "success" | "code" | "result_mode">[],
): string[] => {
  const task = tasks.find(
    (candidate) =>
      candidate.taskId === taskId &&
      candidate.kind === "batch" &&
      candidate.status === "completed",
  );
  return task ? failedBatchFilepaths(task.payload.filepaths || [], results) : [];
};

export const batchRetryFilepathForItem = (
  tasks: Pick<AnalysisTaskQueueItem, "taskId" | "kind" | "status" | "payload">[],
  taskId: string,
  result: Pick<BatchResultItem, "index" | "filename" | "success" | "code" | "result_mode">,
): string => {
  const filepaths = batchRetryFilepathsForTask(tasks, taskId, [result]);
  return filepaths.length === 1 ? filepaths[0] : "";
};

export const selectBatchTaskCenterItems = <
  T extends Pick<AnalysisTaskQueueItem, "kind" | "status" | "createdAt">
>(tasks: T[], status: AnalysisTaskStatus | "all" = "all"): T[] =>
  tasks
    .filter(
      (task) => task.kind === "batch" && (status === "all" || task.status === status),
    )
    .slice()
    .sort((left, right) => {
      const leftTime = Date.parse(left.createdAt) || 0;
      const rightTime = Date.parse(right.createdAt) || 0;
      return rightTime - leftTime;
    });

export const completionNotificationKey = (
  task: Pick<AnalysisTaskQueueItem, "taskId" | "attemptCount">,
): string => {
  const attemptCount = Math.max(0, Math.floor(safeNumber(task.attemptCount)));
  return `${safeString(task.taskId)}:${attemptCount}`;
};

export const newlyCompletedTasks = <
  T extends Pick<AnalysisTaskQueueItem, "taskId" | "status" | "attemptCount">
>(previous: T[], current: T[], notifiedKeys: Iterable<string> = []): T[] => {
  const previousById = new Map(previous.map((task) => [task.taskId, task]));
  const notified = new Set(notifiedKeys);
  return current.filter((task) => {
    if (task.status !== "completed") return false;
    const prior = previousById.get(task.taskId);
    if (!prior || prior.status === "completed") return false;
    return !notified.has(completionNotificationKey(task));
  });
};

export const shouldSendBrowserCompletionNotification = (options: {
  enabled: boolean;
  visibilityState: string;
  permission: string;
}): boolean =>
  options.enabled &&
  options.visibilityState === "hidden" &&
  options.permission === "granted";
