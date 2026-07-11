import DOMPurify from "dompurify";
import { marked } from "marked";
import { motion } from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BackgroundBeams } from "@/components/ui/background-beams";
import { CanvasText } from "@/components/ui/canvas-text";
import { LayoutTextFlip } from "@/components/ui/layout-text-flip";
import { NoiseBackground } from "@/components/ui/noise-background";
import { cn } from "@/lib/utils";

import {
  ALIYUN_APIKEY_DOC_URL,
  ANALYZE_BUTTON_GRADIENT_COLORS,
  ANALYZE_BUTTON_LIGHT_GRADIENT_COLORS,
  DEFAULT_PROGRESS_BOARD,
  DEFAULT_UPLOAD_CHUNK_SIZE,
  EMPTY_STEPS,
  ERROR_GUIDE_DURATION_MS,
  ERROR_TOAST_DURATION_MS,
  FPS_MAX,
  FPS_MIN,
  FPS_STEP,
  HERO_ANIMATION_TOP_THRESHOLD,
  HERO_SUBTITLE_CANVAS_COLORS,
  HERO_TITLE_CANVAS_COLORS,
  HISTORY_CLIENT_ID_HEADER,
  HISTORY_CLIENT_ID_KEY,
  MAX_VISION_MAX,
  MAX_VISION_MIN,
  MOBILE_PERF_MEDIA_QUERY,
  MODEL_PRESETS,
  MODEL_PRESET_VALUES,
  NEW_STEP_DEFAULT_DESCRIPTION,
  NEW_STEP_DEFAULT_TIME,
  NEW_STEP_DEFAULT_TITLE,
  PROGRESS_POLL_INTERVAL_DESKTOP_MS,
  PROGRESS_POLL_INTERVAL_MOBILE_MS,
  REDUCED_MOTION_MEDIA_QUERY,
  SEGMENT_POLICY_CODE_GUIDES,
  SEGMENT_ZONE_LABELS,
  STAGE_LABELS,
  UPLOAD_RESUME_KEY_PREFIX,
  USER_SETTINGS_STORAGE_KEY_PREFIX,
  THEME_STORAGE_KEY,
  VALID_VIDEO_EXTENSIONS,
  WEB_SEARCH_ACTIVATION_URL,
  WEB_SEARCH_ERROR_HINTS,
  WHISPER_MODEL_VALUES,
} from "./constants/app";
import type {
  AnalysisTaskKind,
  AnalysisTaskListResponse,
  AnalysisTaskPayload,
  AnalysisTaskQueueItem,
  AnalysisTaskStatusResponse,
  ApiErrorPayload,
  BatchFileItem,
  BatchResultData,
  BatchResultItem,
  BatchSegmentPolicy,
  BlockedNotice,
  EffectiveOptions,
  FileStatus,
  HistoryItem,
  Mode,
  ModelPreset,
  NavigatorWithConnection,
  OutputTemplate,
  PersistedUserSettings,
  ProgressBoard,
  RiskResult,
  SegmentPolicy,
  SingleResultData,
  StepItem,
  SubtitleLine,
  SubtitleWorkbenchData,
} from "./types/api";
import { ApiRequestError } from "./lib/api-error";
import { buildUploadSourceKey, dedupeBatchUploadFiles } from "./lib/upload-dedupe";
import {
  TASK_LIFECYCLE_STORAGE_KEY,
  TASK_STATUS_LABELS,
  batchRetryFilepathForItem,
  batchRetryFilepathsForTask,
  cachedTaskResultForPresentation,
  classifyResultLoadFailure,
  completionNotificationKey,
  createTaskQueueItem,
  findReselectableUpload,
  markTaskUnavailable,
  mergeServerTaskQueue,
  mergeTaskStatus,
  newlyCompletedTasks,
  parseLifecycleState,
  pendingCompletedTasks,
  reconcileTaskFiles,
  resultLoadRetryDelayMs,
  runExclusiveTaskSubmission,
  runUploadCancellation,
  safeStorageGet,
  safeStorageRemove,
  safeStorageSet,
  serializeLifecycleState,
  shouldSendBrowserCompletionNotification,
  shouldPollTask,
  upsertTaskQueueItem,
} from "./lib/task-lifecycle";
import type { CachedTaskResult, ResultPresentationToken } from "./lib/task-lifecycle";
import {
  basename,
  buildModelConfigSignature,
  clampNumber,
  clone,
  createHistoryClientId,
  getOrCreateHistoryClientId,
  isValidVideo,
  normalizeModelBaseUrlForSignature,
  parseSourceUrls,
  safeString,
  shouldEnableMobilePerfMode,
} from "./lib/utils-app";
import {
  compactErrorDetail,
  extractErrorCode,
  extractModelNameFromNotFound,
  extractRequestId,
  formatBatchSegmentPolicyHint,
  formatContentPolicyViolationMessage,
  formatDegradeReason,
  formatErrorMessage,
  formatInlineErrorMessage,
  formatModelConnectionError,
  formatRiskHint,
  formatSegmentPolicyGuideByCode,
  formatSegmentPolicyHint,
  formatSegmentPolicyLine,
  getSegmentZoneLabel,
} from "./lib/format";
import {
  BrandStudioIcon,
  ClearIcon,
  CloseIcon,
  DocumentIcon,
  DownloadSingleIcon,
  DownloadZipIcon,
  EditIcon,
  EyeIcon,
  EyeOffIcon,
  FileVideoIcon,
  FolderPlusIcon,
  HistoryEmptyIllustration,
  HistoryIcon,
  MoonIcon,
  PlayIcon,
  RefreshIcon,
  SettingsIcon,
  StackIcon,
  StatusFailedIcon,
  StatusSuccessIcon,
  StepsIcon,
  SunIcon,
  TrashIcon,
  UploadIcon,
} from "./components/icons";
import { MarkdownPreview } from "./components/MarkdownPreview";
import { ReadonlyStepsList } from "./components/ReadonlyStepsList";
import { StepsPanel } from "./components/StepsPanel";
import { DocumentPanel } from "./components/DocumentPanel";
import { SubtitlePanel } from "./components/SubtitlePanel";
import { BatchResultPanel } from "./components/BatchResultPanel";
import { BatchTaskCenter } from "./components/BatchTaskCenter";
import { VirtualizedHistoryList } from "./components/VirtualizedHistoryList";

void BrandStudioIcon;
void ClearIcon;
void CloseIcon;
void DocumentIcon;
void DownloadSingleIcon;
void DownloadZipIcon;
void EditIcon;
void EyeIcon;
void EyeOffIcon;
void FileVideoIcon;
void FolderPlusIcon;
void HistoryEmptyIllustration;
void HistoryIcon;
void PlayIcon;
void RefreshIcon;
void SettingsIcon;
void StackIcon;
void StatusFailedIcon;
void StatusSuccessIcon;
void StepsIcon;
void TrashIcon;
void UploadIcon;
void ALIYUN_APIKEY_DOC_URL;
void ANALYZE_BUTTON_GRADIENT_COLORS;
void DEFAULT_PROGRESS_BOARD;
void DEFAULT_UPLOAD_CHUNK_SIZE;
void EMPTY_STEPS;
void ERROR_GUIDE_DURATION_MS;
void ERROR_TOAST_DURATION_MS;
void FPS_MAX;
void FPS_MIN;
void FPS_STEP;
void HERO_ANIMATION_TOP_THRESHOLD;
void HERO_SUBTITLE_CANVAS_COLORS;
void HERO_TITLE_CANVAS_COLORS;
void HISTORY_CLIENT_ID_HEADER;
void HISTORY_CLIENT_ID_KEY;
void MAX_VISION_MAX;
void MAX_VISION_MIN;
void MOBILE_PERF_MEDIA_QUERY;
void MODEL_PRESETS;
void MODEL_PRESET_VALUES;
void NEW_STEP_DEFAULT_DESCRIPTION;
void NEW_STEP_DEFAULT_TIME;
void NEW_STEP_DEFAULT_TITLE;
void PROGRESS_POLL_INTERVAL_DESKTOP_MS;
void PROGRESS_POLL_INTERVAL_MOBILE_MS;
void REDUCED_MOTION_MEDIA_QUERY;
void SEGMENT_POLICY_CODE_GUIDES;
void SEGMENT_ZONE_LABELS;
void STAGE_LABELS;
void UPLOAD_RESUME_KEY_PREFIX;
void USER_SETTINGS_STORAGE_KEY_PREFIX;
void VALID_VIDEO_EXTENSIONS;
void WEB_SEARCH_ACTIVATION_URL;
void WEB_SEARCH_ERROR_HINTS;
void WHISPER_MODEL_VALUES;
void basename;
void buildModelConfigSignature;
void clampNumber;
void clone;
void createHistoryClientId;
void getOrCreateHistoryClientId;
void isValidVideo;
void normalizeModelBaseUrlForSignature;
void parseSourceUrls;
void safeString;
void shouldEnableMobilePerfMode;
void compactErrorDetail;
void extractErrorCode;
void extractModelNameFromNotFound;
void extractRequestId;
void formatBatchSegmentPolicyHint;
void formatContentPolicyViolationMessage;
void formatDegradeReason;
void formatErrorMessage;
void formatInlineErrorMessage;
void formatModelConnectionError;
void formatRiskHint;
void formatSegmentPolicyGuideByCode;
void formatSegmentPolicyHint;
void formatSegmentPolicyLine;
void getSegmentZoneLabel;
void ApiRequestError;
void ReadonlyStepsList;
void VirtualizedHistoryList;
void MarkdownPreview;

export type {
  AnalysisTaskKind,
  AnalysisTaskPayload,
  AnalysisTaskQueueItem,
  AnalysisTaskStatusResponse,
  ApiErrorPayload,
  BatchFileItem,
  BatchResultData,
  BatchResultItem,
  BatchSegmentPolicy,
  BlockedNotice,
  EffectiveOptions,
  FileStatus,
  HistoryItem,
  Mode,
  ModelPreset,
  NavigatorWithConnection,
  OutputTemplate,
  PersistedUserSettings,
  ProgressBoard,
  RiskResult,
  SegmentPolicy,
  SingleResultData,
  StepItem,
  SubtitleLine,
  SubtitleWorkbenchData,
};

type AnalysisTaskSingleResult = SingleResultData & {
  filename?: string;
  filepath?: string;
  download_title?: string;
};
type AnalysisTaskCachedResult = CachedTaskResult<AnalysisTaskSingleResult, BatchResultData>;

const BROWSER_COMPLETION_NOTIFICATION_KEY = "video-analysis-browser-completion-notifications-v1";

export default function App() {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    if (typeof window === "undefined") return "dark";
    try {
      const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch {
      // ignore storage read failure
    }
    return "dark";
  });
  const [, setWebSearch] = useState(false);
  const [summaryOnly] = useState(false);
  const [outputTemplate, setOutputTemplate] = useState<OutputTemplate>("operation_guide");
  const [sourceUrl, setSourceUrl] = useState("");
  const [importingUrl, setImportingUrl] = useState(false);

  const [savingSteps, setSavingSteps] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [deletingHistoryId, setDeletingHistoryId] = useState("");
  const [pendingDeleteHistory, setPendingDeleteHistory] = useState<HistoryItem | null>(null);
  const [showClearHistoryConfirm, setShowClearHistoryConfirm] = useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);

  const [batchFiles, setBatchFiles] = useState<BatchFileItem[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return parseLifecycleState(window.localStorage.getItem(TASK_LIFECYCLE_STORAGE_KEY)).uploads;
    } catch {
      return [];
    }
  });
  const [taskQueue, setTaskQueue] = useState<AnalysisTaskQueueItem[]>(() => {
    if (typeof window === "undefined") return [];
    try {
      return parseLifecycleState(window.localStorage.getItem(TASK_LIFECYCLE_STORAGE_KEY)).tasks;
    } catch {
      return [];
    }
  });
  const [taskActionId, setTaskActionId] = useState("");
  const [submittingTask, setSubmittingTask] = useState(false);
  const [browserNotificationsEnabled, setBrowserNotificationsEnabled] = useState(() => {
    if (typeof window === "undefined" || typeof Notification === "undefined") return false;
    return (
      Notification.permission === "granted" &&
      safeStorageGet(() => window.localStorage, BROWSER_COMPLETION_NOTIFICATION_KEY) === "enabled"
    );
  });
  const [browserNotificationPermission, setBrowserNotificationPermission] = useState<
    NotificationPermission | "unsupported"
  >(() => (typeof Notification === "undefined" ? "unsupported" : Notification.permission));
  const isAnalyzing = submittingTask || Boolean(taskActionId) || taskQueue.some(shouldPollTask);
  const [resultData, setResultData] = useState<SingleResultData | null>(null);
  const [batchResultData, setBatchResultData] = useState<BatchResultData | null>(null);
  const [batchResultTaskId, setBatchResultTaskId] = useState("");
  const [savedBatchResult, setSavedBatchResult] = useState<BatchResultData | null>(null);
  const [savedBatchResultTaskId, setSavedBatchResultTaskId] = useState("");
  const [resultRetryTick, setResultRetryTick] = useState(0);
  const [view, setView] = useState<"upload" | "result">("upload");
  const [activeResultTab, setActiveResultTab] = useState<"steps" | "document" | "subtitle">("steps");
  const [activeResultSection, setActiveResultSection] = useState<string>("");
  const [showBackToTop, setShowBackToTop] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [subtitleWorkbench, setSubtitleWorkbench] = useState<SubtitleWorkbenchData | null>(null);
  const [subtitleLoading, setSubtitleLoading] = useState(false);
  const [subtitleRefreshing, setSubtitleRefreshing] = useState(false);
  const [subtitleKeyword, setSubtitleKeyword] = useState("");
  const [subtitleLoadError, setSubtitleLoadError] = useState("");

  const [isEditMode, setIsEditMode] = useState(false);
  const [editedSteps, setEditedSteps] = useState<StepItem[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const [batchDragOver, setBatchDragOver] = useState(false);
  const [progressVisible, setProgressVisible] = useState(false);
  const [progressTitle, setProgressTitle] = useState("处理中...");
  const [progressText, setProgressText] = useState("请稍候...");
  const [progressBoard, setProgressBoard] = useState<ProgressBoard>(DEFAULT_PROGRESS_BOARD);
  const [errorMessage, setErrorMessage] = useState("");
  const [showErrorToast, setShowErrorToast] = useState(false);
  const [successMessage, setSuccessMessage] = useState("");
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [heroAnimationActive, setHeroAnimationActive] = useState(true);
  const [mobilePerfMode, setMobilePerfMode] = useState<boolean>(() => shouldEnableMobilePerfMode());

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const sourceUrlInputRef = useRef<HTMLInputElement | null>(null);
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const batchFilesRef = useRef<BatchFileItem[]>([]);
  const taskQueueRef = useRef<AnalysisTaskQueueItem[]>([]);
  const uploadRuntimeRef = useRef(
    new Map<string, { controller: AbortController; resumeKey: string; uploadId: string }>(),
  );
  const loadingTaskResultsRef = useRef(new Set<string>());
  const loadedTaskResultsRef = useRef(new Set<string>());
  const taskResultCacheRef = useRef(new Map<string, AnalysisTaskCachedResult>());
  const resultPresentationRef = useRef<{
    taskId: string;
    revision: number;
    mode: "auto" | "user";
  }>({ taskId: "", revision: 0, mode: "auto" });
  const resultRetryAttemptsRef = useRef(new Map<string, number>());
  const resultRetryTimersRef = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const resultRetryNotifiedRef = useRef(new Set<string>());
  const taskSubmissionGateRef = useRef({ current: false });
  const completionNotificationTasksRef = useRef(taskQueue);
  const completionNotificationKeysRef = useRef(new Set<string>());
  const pendingFileSeqRef = useRef(0);
  const subtitleVideoRef = useRef<HTMLVideoElement | null>(null);
  const progressPollIntervalMs = mobilePerfMode
    ? PROGRESS_POLL_INTERVAL_MOBILE_MS
    : PROGRESS_POLL_INTERVAL_DESKTOP_MS;
  const uiScrollBehavior: ScrollBehavior = mobilePerfMode ? "auto" : "smooth";

  useEffect(() => {
    batchFilesRef.current = batchFiles;
  }, [batchFiles]);

  useEffect(() => {
    taskQueueRef.current = taskQueue;
  }, [taskQueue]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    safeStorageSet(
      () => window.localStorage,
      TASK_LIFECYCLE_STORAGE_KEY,
      serializeLifecycleState({
        tasks: taskQueue.filter(shouldPollTask),
        uploads: batchFiles,
      }),
    );
  }, [batchFiles, taskQueue]);

  const requestTaskPresentation = useCallback((taskId: string) => {
    const next = {
      taskId,
      revision: resultPresentationRef.current.revision + 1,
      mode: "auto" as const,
    };
    resultPresentationRef.current = next;
    return { taskId: next.taskId, revision: next.revision };
  }, []);

  const invalidateTaskPresentation = useCallback(() => {
    resultPresentationRef.current = {
      taskId: "",
      revision: resultPresentationRef.current.revision + 1,
      mode: "user",
    };
  }, []);

  const presentationTokenForTask = useCallback((taskId: string) => {
    const current = resultPresentationRef.current;
    if (current.mode !== "auto" || current.taskId !== taskId) return undefined;
    return { taskId, revision: current.revision };
  }, []);

  const nextPendingFileId = useCallback((prefix: string) => {
    pendingFileSeqRef.current += 1;
    return `${prefix}-${Date.now()}-${pendingFileSeqRef.current}`;
  }, []);

  const replaceBatchFileByClientId = useCallback((clientId: string, nextItem: BatchFileItem) => {
    setBatchFiles((prev) => prev.map((item) => (item.clientId === clientId ? nextItem : item)));
  }, []);

  const guessUrlVideoName = useCallback((url: string) => {
    try {
      const parsed = new URL(url);
      const guessed = basename(decodeURIComponent(parsed.pathname || ""));
      return guessed && /\.[A-Za-z0-9]{2,5}$/.test(guessed) ? guessed : "url_video.mp4";
    } catch {
      return "url_video.mp4";
    }
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, theme);
    } catch {
      // ignore storage write failure
    }
  }, [theme]);

  const toggleTheme = useCallback(() => {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const coarseMobileQuery = window.matchMedia(MOBILE_PERF_MEDIA_QUERY);
    const reducedMotionQuery = window.matchMedia(REDUCED_MOTION_MEDIA_QUERY);
    const connection = (navigator as NavigatorWithConnection).connection;
    const updateMode = () => {
      const next = coarseMobileQuery.matches || reducedMotionQuery.matches || Boolean(connection?.saveData);
      setMobilePerfMode((prev) => (prev === next ? prev : next));
    };
    const addMediaListener = (media: MediaQueryList, listener: () => void) => {
      if (typeof media.addEventListener === "function") {
        media.addEventListener("change", listener);
        return;
      }
      media.addListener(listener);
    };
    const removeMediaListener = (media: MediaQueryList, listener: () => void) => {
      if (typeof media.removeEventListener === "function") {
        media.removeEventListener("change", listener);
        return;
      }
      media.removeListener(listener);
    };

    updateMode();
    addMediaListener(coarseMobileQuery, updateMode);
    addMediaListener(reducedMotionQuery, updateMode);
    connection?.addEventListener?.("change", updateMode);

    return () => {
      removeMediaListener(coarseMobileQuery, updateMode);
      removeMediaListener(reducedMotionQuery, updateMode);
      connection?.removeEventListener?.("change", updateMode);
    };
  }, []);

  useEffect(() => {
    const uploadRuntimes = uploadRuntimeRef.current;
    const resultRetryTimers = resultRetryTimersRef.current;
    return () => {
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      uploadRuntimes.forEach(({ controller }) => controller.abort());
      uploadRuntimes.clear();
      resultRetryTimers.forEach((timer) => clearTimeout(timer));
      resultRetryTimers.clear();
    };
  }, []);

  useEffect(() => {
    if ((!historyDrawerOpen && !showClearHistoryConfirm && !pendingDeleteHistory) || typeof document === "undefined") return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (showClearHistoryConfirm) {
          if (!clearingHistory) setShowClearHistoryConfirm(false);
          return;
        }
        if (pendingDeleteHistory) {
          if (!deletingHistoryId) setPendingDeleteHistory(null);
          return;
        }
        setHistoryDrawerOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [
    clearingHistory,
    deletingHistoryId,
    historyDrawerOpen,
    pendingDeleteHistory,
    showClearHistoryConfirm,
  ]);

  useEffect(() => {
    if (!historyDrawerOpen) {
      if (showClearHistoryConfirm) setShowClearHistoryConfirm(false);
      if (pendingDeleteHistory) setPendingDeleteHistory(null);
    }
  }, [historyDrawerOpen, pendingDeleteHistory, showClearHistoryConfirm]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (mobilePerfMode) {
      setHeroAnimationActive(false);
      return;
    }

    let rafId = 0;
    const syncHeroAnimationState = () => {
      const currentScrollTop = window.scrollY || document.documentElement.scrollTop || 0;
      const nextActive = currentScrollTop <= HERO_ANIMATION_TOP_THRESHOLD;
      setHeroAnimationActive((prev) => (prev === nextActive ? prev : nextActive));
    };

    const handleScroll = () => {
      if (rafId) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = 0;
        syncHeroAnimationState();
      });
    };

    syncHeroAnimationState();
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      if (rafId) window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", handleScroll);
    };
  }, [mobilePerfMode]);

  const withHistoryClientHeader = useCallback((options: RequestInit = {}) => {
    const headers = new Headers(options.headers || {});
    const clientId = getOrCreateHistoryClientId();
    if (clientId && !headers.has(HISTORY_CLIENT_ID_HEADER)) {
      headers.set(HISTORY_CLIENT_ID_HEADER, clientId);
    }
    return { ...options, headers };
  }, []);

  const fetchJson = useCallback(async <T,>(url: string, options: RequestInit = {}) => {
    const response = await fetch(url, withHistoryClientHeader(options));
    const data = (await response.json().catch(() => ({}))) as ApiErrorPayload & T;
    if (!response.ok || data.error) {
      const base = String(data.error || `请求失败 (${response.status})`);
      const riskHint = formatRiskHint(data.risk);
      const segmentHint = formatSegmentPolicyHint(data.segment_policy);
      const batchSegmentHint = formatBatchSegmentPolicyHint(data.batch_segment_policy);
      const codeText = data.code ? `code=${data.code}` : "";
      const merged = [base, codeText, segmentHint, batchSegmentHint, riskHint].filter(Boolean).join(" | ");
      throw new ApiRequestError(merged, response.status, data);
    }
    return data;
  }, [withHistoryClientHeader]);

  useEffect(() => {
    let stopped = false;
    const hydrateTaskHistory = async () => {
      try {
        const data = await fetchJson<AnalysisTaskListResponse>("/analysis_tasks");
        if (stopped) return;
        setTaskQueue((current) => mergeServerTaskQueue(current, data.tasks || []));
      } catch {
        // The local lifecycle snapshot remains available while the server is offline.
      }
    };
    void hydrateTaskHistory();
    return () => {
      stopped = true;
    };
  }, [fetchJson]);

  const fetchBlob = useCallback(async (url: string, options: RequestInit = {}) => {
    const response = await fetch(url, withHistoryClientHeader(options));
    if (!response.ok) {
      throw new Error(`下载失败 (${response.status})`);
    }
    return response.blob();
  }, [withHistoryClientHeader]);

  const showError = useCallback((message: string) => {
    const rawMessage = String(message || "");
    setShowSuccessToast(false);
    if (successTimerRef.current) clearTimeout(successTimerRef.current);
    setErrorMessage(formatErrorMessage(rawMessage));
    setShowErrorToast(true);
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    errorTimerRef.current = setTimeout(() => setShowErrorToast(false), ERROR_TOAST_DURATION_MS);
  }, []);

  const showSuccess = useCallback((message: string) => {
    const rawMessage = String(message || "").trim() || "操作成功";
    setShowErrorToast(false);
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    setSuccessMessage(rawMessage);
    setShowSuccessToast(true);
    if (successTimerRef.current) clearTimeout(successTimerRef.current);
    successTimerRef.current = setTimeout(() => setShowSuccessToast(false), 3600);
  }, []);

  const toggleBrowserCompletionNotifications = useCallback(async () => {
    if (browserNotificationsEnabled) {
      setBrowserNotificationsEnabled(false);
      if (typeof window !== "undefined") {
        safeStorageRemove(() => window.localStorage, BROWSER_COMPLETION_NOTIFICATION_KEY);
      }
      showSuccess("浏览器完成通知已关闭，站内通知仍会保留。");
      return;
    }
    if (typeof Notification === "undefined") {
      setBrowserNotificationPermission("unsupported");
      showError("当前浏览器不支持系统通知。");
      return;
    }
    const permission =
      Notification.permission === "default"
        ? await Notification.requestPermission()
        : Notification.permission;
    setBrowserNotificationPermission(permission);
    if (permission !== "granted") {
      setBrowserNotificationsEnabled(false);
      if (typeof window !== "undefined") {
        safeStorageRemove(() => window.localStorage, BROWSER_COMPLETION_NOTIFICATION_KEY);
      }
      showError("浏览器通知未获授权，站内完成通知不受影响。");
      return;
    }
    setBrowserNotificationsEnabled(true);
    if (typeof window !== "undefined") {
      safeStorageSet(
        () => window.localStorage,
        BROWSER_COMPLETION_NOTIFICATION_KEY,
        "enabled",
      );
    }
    showSuccess("浏览器完成通知已开启。");
  }, [browserNotificationsEnabled, showError, showSuccess]);

  useEffect(() => {
    const completed = newlyCompletedTasks(
      completionNotificationTasksRef.current,
      taskQueue,
      completionNotificationKeysRef.current,
    );
    completionNotificationTasksRef.current = taskQueue;
    if (completed.length === 0) return;

    completed.forEach((task) => {
      completionNotificationKeysRef.current.add(completionNotificationKey(task));
    });
    showSuccess(
      completed.length === 1
        ? `${completed[0].label} 已完成`
        : `${completed.length} 个分析任务已完成`,
    );

    if (
      typeof document === "undefined" ||
      typeof Notification === "undefined" ||
      !shouldSendBrowserCompletionNotification({
        enabled: browserNotificationsEnabled,
        visibilityState: document.visibilityState,
        permission: Notification.permission,
      })
    ) {
      return;
    }
    completed.forEach((task) => {
      new Notification("视频分析完成", { body: task.label, tag: completionNotificationKey(task) });
    });
  }, [browserNotificationsEnabled, showSuccess, taskQueue]);

  const verifyModelConnectionForUpload = useCallback(async () => {
    // 模型连通校验已取消：模型配置（API Key / 名称 / Base URL）统一由后端 .env 托管。
    return true;
  }, []);

  const setProgressTextIfChanged = useCallback((nextText: string) => {
    const normalized = String(nextText || "");
    setProgressText((prev) => (prev === normalized ? prev : normalized));
  }, []);

  const showProgress = useCallback((title: string, text: string) => {
    setProgressTitle(title);
    setProgressTextIfChanged(text);
    setProgressBoard(DEFAULT_PROGRESS_BOARD);
    setProgressVisible(true);
  }, [setProgressTextIfChanged]);

  const hideProgress = useCallback(() => {
    setProgressVisible(false);
    setProgressBoard(DEFAULT_PROGRESS_BOARD);
  }, []);

  const getAnalyzableBatchFiles = useCallback(
    () => batchFilesRef.current.filter((item) => Boolean(String(item.filepath || "").trim())),
    [],
  );
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const data = await fetchJson<{ history?: HistoryItem[] }>("/history");
      setHistory(Array.isArray(data.history) ? data.history : []);
    } catch (error) {
      showError(`加载历史失败: ${String((error as Error).message || error)}`);
    } finally {
      setLoadingHistory(false);
    }
  }, [fetchJson, showError]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const uploadSingleFileWithResume = useCallback(
    async (
      file: File,
      fileIndex: number,
      totalFiles: number,
      options: {
        signal: AbortSignal;
        onUploadReady: (uploadId: string, resumeKey: string) => void;
        onSafetyCheckStart?: (currentFile: File, currentIndex: number, total: number) => void;
      },
    ) => {
      const resumeKey = `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`;
      const storedUploadId = safeStorageGet(() => window.localStorage, resumeKey, "");
      const initData = await fetchJson<{
        upload_id: string;
        chunk_size?: number;
        total_chunks?: number;
        received_chunks?: number[];
      }>("/upload_chunk_init", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          total_size: file.size,
          chunk_size: DEFAULT_UPLOAD_CHUNK_SIZE,
          upload_id: storedUploadId,
          file_key: resumeKey,
        }),
        signal: options.signal,
      });
      const uploadId = String(initData.upload_id || "");
      if (!uploadId) throw new Error("初始化上传失败");
      safeStorageSet(() => window.localStorage, resumeKey, uploadId);
      options.onUploadReady(uploadId, resumeKey);

      const chunkSize = Number(initData.chunk_size) || DEFAULT_UPLOAD_CHUNK_SIZE;
      const totalChunks = Number(initData.total_chunks) || 1;
      const receivedSet = new Set((initData.received_chunks || []).map((item) => Number(item)));

      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
        if (receivedSet.has(chunkIndex)) continue;
        const start = chunkIndex * chunkSize;
        const end = Math.min(file.size, start + chunkSize);
        const formData = new FormData();
        formData.append("upload_id", uploadId);
        formData.append("chunk_index", String(chunkIndex));
        formData.append("chunk", file.slice(start, end));
        await fetchJson("/upload_chunk", { method: "POST", body: formData, signal: options.signal });
      }

      options.onSafetyCheckStart?.(file, fileIndex, totalFiles);
      const finalized = await fetchJson<{ filename: string; filepath: string }>("/upload_chunk_finalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId }),
        signal: options.signal,
      });
      safeStorageRemove(() => window.localStorage, resumeKey);
      return finalized;
    },
    [fetchJson],
  );

  const uploadBatchFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const selectedFiles = Array.from(fileList || []).filter((file) => isValidVideo(file.name));
      const existingFiles = batchFilesRef.current;
      const claimedResumableIds = new Set<string>();
      const resumableEntries: Array<{ file: File; placeholder: BatchFileItem }> = [];
      const freshCandidates: File[] = [];

      for (const file of selectedFiles) {
        const sourceKey = buildUploadSourceKey(file);
        const resumable = findReselectableUpload(
          existingFiles.filter((item) => !item.clientId || !claimedResumableIds.has(item.clientId)),
          sourceKey,
        );
        if (resumable?.clientId) {
          claimedResumableIds.add(resumable.clientId);
          resumableEntries.push({ file, placeholder: resumable });
        } else {
          freshCandidates.push(file);
        }
      }

      const existingSourceKeys = existingFiles
        .map((item) => item.sourceKey || "")
        .filter(Boolean);
      const { files: freshFiles, duplicateCount } = dedupeBatchUploadFiles(freshCandidates, existingSourceKeys);
      if (duplicateCount > 0) {
        showError(`检测到 ${duplicateCount} 个重复视频源，已自动跳过去重，请勿重复上传。`);
      }
      if (freshFiles.length === 0 && resumableEntries.length === 0 && duplicateCount > 0) {
        return;
      }
      if (freshFiles.length === 0 && resumableEntries.length === 0) {
        showError("没有可用的视频文件");
        return;
      }

      const readyForUpload = await verifyModelConnectionForUpload();
      if (!readyForUpload) return;

      const freshPlaceholders = freshFiles.map((file) => ({
        filename: file.name,
        sourceKey: buildUploadSourceKey(file),
        resumeKey: `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`,
        size: file.size,
        lastModified: file.lastModified,
        filepath: "",
        status: "uploading" as FileStatus,
        error: "等待上传...",
        clientId: nextPendingFileId("upload"),
        needsReselect: false,
      }));
      const resumedPlaceholders = resumableEntries.map(({ file, placeholder }) => ({
        ...placeholder,
        filename: file.name,
        sourceKey: buildUploadSourceKey(file),
        resumeKey: `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`,
        size: file.size,
        lastModified: file.lastModified,
        filepath: "",
        status: "uploading" as FileStatus,
        error: "等待续传...",
        needsReselect: false,
      }));
      const entries = [
        ...resumableEntries.map(({ file }, index) => ({ file, placeholder: resumedPlaceholders[index] })),
        ...freshFiles.map((file, index) => ({ file, placeholder: freshPlaceholders[index] })),
      ];
      const entryRuntimes = new Map<string, { controller: AbortController; resumeKey: string }>();
      for (const { file, placeholder } of entries) {
        const clientId = placeholder.clientId || "";
        const resumeKey =
          placeholder.resumeKey ||
          `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`;
        const controller = new AbortController();
        entryRuntimes.set(clientId, { controller, resumeKey });
        uploadRuntimeRef.current.set(clientId, {
          controller,
          resumeKey,
          uploadId: safeStorageGet(() => window.localStorage, resumeKey, ""),
        });
      }
      const resumedById = new Map(
        resumedPlaceholders.map((placeholder) => [placeholder.clientId || "", placeholder]),
      );
      setBatchFiles((prev) => [
        ...prev.map((item) => resumedById.get(item.clientId || "") || item),
        ...freshPlaceholders,
      ]);
      try {
        let uploadedFailed = 0;
        for (let i = 0; i < entries.length; i += 1) {
          const { file: currentFile, placeholder } = entries[i];
          const clientId = placeholder.clientId || "";
          const resumeKey =
            placeholder.resumeKey ||
            `${UPLOAD_RESUME_KEY_PREFIX}:${currentFile.name}:${currentFile.size}:${currentFile.lastModified}`;
          const controller = entryRuntimes.get(clientId)?.controller || new AbortController();
          if (controller.signal.aborted) continue;
          try {
            replaceBatchFileByClientId(clientId, {
              ...placeholder,
              status: "uploading",
              error: `正在上传（${i + 1}/${entries.length}）...`,
              needsReselect: false,
            });
            const item = await uploadSingleFileWithResume(
              currentFile,
              i + 1,
              entries.length,
              {
                signal: controller.signal,
                onUploadReady: (uploadId, nextResumeKey) => {
                  const runtime = uploadRuntimeRef.current.get(clientId);
                  if (runtime) {
                    runtime.uploadId = uploadId;
                    runtime.resumeKey = nextResumeKey;
                  }
                },
                onSafetyCheckStart: (processingFile, currentIndex, total) => {
                  replaceBatchFileByClientId(clientId, {
                    ...placeholder,
                    filename: processingFile.name,
                    status: "uploading",
                    error: `正在保存视频（${currentIndex}/${total}）...`,
                    needsReselect: false,
                  });
                },
              },
            );
            replaceBatchFileByClientId(clientId, {
              filename: item.filename,
              filepath: item.filepath,
              status: "pending",
              error: "",
              clientId,
              sourceKey: placeholder.sourceKey,
              resumeKey,
              size: currentFile.size,
              lastModified: currentFile.lastModified,
              needsReselect: false,
            });
          } catch (error) {
            if (controller.signal.aborted) continue;
            const apiError = error instanceof ApiRequestError ? error : null;
            let message = String((error as Error).message || error || "上传失败");
            if (apiError?.payload?.code === "content_policy_violation") {
              message = formatContentPolicyViolationMessage();
            } else if (apiError?.payload?.error) {
              message = String(apiError.payload.error);
            }
            const segmentHint = formatSegmentPolicyHint(apiError?.payload?.segment_policy);
            if (segmentHint) message = [message, segmentHint].filter(Boolean).join(" | ");
            replaceBatchFileByClientId(clientId, {
              filename: currentFile.name,
              filepath: "",
              status: "failed",
              error: `${formatInlineErrorMessage(message)} 重新选择同一文件可继续上传。`,
              clientId,
              sourceKey: placeholder.sourceKey,
              resumeKey,
              size: currentFile.size,
              lastModified: currentFile.lastModified,
              needsReselect: true,
            });
            uploadedFailed += 1;
          } finally {
            const runtime = uploadRuntimeRef.current.get(clientId);
            if (runtime?.controller === controller) uploadRuntimeRef.current.delete(clientId);
          }
        }
        if (uploadedFailed > 0) {
          showError(`已跳过 ${uploadedFailed} 个上传失败视频，可继续分析其余视频。`);
        }
      } catch (error) {
        showError(`上传失败: ${String((error as Error).message || error)}`);
      }
    },
    [
      nextPendingFileId,
      replaceBatchFileByClientId,
      showError,
      uploadSingleFileWithResume,
      verifyModelConnectionForUpload,
    ],
  );

  const cancelFileUpload = useCallback(
    async (item: BatchFileItem) => {
      const clientId = item.clientId || "";
      if (!clientId) return;
      const runtime = uploadRuntimeRef.current.get(clientId);
      const resumeKey =
        runtime?.resumeKey ||
        item.resumeKey ||
        `${UPLOAD_RESUME_KEY_PREFIX}:${item.filename}:${item.size || 0}:${item.lastModified || 0}`;
      const uploadId = runtime?.uploadId || safeStorageGet(() => window.localStorage, resumeKey, "");
      const outcome = await runUploadCancellation({
        uploadId,
        abort: () => runtime?.controller.abort(),
        cancel: async (targetUploadId) => {
          await fetchJson("/upload_chunk_cancel", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ upload_id: targetUploadId }),
          });
        },
        clearResume: () => {
          safeStorageRemove(() => window.localStorage, resumeKey);
        },
      });
      uploadRuntimeRef.current.delete(clientId);
      if (!outcome.confirmed) {
        const reason = String((outcome.error as Error)?.message || outcome.error || "服务端未确认取消");
        showError(`取消上传未确认: ${reason}`);
        replaceBatchFileByClientId(clientId, {
          ...item,
          filepath: "",
          status: "failed",
          error: "服务端未确认取消；断点已保留，请稍后重新选择同一文件恢复状态。",
          resumeKey,
          needsReselect: true,
        });
        return;
      }
      replaceBatchFileByClientId(clientId, {
        ...item,
        filepath: "",
        status: "cancelled",
        error: "上传已取消；如需重新上传，请重新选择同一文件。",
        resumeKey,
        needsReselect: true,
      });
    },
    [fetchJson, replaceBatchFileByClientId, showError],
  );
  const updateFilesForTask = useCallback((task: AnalysisTaskQueueItem) => {
    setBatchFiles((prev) => reconcileTaskFiles(prev, task));
  }, []);

  const submitAnalysisTask = useCallback(
    async (
      kind: AnalysisTaskKind,
      payload: AnalysisTaskPayload,
      label: string,
      clientId?: string,
    ) =>
      runExclusiveTaskSubmission(taskSubmissionGateRef.current, async () => {
        setSubmittingTask(true);
        const presentationIntent = requestTaskPresentation("");
        try {
          const status = await fetchJson<AnalysisTaskStatusResponse>("/analysis_tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kind, payload }),
          });
          const task = createTaskQueueItem(status, { payload, label, clientId });
          if (
            resultPresentationRef.current.mode === "auto" &&
            resultPresentationRef.current.revision === presentationIntent.revision
          ) {
            requestTaskPresentation(task.taskId);
          }
          setSavedBatchResult(null);
          setSavedBatchResultTaskId("");
          setTaskQueue((prev) => upsertTaskQueueItem(prev, task));
          setView("upload");
          updateFilesForTask(task);
          return task;
        } finally {
          setSubmittingTask(false);
        }
      }),
    [
      fetchJson,
      requestTaskPresentation,
      updateFilesForTask,
    ],
  );

  const presentAnalysisTaskResult = useCallback(
    (presentationToken: ResultPresentationToken | undefined) => {
      const cached = cachedTaskResultForPresentation(
        taskResultCacheRef.current,
        presentationToken,
        resultPresentationRef.current,
      );
      if (!cached) return false;

      if (cached.kind === "batch") {
        setBatchResultData(cached.data);
        setBatchResultTaskId(cached.taskId);
        setResultData(null);
      } else {
        setResultData(cached.data);
        setBatchResultData(null);
        setBatchResultTaskId("");
        if (cached.data.fallback_used) {
          showSuccess(
            String(cached.data.analysis_note || "未识别到标准步骤，已自动生成候选内容。"),
          );
        }
      }
      setSavedBatchResult(null);
      setSavedBatchResultTaskId("");
      setIsEditMode(false);
      setEditedSteps([]);
      setActiveResultTab("steps");
      setView("result");
      if (typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          resultsRef.current?.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
        });
      }
      return true;
    },
    [showSuccess, uiScrollBehavior],
  );

  const loadAnalysisTaskResult = useCallback(
    async (
      task: AnalysisTaskQueueItem,
      presentationToken?: ResultPresentationToken,
    ) => {
      const latestPresentationToken = () =>
        presentationTokenForTask(task.taskId) || presentationToken;
      if (taskResultCacheRef.current.has(task.taskId)) {
        presentAnalysisTaskResult(latestPresentationToken());
        return;
      }
      if (
        loadedTaskResultsRef.current.has(task.taskId) ||
        loadingTaskResultsRef.current.has(task.taskId)
      ) {
        return;
      }
      loadingTaskResultsRef.current.add(task.taskId);
      try {
        let cachedResult: AnalysisTaskCachedResult;
        if (task.kind === "batch") {
          const data = await fetchJson<BatchResultData>(`/analysis_tasks/${encodeURIComponent(task.taskId)}/result`);
          const filepaths = task.payload.filepaths || [];
          const resultsByIndex = new Map(
            (data.results || [])
              .filter((result) => Number.isInteger(Number(result.index)) && Number(result.index) >= 1)
              .map((result) => [Number(result.index), result]),
          );
          setBatchFiles((prev) =>
            prev.map((item) => {
              const resultIndex = filepaths.indexOf(item.filepath);
              if (resultIndex < 0) return item;
              const indexedResult = resultsByIndex.get(resultIndex + 1);
              const filenameMatches = indexedResult
                ? []
                : (data.results || []).filter(
                    (result) => String(result.filename || "") === basename(item.filepath),
                  );
              const result = indexedResult || (filenameMatches.length === 1 ? filenameMatches[0] : undefined);
              if (!result) {
                return {
                  ...item,
                  status: "failed" as FileStatus,
                  error: "任务已完成，但未返回该文件的分析结果。",
                };
              }
              const base = String(result?.error || "");
              const riskHint = formatRiskHint(result?.risk);
              const codeText = result?.code ? `code=${result.code}` : "";
              return {
                ...item,
                status: result?.success ? ("success" as FileStatus) : ("failed" as FileStatus),
                error: [base, codeText, riskHint].filter(Boolean).join(" | "),
                };
              }),
            );
          cachedResult = { taskId: task.taskId, kind: "batch", data };
        } else {
          const data = await fetchJson<AnalysisTaskSingleResult>(
            `/analysis_tasks/${encodeURIComponent(task.taskId)}/result`,
          );
          if (task.kind === "single") {
            const filepath = String(task.payload.filepath || "");
            setBatchFiles((prev) =>
              prev.map((item) =>
                item.filepath === filepath ? { ...item, status: "success", error: "" } : item,
              ),
            );
          } else {
            const filepath = String(data.filepath || "").trim();
            const filename =
              String(data.download_title || data.filename || "").trim() ||
              basename(filepath) ||
              task.label;
            setBatchFiles((prev) => {
              let matched = false;
              const next = prev.map((item) => {
                if (!task.clientId || item.clientId !== task.clientId) return item;
                matched = true;
                return { ...item, filename, filepath, status: "success" as FileStatus, error: "" };
              });
              if (!matched && filepath) {
                next.unshift({
                  filename,
                  filepath,
                  status: "success",
                  error: "",
                  clientId: task.clientId,
                });
              }
              return next;
            });
          }
          cachedResult = {
            taskId: task.taskId,
            kind: task.kind === "url" ? "url" : "single",
            data,
          };
        }
        taskResultCacheRef.current.set(task.taskId, cachedResult);
        loadedTaskResultsRef.current.add(task.taskId);
        resultRetryAttemptsRef.current.delete(task.taskId);
        resultRetryNotifiedRef.current.delete(task.taskId);
        const retryTimer = resultRetryTimersRef.current.get(task.taskId);
        if (retryTimer) clearTimeout(retryTimer);
        resultRetryTimersRef.current.delete(task.taskId);
        presentAnalysisTaskResult(latestPresentationToken());
        await loadHistory();
      } catch (error) {
        const apiError = error instanceof ApiRequestError ? error : null;
        if (classifyResultLoadFailure(apiError?.status) === "unavailable") {
          const unavailable = markTaskUnavailable(task);
          setTaskQueue((prev) =>
            prev.map((item) => (item.taskId === task.taskId ? unavailable : item)),
          );
          if (task.kind === "url" && task.payload.url) setSourceUrl(task.payload.url);
          updateFilesForTask(unavailable);
          resultRetryAttemptsRef.current.delete(task.taskId);
          resultRetryNotifiedRef.current.delete(task.taskId);
          const retryTimer = resultRetryTimersRef.current.get(task.taskId);
          if (retryTimer) clearTimeout(retryTimer);
          resultRetryTimersRef.current.delete(task.taskId);
          showError(unavailable.message);
        } else {
          const attempt = resultRetryAttemptsRef.current.get(task.taskId) || 0;
          resultRetryAttemptsRef.current.set(task.taskId, attempt + 1);
          if (!resultRetryTimersRef.current.has(task.taskId)) {
            const retryTimer = setTimeout(() => {
              resultRetryTimersRef.current.delete(task.taskId);
              setResultRetryTick((value) => value + 1);
            }, resultLoadRetryDelayMs(attempt));
            resultRetryTimersRef.current.set(task.taskId, retryTimer);
          }
          if (!resultRetryNotifiedRef.current.has(task.taskId)) {
            resultRetryNotifiedRef.current.add(task.taskId);
            showError("读取分析结果暂时失败，将自动重试。");
          }
        }
      } finally {
        loadingTaskResultsRef.current.delete(task.taskId);
      }
    },
    [
      fetchJson,
      loadHistory,
      presentAnalysisTaskResult,
      presentationTokenForTask,
      showError,
      updateFilesForTask,
    ],
  );

  const analyzeByUploadedFile = useCallback(
    async (file: BatchFileItem) => {
      setBatchFiles((prev) =>
        prev.map((item) =>
          item.filepath === file.filepath
            ? { ...item, status: "processing", error: "正在提交分析任务..." }
            : item,
        ),
      );
      try {
        await submitAnalysisTask(
          "single",
          {
            filepath: file.filepath,
            summary_only: summaryOnly,
            output_template: outputTemplate,
          },
          file.filename,
          file.clientId,
        );
      } catch (error) {
        const message = String((error as Error).message || error);
        setBatchFiles((prev) =>
          prev.map((item) =>
            item.filepath === file.filepath ? { ...item, status: "failed", error: message } : item,
          ),
        );
        showError(`提交单文件分析失败: ${message}`);
      }
    },
    [outputTemplate, showError, submitAnalysisTask, summaryOnly],
  );

  const analyzeSingle = useCallback(async () => {
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length !== 1) return;
    await analyzeByUploadedFile(analyzableFiles[0]);
  }, [analyzeByUploadedFile, getAnalyzableBatchFiles]);

  const uploadBySourceUrl = useCallback(async (targetUrl: string) => {
    const uploaded = await fetchJson<{ filename: string; filepath: string; download_title?: string }>("/upload_url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: targetUrl,
      }),
    });
    const uploadedPath = String(uploaded.filepath || "").trim();
    if (!uploadedPath) throw new Error("链接导入失败：未返回可分析文件");

    const uploadedName =
      String(uploaded.download_title || uploaded.filename || "").trim() ||
      basename(uploadedPath) ||
      "链接视频";
    return {
      filename: uploadedName,
      filepath: uploadedPath,
      status: "pending",
      error: "",
    } satisfies BatchFileItem;
  }, [fetchJson]);

  const importSourceUrlOnly = useCallback(async () => {
    const urls = parseSourceUrls(sourceUrl);
    if (urls.length === 0) {
      showError("请输入有效的视频链接（http/https）");
      sourceUrlInputRef.current?.focus();
      return;
    }
    const readyForUpload = await verifyModelConnectionForUpload();
    if (!readyForUpload) return;

    const clientId = nextPendingFileId("url");
    const placeholder: BatchFileItem = {
      filename: guessUrlVideoName(urls[0]),
      filepath: "",
      status: "processing",
      error: "正在导入链接视频...",
      clientId,
    };
    setBatchFiles((prev) => [placeholder, ...prev]);
    setImportingUrl(true);

    try {
      const uploadedItem = await uploadBySourceUrl(urls[0]);
      replaceBatchFileByClientId(clientId, { ...uploadedItem, clientId });
      setSourceUrl("");
      showSuccess("链接导入成功，可直接开始分析。");
    } catch (error) {
      const message = `链接导入失败: ${String((error as Error).message || error)}`;
      replaceBatchFileByClientId(clientId, {
        ...placeholder,
        status: "failed",
        error: formatInlineErrorMessage(message),
      });
      showError(message);
    } finally {
      setImportingUrl(false);
    }
  }, [
    guessUrlVideoName,
    nextPendingFileId,
    replaceBatchFileByClientId,
    showError,
    showSuccess,
    sourceUrl,
    uploadBySourceUrl,
    verifyModelConnectionForUpload,
  ]);

  const analyzeBySourceUrl = useCallback(async () => {
    const urls = parseSourceUrls(sourceUrl);
    if (urls.length === 0) {
      showError("请输入有效的视频链接（http/https）");
      sourceUrlInputRef.current?.focus();
      return;
    }
    const readyForUpload = await verifyModelConnectionForUpload();
    if (!readyForUpload) return;

    const clientId = nextPendingFileId("url");
    const placeholder: BatchFileItem = {
      filename: guessUrlVideoName(urls[0]),
      filepath: "",
      status: "processing",
      error: "正在提交链接分析任务...",
      clientId,
    };
    setBatchFiles((prev) => [placeholder, ...prev]);
    setImportingUrl(true);

    try {
      await submitAnalysisTask(
        "url",
        {
          url: urls[0],
          filename: placeholder.filename,
          summary_only: summaryOnly,
          output_template: outputTemplate,
        },
        placeholder.filename,
        clientId,
      );
      setSourceUrl("");
    } catch (error) {
      const message = `提交链接分析失败: ${String((error as Error).message || error)}`;
      if (WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint))) setWebSearch(false);
      replaceBatchFileByClientId(clientId, {
        ...placeholder,
        status: "failed",
        error: formatInlineErrorMessage(message),
      });
      showError(message);
    } finally {
      setImportingUrl(false);
    }
  }, [
    guessUrlVideoName,
    nextPendingFileId,
    replaceBatchFileByClientId,
    outputTemplate,
    showError,
    sourceUrl,
    submitAnalysisTask,
    summaryOnly,
    verifyModelConnectionForUpload,
  ]);

  const analyzeBatch = useCallback(async () => {
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length <= 1) return;
    const filepaths = analyzableFiles.map((item) => item.filepath);
    const targetPaths = new Set(filepaths);
    setBatchFiles((prev) =>
      prev.map((item) =>
        targetPaths.has(item.filepath)
          ? { ...item, status: "processing", error: "正在提交批量分析任务..." }
          : item,
      ),
    );
    try {
      await submitAnalysisTask(
        "batch",
        { filepaths, summary_only: summaryOnly, output_template: outputTemplate },
        `${filepaths.length} 个视频`,
      );
    } catch (error) {
      const message = String((error as Error).message || error);
      if (WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint))) setWebSearch(false);
      setBatchFiles((prev) =>
        prev.map((item) =>
          targetPaths.has(item.filepath) ? { ...item, status: "failed", error: message } : item,
        ),
      );
      showError(`提交批量分析失败: ${message}`);
    }
  }, [
    getAnalyzableBatchFiles,
    outputTemplate,
    showError,
    submitAnalysisTask,
    summaryOnly,
  ]);

  const startAnalyze = useCallback(async () => {
    setSavedBatchResult(null);
    setSavedBatchResultTaskId("");
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length === 1) return analyzeSingle();
    if (analyzableFiles.length > 1) return analyzeBatch();
    if (batchFilesRef.current.length > 0) {
      showError("没有可分析的视频，请查看失败原因后重试上传。");
      return;
    }
    if (parseSourceUrls(sourceUrl).length > 0) {
      await analyzeBySourceUrl();
      return;
    }
    showError("请先上传视频文件");
  }, [analyzeBatch, analyzeBySourceUrl, analyzeSingle, getAnalyzableBatchFiles, showError, sourceUrl]);

  const activeTaskIds = taskQueue
    .filter(shouldPollTask)
    .map((task) => task.taskId)
    .sort()
    .join("|");

  useEffect(() => {
    if (!activeTaskIds) return;
    let stopped = false;
    let polling = false;
    const poll = async () => {
      if (polling || stopped) return;
      polling = true;
      try {
        const activeTasks = taskQueueRef.current.filter(shouldPollTask);
        await Promise.all(
          activeTasks.map(async (task) => {
            try {
              const status = await fetchJson<AnalysisTaskStatusResponse>(
                `/analysis_tasks/${encodeURIComponent(task.taskId)}`,
              );
              if (stopped) return;
              const nextTask = mergeTaskStatus(task, status);
              setTaskQueue((prev) =>
                prev.map((item) => (item.taskId === nextTask.taskId ? nextTask : item)),
              );
              updateFilesForTask(nextTask);
            } catch (error) {
              if (stopped) return;
              const apiError = error instanceof ApiRequestError ? error : null;
              if (apiError?.status !== 404) return;
              const unavailable = markTaskUnavailable(task);
              setTaskQueue((prev) =>
                prev.map((item) => (item.taskId === task.taskId ? unavailable : item)),
              );
              if (task.kind === "url" && task.payload.url) setSourceUrl(task.payload.url);
              updateFilesForTask(unavailable);
              showError(unavailable.message);
            }
          }),
        );
      } finally {
        polling = false;
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), progressPollIntervalMs);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [activeTaskIds, fetchJson, progressPollIntervalMs, showError, updateFilesForTask]);

  useEffect(() => {
    if (resultPresentationRef.current.mode !== "auto") return;
    const target = [...taskQueue]
      .reverse()
      .find(
        (task) =>
          task.status === "uploading" ||
          task.status === "queued" ||
          task.status === "analyzing" ||
          task.status === "completed",
      );
    if (target && resultPresentationRef.current.taskId !== target.taskId) {
      const presentationToken = requestTaskPresentation(target.taskId);
      if (target.status === "completed") {
        void loadAnalysisTaskResult(target, presentationToken);
      }
    }
  }, [loadAnalysisTaskResult, requestTaskPresentation, taskQueue]);

  const completedTaskIds = taskQueue
    .filter((task) => task.status === "completed")
    .map((task) => task.taskId)
    .join("|");

  useEffect(() => {
    if (!completedTaskIds) return;
    const currentPresentation = resultPresentationRef.current;
    const pendingTasks = pendingCompletedTasks(
      taskQueueRef.current,
      loadedTaskResultsRef.current,
      loadingTaskResultsRef.current,
      resultRetryTimersRef.current.keys(),
      currentPresentation.mode === "auto" ? currentPresentation.taskId : "",
    );
    pendingTasks.forEach((task) => {
      void loadAnalysisTaskResult(task, presentationTokenForTask(task.taskId));
    });
  }, [completedTaskIds, loadAnalysisTaskResult, presentationTokenForTask, resultRetryTick]);

  const cancelAnalysisTask = useCallback(
    async (task: AnalysisTaskQueueItem) => {
      setTaskActionId(task.taskId);
      try {
        const status = await fetchJson<AnalysisTaskStatusResponse>(
          `/analysis_tasks/${encodeURIComponent(task.taskId)}/cancel`,
          { method: "POST" },
        );
        const nextTask = mergeTaskStatus(task, status);
        setTaskQueue((prev) =>
          prev.map((item) => (item.taskId === task.taskId ? nextTask : item)),
        );
        updateFilesForTask(nextTask);
      } catch (error) {
        showError(`取消任务失败: ${String((error as Error).message || error)}`);
      } finally {
        setTaskActionId("");
      }
    },
    [fetchJson, showError, updateFilesForTask],
  );

  const retryAnalysisTask = useCallback(
    async (task: AnalysisTaskQueueItem) => {
      setTaskActionId(task.taskId);
      requestTaskPresentation(task.taskId);
      try {
        const status = await fetchJson<AnalysisTaskStatusResponse>(
          `/analysis_tasks/${encodeURIComponent(task.taskId)}/retry`,
          { method: "POST" },
        );
        const nextTask = mergeTaskStatus(task, status);
        loadingTaskResultsRef.current.delete(task.taskId);
        loadedTaskResultsRef.current.delete(task.taskId);
        taskResultCacheRef.current.delete(task.taskId);
        resultRetryAttemptsRef.current.delete(task.taskId);
        resultRetryNotifiedRef.current.delete(task.taskId);
        const retryTimer = resultRetryTimersRef.current.get(task.taskId);
        if (retryTimer) clearTimeout(retryTimer);
        resultRetryTimersRef.current.delete(task.taskId);
        setTaskQueue((prev) =>
          prev.map((item) => (item.taskId === task.taskId ? nextTask : item)),
        );
        setView("upload");
        updateFilesForTask(nextTask);
      } catch (error) {
        showError(`重试任务失败: ${String((error as Error).message || error)}`);
      } finally {
        setTaskActionId("");
      }
    },
    [fetchJson, requestTaskPresentation, showError, updateFilesForTask],
  );

  const retryFailedBatchItems = useCallback(async () => {
    if (!batchResultData) return;
    const sourceTask = taskQueueRef.current.find(
      (task) =>
        task.taskId === batchResultTaskId &&
        task.kind === "batch" &&
        task.status === "completed",
    );
    if (!sourceTask) {
      showError("缺少批量任务信息，无法重试失败项。");
      return;
    }
    const filepaths = batchRetryFilepathsForTask(
      taskQueueRef.current,
      batchResultTaskId,
      batchResultData.results || [],
    );
    if (filepaths.length === 0) return;
    const targetPaths = new Set(filepaths);
    setBatchFiles((prev) =>
      prev.map((item) =>
        targetPaths.has(item.filepath)
          ? { ...item, status: "processing", error: "正在重新提交分析..." }
          : item,
      ),
    );
    setView("upload");
    try {
      await submitAnalysisTask(
        "batch",
        { ...sourceTask.payload, filepaths },
        `${filepaths.length} 个失败视频`,
      );
    } catch (error) {
      const message = String((error as Error).message || error);
      setBatchFiles((prev) =>
        prev.map((item) =>
          targetPaths.has(item.filepath) ? { ...item, status: "failed", error: message } : item,
        ),
      );
      showError(`提交失败项重试失败: ${message}`);
    }
  }, [batchResultData, batchResultTaskId, showError, submitAnalysisTask]);

  const retryFailedBatchItem = useCallback(
    async (item: BatchResultItem) => {
      const sourceTask = taskQueueRef.current.find(
        (task) =>
          task.taskId === batchResultTaskId &&
          task.kind === "batch" &&
          task.status === "completed",
      );
      const filepath = batchRetryFilepathForItem(
        taskQueueRef.current,
        batchResultTaskId,
        item,
      );
      if (!sourceTask || !filepath) {
        showError("无法确定该失败项对应的原文件，未发起重试。");
        return;
      }
      setBatchFiles((prev) =>
        prev.map((file) =>
          file.filepath === filepath
            ? { ...file, status: "processing", error: "正在重新提交分析..." }
            : file,
        ),
      );
      try {
        await submitAnalysisTask(
          "batch",
          { ...sourceTask.payload, filepaths: [filepath] },
          `重试：${item.filename || basename(filepath)}`,
        );
      } catch (error) {
        const message = String((error as Error).message || error);
        setBatchFiles((prev) =>
          prev.map((file) =>
            file.filepath === filepath
              ? { ...file, status: "failed", error: message }
              : file,
          ),
        );
        showError(`提交单项重试失败: ${message}`);
      }
    },
    [batchResultTaskId, showError, submitAnalysisTask],
  );

  const openBatchTaskCenterResult = useCallback(
    async (task: AnalysisTaskQueueItem) => {
      if (task.status !== "completed") return;
      const presentationToken = requestTaskPresentation(task.taskId);
      if (!presentAnalysisTaskResult(presentationToken)) {
        await loadAnalysisTaskResult(task, presentationToken);
      }
    },
    [loadAnalysisTaskResult, presentAnalysisTaskResult, requestTaskPresentation],
  );

  const openHistoryRecord = useCallback(
    async (recordId: string) => {
      invalidateTaskPresentation();
      showProgress("加载中", "正在读取历史记录...");
      try {
        const data = await fetchJson<{ record?: Partial<SingleResultData> & { steps?: StepItem[] } }>(
          `/history/${recordId}`,
        );
        const record = data.record || {};
        setResultData({
          steps: Array.isArray(record.steps) ? record.steps : [],
          markdown: record.markdown || "",
          output_dir: record.output_dir || "",
          output_dir_name: record.output_dir_name || "",
          pdf_path: record.pdf_path || "",
          has_steps: Boolean(record.steps && Array.isArray(record.steps) && record.steps.length > 0),
          result_mode: String(record.result_mode || ""),
          fallback_used: Boolean(record.fallback_used),
          analysis_note: String(record.analysis_note || ""),
          quality_score: Number(record.quality_score || 0),
          degrade_reason: String(record.degrade_reason || ""),
          content_title: String(record.content_title || ""),
          confidence_note: String(record.confidence_note || ""),
          output_template:
            record.output_template === "content_summary"
              ? "content_summary"
              : "operation_guide",
          external_references: Array.isArray(record.external_references)
            ? record.external_references
            : [],
          video_preview_url: String(record.video_preview_url || ""),
          subtitle_available: Boolean(record.subtitle_available),
          subtitle_file_name: String(record.subtitle_file_name || ""),
          subtitle_line_count: Number(record.subtitle_line_count || 0),
          subtitle_exports:
            record.subtitle_exports && typeof record.subtitle_exports === "object"
              ? (record.subtitle_exports as Record<string, string>)
              : {},
          subtitle_workbench_url: String(record.subtitle_workbench_url || ""),
        });
        setSavedBatchResult(null);
        setSavedBatchResultTaskId("");
        setBatchResultData(null);
        setBatchResultTaskId("");
        setIsEditMode(false);
        setEditedSteps([]);
        setActiveResultTab("steps");
        setView("result");
        if (resultsRef.current) {
          resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
        }
      } catch (error) {
        showError(`加载历史失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [fetchJson, hideProgress, invalidateTaskPresentation, showError, showProgress, uiScrollBehavior],
  );

  const openBatchResultItem = useCallback(
    async (item: BatchResultItem) => {
      invalidateTaskPresentation();
      const outputDirName = basename(item.output_dir_name || item.output_dir);
      if (!outputDirName) {
        showError("该结果缺少输出目录，无法打开详情");
        return;
      }
      showProgress("加载中", "正在读取分析结果...");
      const base = `/output/${encodeURIComponent(outputDirName)}`;
      try {
        const [stepsRes, markdownRes] = await Promise.all([
          fetch(`${base}/steps.json`, withHistoryClientHeader()).catch(() => null),
          fetch(`${base}/operation_guide.md`, withHistoryClientHeader()).catch(() => null),
        ]);
        const steps =
          stepsRes && stepsRes.ok ? ((await stepsRes.json().catch(() => [])) as StepItem[]) : [];
        const markdown = markdownRes && markdownRes.ok ? await markdownRes.text().catch(() => "") : "";

        setResultData({
          steps: Array.isArray(steps) ? steps : [],
          markdown: markdown || "",
          output_dir: String(item.output_dir || outputDirName),
          output_dir_name: outputDirName,
          pdf_path: "",
          has_steps: Array.isArray(steps) && steps.length > 0,
          result_mode: String(item.result_mode || ""),
          fallback_used: Boolean(item.fallback_used),
          analysis_note: String(item.analysis_note || ""),
          quality_score: Number(item.quality_score || 0),
          degrade_reason: String(item.degrade_reason || ""),
          content_title: String(item.content_title || item.filename || ""),
          key_points: Array.isArray(item.key_points) ? item.key_points : [],
          timeline_points: Array.isArray(item.timeline_points) ? item.timeline_points : [],
          confidence_note: String(item.confidence_note || ""),
          output_template:
            item.output_template === "content_summary"
              ? "content_summary"
              : "operation_guide",
          external_references: Array.isArray(item.external_references)
            ? item.external_references
            : [],
          video_preview_url: String(item.video_preview_url || ""),
          subtitle_available: Boolean(item.subtitle_available),
          subtitle_file_name: String(item.subtitle_file_name || ""),
          subtitle_line_count: Number(item.subtitle_line_count || 0),
          subtitle_exports:
            item.subtitle_exports && typeof item.subtitle_exports === "object"
              ? (item.subtitle_exports as Record<string, string>)
              : {},
          subtitle_workbench_url: String(item.subtitle_workbench_url || ""),
        });
        setSavedBatchResult(batchResultData);
        setSavedBatchResultTaskId(batchResultTaskId);
        setBatchResultData(null);
        setBatchResultTaskId("");
        setIsEditMode(false);
        setEditedSteps([]);
        setActiveResultTab("steps");
        setView("result");
        if (resultsRef.current) {
          resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
        } else if (typeof window !== "undefined") {
          window.scrollTo({ top: 0, behavior: uiScrollBehavior });
        }
      } catch (error) {
        showError(`打开结果失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [
      batchResultData,
      batchResultTaskId,
      hideProgress,
      invalidateTaskPresentation,
      showError,
      showProgress,
      uiScrollBehavior,
      withHistoryClientHeader,
    ],
  );

  const returnToBatchResult = useCallback(() => {
    if (!savedBatchResult) return;
    invalidateTaskPresentation();
    setBatchResultData(savedBatchResult);
    setBatchResultTaskId(savedBatchResultTaskId);
    setSavedBatchResult(null);
    setSavedBatchResultTaskId("");
    setResultData(null);
    setIsEditMode(false);
    setEditedSteps([]);
    if (resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
    } else if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: uiScrollBehavior });
    }
  }, [invalidateTaskPresentation, savedBatchResult, savedBatchResultTaskId, uiScrollBehavior]);

  const openDeleteHistoryConfirm = useCallback(
    (record: HistoryItem) => {
      if (!record?.id || clearingHistory || loadingHistory || Boolean(deletingHistoryId)) return;
      setShowClearHistoryConfirm(false);
      setPendingDeleteHistory(record);
    },
    [clearingHistory, deletingHistoryId, loadingHistory],
  );

  const closeDeleteHistoryConfirm = useCallback(() => {
    if (deletingHistoryId) return;
    setPendingDeleteHistory(null);
  }, [deletingHistoryId]);

  const removeHistoryRecord = useCallback(async () => {
    const recordId = pendingDeleteHistory?.id;
    if (!recordId) return;
    setDeletingHistoryId(recordId);
    try {
      await fetchJson(`/history/${recordId}`, { method: "DELETE" });
      await loadHistory();
      setPendingDeleteHistory(null);
    } catch (error) {
      showError(`删除失败: ${String((error as Error).message || error)}`);
    } finally {
      setDeletingHistoryId("");
    }
  }, [fetchJson, loadHistory, pendingDeleteHistory, showError]);

  const openClearHistoryConfirm = useCallback(() => {
    if (history.length === 0 || clearingHistory || loadingHistory || Boolean(deletingHistoryId)) return;
    setPendingDeleteHistory(null);
    setShowClearHistoryConfirm(true);
  }, [clearingHistory, deletingHistoryId, history.length, loadingHistory]);

  const closeClearHistoryConfirm = useCallback(() => {
    if (clearingHistory) return;
    setShowClearHistoryConfirm(false);
  }, [clearingHistory]);

  const clearAllHistoryRecords = useCallback(async () => {
    if (history.length === 0) {
      setShowClearHistoryConfirm(false);
      return;
    }
    setClearingHistory(true);
    try {
      for (const record of history) {
        await fetchJson(`/history/${record.id}`, { method: "DELETE" });
      }
      await loadHistory();
      setShowClearHistoryConfirm(false);
    } catch (error) {
      showError(`清空失败: ${String((error as Error).message || error)}`);
    } finally {
      setClearingHistory(false);
    }
  }, [fetchJson, history, loadHistory, showError]);

  const openHistoryRecordFromDrawer = useCallback(
    async (recordId: string) => {
      setHistoryDrawerOpen(false);
      await openHistoryRecord(recordId);
    },
    [openHistoryRecord],
  );

  const saveEditedSteps = useCallback(async () => {
    if (!resultData?.output_dir) return showError("缺少输出目录信息");
    setSavingSteps(true);
    showProgress("重新生成中", "根据编辑步骤生成新文档...");

    const requestRegenerate = async () =>
      fetchJson<SingleResultData>("/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          steps: editedSteps,
          output_dir: resultData.output_dir,
          output_template: resultData.output_template || "operation_guide",
        }),
      });

    try {
      const data = await requestRegenerate();

      setResultData(data);
      setIsEditMode(false);
      setEditedSteps([]);
    } catch (error) {
      showError(`重新生成失败: ${String((error as Error).message || error)}`);
    } finally {
      setSavingSteps(false);
      hideProgress();
    }
  }, [editedSteps, fetchJson, hideProgress, resultData, showError, showProgress]);

  const triggerDownload = useCallback((blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, []);

  const downloadSingleZip = useCallback(async () => {
    const outputDirName = basename(resultData?.output_dir);
    if (!outputDirName) return showError("没有可下载结果");
    try {
      const blob = await fetchBlob(`/download_zip/${encodeURIComponent(outputDirName)}`);
      triggerDownload(blob, `${outputDirName}.zip`);
    } catch (error) {
      showError(`下载失败: ${String((error as Error).message || error)}`);
    }
  }, [fetchBlob, resultData?.output_dir, showError, triggerDownload]);

  const downloadSingleFromBatch = useCallback(
    async (outputDir: string | undefined, filename: string | undefined) => {
      const outputDirName = basename(outputDir);
      if (!outputDirName) return showError("下载路径无效");
      try {
        const blob = await fetchBlob(`/download_zip/${encodeURIComponent(outputDirName)}`);
        const baseName = basename(filename).replace(/\.[^/.]+$/, "") || outputDirName;
        triggerDownload(blob, `${baseName}.zip`);
      } catch (error) {
        showError(`下载失败: ${String((error as Error).message || error)}`);
      }
    },
    [fetchBlob, showError, triggerDownload],
  );

  const downloadBatchZip = useCallback(async () => {
    const outputDirs = (batchResultData?.results || [])
      .filter((item) => item.success && item.output_dir)
      .map((item) => String(item.output_dir));
    if (outputDirs.length === 0) return showError("没有可下载批量结果");
    try {
      const blob = await fetchBlob("/download_batch_zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_dirs: outputDirs }),
      });
      triggerDownload(blob, "batch_results.zip");
    } catch (error) {
      showError(`下载失败: ${String((error as Error).message || error)}`);
    }
  }, [batchResultData?.results, fetchBlob, showError, triggerDownload]);

  const loadSubtitleWorkbench = useCallback(
    async (outputDir: string) => {
      const outputDirName = basename(outputDir);
      if (!outputDirName) {
        setSubtitleWorkbench(null);
        setSubtitleLoadError("");
        return;
      }
      setSubtitleLoading(true);
      setSubtitleLoadError("");
      try {
        const data = await fetchJson<SubtitleWorkbenchData>(
          `/subtitle_workbench?output_dir=${encodeURIComponent(outputDirName)}&limit=12000`,
        );
        setSubtitleWorkbench(data);
        setSubtitleLoadError("");
      } catch (error) {
        setSubtitleWorkbench(null);
        setSubtitleLoadError(String((error as Error).message || error || "字幕加载失败"));
      } finally {
        setSubtitleLoading(false);
      }
    },
    [fetchJson],
  );

  useEffect(() => {
    const outputDir = String(resultData?.output_dir || "").trim();
    const blockedMode = String(resultData?.result_mode || "").trim().toLowerCase() === "blocked_notice";
    if (!outputDir || blockedMode) {
      setSubtitleWorkbench(null);
      setSubtitleLoading(false);
      setSubtitleLoadError("");
      return;
    }
    let cancelled = false;
    setSubtitleLoading(true);
    setSubtitleLoadError("");
    void loadSubtitleWorkbench(outputDir)
      .catch(() => {
        if (!cancelled) setSubtitleWorkbench(null);
      })
      .finally(() => {
        if (!cancelled) setSubtitleLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [loadSubtitleWorkbench, resultData?.output_dir, resultData?.result_mode]);

  useEffect(() => {
    setSubtitleKeyword("");
  }, [resultData?.output_dir]);

  useEffect(() => {
    const blocked = String(resultData?.result_mode || "").trim().toLowerCase() === "blocked_notice";
    const single = Boolean(resultData);
    if (activeResultTab === "document" && !(single && !blocked && Boolean(resultData?.markdown))) {
      setActiveResultTab("steps");
      return;
    }
    if (activeResultTab === "subtitle" && !(single && !blocked && Boolean(resultData?.output_dir))) {
      setActiveResultTab("steps");
    }
  }, [activeResultTab, resultData]);

  const downloadSubtitleZip = useCallback(
    async () => {
      const outputDirName = basename(resultData?.output_dir);
      if (!outputDirName) {
        showError("没有可下载字幕的结果");
        return;
      }
      try {
        const blob = await fetchBlob(`/download_subtitles_zip/${encodeURIComponent(outputDirName)}`);
        triggerDownload(blob, `${outputDirName}_subtitles.zip`);
      } catch (error) {
        showError(`字幕下载失败: ${String((error as Error).message || error)}`);
      }
    },
    [fetchBlob, resultData?.output_dir, showError, triggerDownload],
  );

  const refreshSubtitleWorkbench = useCallback(async () => {
    const outputDirName = basename(resultData?.output_dir);
    if (!outputDirName) {
      showError("没有可重新加载字幕的结果");
      return;
    }
    setSubtitleRefreshing(true);
    setSubtitleLoadError("");
    try {
      const data = await fetchJson<SubtitleWorkbenchData>(
        `/refresh_subtitle/${encodeURIComponent(outputDirName)}`,
        { method: "POST" },
      );
      setSubtitleWorkbench(data);
      setSubtitleLoadError("");
    } catch (error) {
      setSubtitleLoadError(String((error as Error).message || error || "字幕重新加载失败"));
      showError(`字幕重新加载失败: ${String((error as Error).message || error)}`);
    } finally {
      setSubtitleRefreshing(false);
    }
  }, [fetchJson, resultData?.output_dir, showError]);

  const seekVideoTo = useCallback((seconds: number) => {
    const videoEl = subtitleVideoRef.current;
    if (!videoEl) return;
    const targetSeconds = Math.max(0, Number(seconds) || 0);
    videoEl.currentTime = targetSeconds;
    void videoEl.play().catch(() => undefined);
  }, []);

  const formatSubtitleDisplayTime = useCallback((value: unknown) => {
    const text = String(value || "").trim();
    const matched = text.match(/^(\d{1,2}:\d{2}:\d{2})/);
    return matched?.[1] || text || "00:00:00";
  }, []);

  const subtitleLines = useMemo(() => (Array.isArray(subtitleWorkbench?.lines) ? subtitleWorkbench?.lines || [] : []), [subtitleWorkbench?.lines]);
  const subtitleAssetAvailable = useMemo(() => {
    const exportsObj =
      resultData?.subtitle_exports && typeof resultData.subtitle_exports === "object"
        ? (resultData.subtitle_exports as Record<string, string>)
        : {};
    return Boolean(
      String(subtitleWorkbench?.subtitle_file || "").trim() ||
        String(resultData?.subtitle_file_name || "").trim() ||
        Boolean(subtitleWorkbench?.subtitle_available) ||
        Boolean(resultData?.subtitle_available) ||
        Number(resultData?.subtitle_line_count || 0) > 0 ||
        Object.keys(exportsObj).length > 0,
    );
  }, [
    resultData?.subtitle_available,
    resultData?.subtitle_exports,
    resultData?.subtitle_file_name,
    resultData?.subtitle_line_count,
    subtitleWorkbench?.subtitle_available,
    subtitleWorkbench?.subtitle_file,
  ]);
  const filteredSubtitleLines = useMemo(() => {
    const keyword = String(subtitleKeyword || "").trim().toLowerCase();
    if (!keyword) return subtitleLines;
    return subtitleLines.filter((line) => {
      const text = String(line.text || "").toLowerCase();
      const start = String(line.start_time || "").toLowerCase();
      const end = String(line.end_time || "").toLowerCase();
      return text.includes(keyword) || start.includes(keyword) || end.includes(keyword);
    });
  }, [subtitleKeyword, subtitleLines]);

  const renderedMarkdown = useMemo(() => {
    if (!resultData?.markdown) return "";
    const outputDirName = basename(resultData.output_dir);
    const baseUrl = outputDirName ? `/output/${encodeURIComponent(outputDirName)}/` : "";
    const markdownText = String(resultData.markdown).replace(
      /!\[(.*?)\]\((images\/.*?)\)/g,
      (_m, alt, imgPath) => `![${alt}](${baseUrl}${imgPath})`,
    );
    return DOMPurify.sanitize(marked.parse(markdownText, { gfm: true, breaks: true }) as string);
  }, [resultData?.markdown, resultData?.output_dir]);

  const progressPercent = Math.max(0, Math.min(100, Math.round(progressBoard.percent || 0)));
  const progressModeText =
    progressBoard.mode === "upload"
      ? "上传进度"
      : progressBoard.mode === "single"
        ? "单文件分析"
        : progressBoard.mode === "batch"
          ? "批量分析"
          : "任务进度";
  const batchStatusText = (status: FileStatus) =>
    status === "success"
      ? "已完成"
      : status === "failed"
        ? "失败"
        : status === "cancelled"
          ? "已取消"
          : status === "uploading"
            ? "上传中"
        : status === "processing"
          ? "分析中"
          : "待处理";
  const handleOpenHistoryRecord = useCallback(
    (id: string) => {
      void openHistoryRecordFromDrawer(id);
    },
    [openHistoryRecordFromDrawer],
  );
  const handleDeleteHistoryRecord = useCallback(
    (record: HistoryItem) => {
      openDeleteHistoryConfirm(record);
    },
    [openDeleteHistoryConfirm],
  );
  const analyzableBatchCount = useMemo(
    () => batchFiles.filter((item) => Boolean(String(item.filepath || "").trim())).length,
    [batchFiles],
  );
  const hasUploadingFiles = useMemo(
    () => batchFiles.some((item) => item.status === "uploading"),
    [batchFiles],
  );
  const visibleTaskQueue = useMemo(
    () => taskQueue.filter((task) => task.kind !== "batch" && task.status !== "completed"),
    [taskQueue],
  );
  const hasSourceUrlInput = useMemo(() => parseSourceUrls(sourceUrl).length > 0, [sourceUrl]);
  const canAnalyze =
    !isAnalyzing && !importingUrl && !hasUploadingFiles && (analyzableBatchCount > 0 || hasSourceUrlInput);
  const analyzeButtonText = isAnalyzing
    ? analyzableBatchCount === 1
      ? "单文件处理中..."
      : "批量处理中..."
    : hasUploadingFiles
      ? "等待上传完成"
      : analyzableBatchCount === 1
      ? "开始单文件分析"
      : analyzableBatchCount > 1
        ? "开始分析"
        : hasSourceUrlInput
          ? "开始链接分析"
          : "开始分析";
  const hasSingleResult = Boolean(resultData);
  const hasBatchResult = Boolean(batchResultData);
  const hasAnyResult = hasSingleResult || hasBatchResult;
  const singleResultSteps = resultData?.steps || EMPTY_STEPS;
  const singleResultMode = String(resultData?.result_mode || "").trim().toLowerCase();
  const isBlockedNoticeResult = singleResultMode === "blocked_notice";
  const isResultView = view === "result" && hasAnyResult;
  const hasDocumentPanel = hasSingleResult && !isBlockedNoticeResult && Boolean(resultData?.markdown);
  const hasSubtitlePanel = hasSingleResult && !isBlockedNoticeResult && Boolean(resultData?.output_dir);
  const showStepsPanel = hasSingleResult && (isBlockedNoticeResult || Boolean(resultData));
  const confidenceLevel = useMemo<"high" | "medium" | "low" | null>(() => {
    if (!hasSingleResult || isBlockedNoticeResult) return null;
    const isDegraded = singleResultMode === "candidate_steps" || singleResultMode === "timeline_summary";
    const score = Number(resultData?.quality_score || 0);
    if (isDegraded) return "low";
    if (score > 0 && score < 0.6) return "low";
    if (score >= 0.6 && score < 0.8) return "medium";
    return "high";
  }, [hasSingleResult, isBlockedNoticeResult, resultData?.quality_score, singleResultMode]);
  const confidenceLabel =
    confidenceLevel === "high" ? "结果可信度 高" : confidenceLevel === "medium" ? "结果可信度 中" : "结果可信度 低";
  const currentResultName = useMemo(() => {
    if (hasBatchResult) return `批量结果（${batchResultData?.results?.length || 0} 个文件）`;
    const title = String(resultData?.content_title || "").trim();
    if (title) return title;
    const named = batchFiles.find((item) => item.status === "success" && item.filename);
    return String(named?.filename || "分析结果").trim() || "分析结果";
  }, [batchFiles, batchResultData?.results?.length, hasBatchResult, resultData?.content_title]);
  const resultSectionIds = useMemo(() => {
    const ids: string[] = [];
    if (hasSubtitlePanel) ids.push("result-panel-subtitle");
    if (showStepsPanel) ids.push("result-panel-steps");
    if (hasDocumentPanel) ids.push("result-panel-document");
    return ids;
  }, [hasDocumentPanel, hasSubtitlePanel, showStepsPanel]);

  // Scroll-spy: highlight whichever result panel is currently in view.
  useEffect(() => {
    if (typeof window === "undefined" || typeof IntersectionObserver === "undefined") return;
    if (!isResultView || resultSectionIds.length < 2) {
      setActiveResultSection("");
      return;
    }
    const elements = resultSectionIds
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => Boolean(el));
    if (elements.length === 0) return;

    const visibility = new Map<string, number>();
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          visibility.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
        }
        let topId = "";
        let topRatio = 0;
        visibility.forEach((ratio, id) => {
          if (ratio > topRatio) {
            topRatio = ratio;
            topId = id;
          }
        });
        if (topId) setActiveResultSection((prev) => (prev === topId ? prev : topId));
      },
      { rootMargin: "-30% 0px -55% 0px", threshold: [0, 0.25, 0.5, 1] },
    );
    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [isResultView, resultSectionIds]);

  // Reveal a "back to top" affordance once the result page is scrolled down.
  useEffect(() => {
    if (typeof window === "undefined") return;
    let rafId = 0;
    const syncVisibility = () => {
      const scrollTop = window.scrollY || document.documentElement.scrollTop || 0;
      const next = isResultView && scrollTop > 520;
      setShowBackToTop((prev) => (prev === next ? prev : next));
    };
    const handleScroll = () => {
      if (rafId) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = 0;
        syncVisibility();
      });
    };
    // Defer the initial sync so we don't setState synchronously in the effect body.
    const initialRafId = window.requestAnimationFrame(syncVisibility);
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => {
      window.cancelAnimationFrame(initialRafId);
      if (rafId) window.cancelAnimationFrame(rafId);
      window.removeEventListener("scroll", handleScroll);
    };
  }, [isResultView]);
  const goBackToUpload = useCallback(() => {
    invalidateTaskPresentation();
    setView("upload");
    setSavedBatchResult(null);
    setSavedBatchResultTaskId("");
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: uiScrollBehavior });
    }
  }, [invalidateTaskPresentation, uiScrollBehavior]);
  const scrollToPanel = useCallback(
    (panelId: string) => {
      if (typeof document === "undefined") return;
      const target = document.getElementById(panelId);
      if (target) target.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
    },
    [uiScrollBehavior],
  );
  const copyTextToClipboard = useCallback(
    async (text: string, successText: string) => {
      const content = String(text || "").trim();
      if (!content) {
        showError("没有可复制的内容");
        return;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(content);
        } else {
          const textarea = document.createElement("textarea");
          textarea.value = content;
          textarea.style.position = "fixed";
          textarea.style.opacity = "0";
          document.body.appendChild(textarea);
          textarea.select();
          document.execCommand("copy");
          document.body.removeChild(textarea);
        }
        showSuccess(successText);
      } catch (error) {
        showError(`复制失败: ${String((error as Error).message || error)}`);
      }
    },
    [showError, showSuccess],
  );
  const copyMarkdownSource = useCallback(() => {
    void copyTextToClipboard(String(resultData?.markdown || ""), "已复制 Markdown 源码");
  }, [copyTextToClipboard, resultData?.markdown]);
  const copyPlainText = useCallback(() => {
    if (typeof document === "undefined") return;
    const container = document.createElement("div");
    container.innerHTML = renderedMarkdown;
    const plainText = container.textContent || container.innerText || "";
    void copyTextToClipboard(plainText, "已复制纯文本");
  }, [copyTextToClipboard, renderedMarkdown]);
  const drawerOverlayActive =
    historyDrawerOpen || showClearHistoryConfirm || Boolean(pendingDeleteHistory);
  const heroCanvasAnimating = !mobilePerfMode && !drawerOverlayActive && heroAnimationActive;
  void heroCanvasAnimating;
  void CanvasText;
  void BrandStudioIcon;
  void HERO_TITLE_CANVAS_COLORS;
  void HERO_SUBTITLE_CANVAS_COLORS;
  const shouldShowBackgroundBeams = !mobilePerfMode;
  const shouldAnimateNoiseBackground = !mobilePerfMode && !drawerOverlayActive;
  const analyzeActionButton = (
    <button
      aria-busy={isAnalyzing}
      className={cn(
        "start-analyze-btn h-full w-full cursor-pointer rounded-full bg-linear-to-r from-neutral-950 via-black to-neutral-900 px-4 py-2 text-neutral-100 shadow-[0px_1px_0px_0px_rgba(255,255,255,0.09)_inset,0px_0.5px_1px_0px_rgba(148,163,184,0.32)] transition-all duration-150 disabled:cursor-not-allowed disabled:opacity-60",
        canAnalyze && "active:scale-98",
      )}
      disabled={!canAnalyze}
      onClick={() => {
        if (!canAnalyze) return;
        void startAnalyze();
      }}
    >
      <span className="inline-flex items-center justify-center gap-1.5">
        <PlayIcon className="h-3.5 w-3.5" />
        <span>{analyzeButtonText}</span>
      </span>
    </button>
  );
  const handleStudioClick = useCallback(() => {
    if (typeof window === "undefined") return;
    if (mobilePerfMode) {
      window.scrollTo({ top: 0, behavior: "auto" });
      window.location.reload();
      return;
    }

    const startY = window.scrollY || document.documentElement.scrollTop || 0;
    if (startY <= 1) {
      window.scrollTo({ top: 0, behavior: "auto" });
      window.location.reload();
      return;
    }

    const duration = 420;
    const startTime = performance.now();

    const animateToTop = (now: number) => {
      const progress = Math.min(1, (now - startTime) / duration);
      const nextY = Math.max(0, Math.round(startY * (1 - progress)));
      window.scrollTo(0, nextY);

      if (progress < 1) {
        window.requestAnimationFrame(animateToTop);
      } else {
        window.scrollTo(0, 0);
        window.location.reload();
      }
    };

    window.requestAnimationFrame(animateToTop);
  }, [mobilePerfMode]);

  return (
    <div className="app-root relative min-h-screen bg-neutral-950 text-neutral-100">
      {shouldShowBackgroundBeams ? (
        <div className="pointer-events-none absolute inset-0">
          <BackgroundBeams className="opacity-70" />
        </div>
      ) : null}
      <nav className="vi-nav fixed inset-x-0 top-0 z-40 w-full">
        <div className="vi-nav-inner mx-auto flex w-full max-w-[1320px] items-center justify-between px-4 sm:px-6 md:px-8">
          <button
            type="button"
            onClick={handleStudioClick}
            className="brand-nav-btn inline-flex items-center gap-2 rounded-sm text-sm font-semibold tracking-[0.12em] text-neutral-300 transition-colors hover:text-neutral-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/70"
          >
            <span className="brand-nav-icon-wrap" aria-hidden="true">
              <img src="/vite.ico" alt="" className="brand-nav-icon" />
            </span>
            <span>Video Insights</span>
          </button>
          <div className="flex items-center gap-2">
            {hasAnyResult ? (
              <button
                type="button"
                onClick={() => {
                  if (view === "result") {
                    goBackToUpload();
                  } else {
                    invalidateTaskPresentation();
                    setView("result");
                    if (typeof window !== "undefined") window.scrollTo({ top: 0, behavior: uiScrollBehavior });
                  }
                }}
                className="vi-nav-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
              >
                {view === "result" ? (
                  <>
                    <UploadIcon className="h-3.5 w-3.5" />
                    上传
                  </>
                ) : (
                  <>
                    <StepsIcon className="h-3.5 w-3.5" />
                    结果
                  </>
                )}
              </button>
            ) : null}
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
              title={theme === "dark" ? "切换到亮色主题" : "切换到暗色主题"}
              className="vi-nav-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
            >
              {theme === "dark" ? (
                <SunIcon className="h-3.5 w-3.5" />
              ) : (
                <MoonIcon className="h-3.5 w-3.5" />
              )}
              {theme === "dark" ? "亮色" : "暗色"}
            </button>
            <button
              type="button"
              aria-expanded={historyDrawerOpen}
              aria-controls="history-drawer"
              onClick={() => {
                setHistoryDrawerOpen((prev) => !prev);
              }}
              className="vi-nav-pill vi-nav-pill--accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
            >
              <HistoryIcon className="h-3.5 w-3.5" />
              历史
            </button>
          </div>
        </div>
      </nav>
      <main className="app-main relative z-10 mx-auto w-full max-w-[1320px] space-y-6 px-4 pb-8 pt-[5.25rem] sm:px-6 md:space-y-7 md:px-8 md:pb-10 md:pt-24">
        {!isResultView ? (
          <header className="vi-hero hero-panel panel-card motion-enter rounded-xl border-0 bg-transparent p-4">
          <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-3 text-center">
            <span className="vi-hero-eyebrow">AI · 视频理解工作台</span>
            <h1 className="vi-hero-title vi-hero-title-flip" aria-label="视频转文档，不止提取，更是理解">
              <motion.div className="relative mx-4 my-4 flex flex-col items-center justify-center gap-4 text-center sm:mx-0 sm:mb-0 sm:flex-row">
                <LayoutTextFlip text="视频转文档" words={["不止提取", "更是理解"]} />
              </motion.div>
            </h1>
            <p className="vi-hero-subtitle">
              AI 自动分析视频内容，抓取关键截图，拆解核心步骤，输出结构清晰、重点明确的总结文档。
              让信息沉淀更高效 — Turn insights into docs.
            </p>
            <div className="vi-hero-chips">
              <span className="vi-chip"><span className="vi-chip-dot" />Whisper ASR</span>
              <span className="vi-chip"><span className="vi-chip-dot" />批量处理</span>
              <span className="vi-chip"><span className="vi-chip-dot" />Markdown · PDF 导出</span>
              <span className="vi-chip"><span className="vi-chip-dot" />链接直达分析</span>
            </div>
          </div>
        </header>
        ) : null}

        <div className="app-grid grid items-start gap-5 2xl:gap-6">
          <section className="app-workspace motion-enter motion-delay-2 min-w-0 space-y-4">
            {!isResultView ? (
            <section className="panel-card rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
              <div className="vi-card-head">
                <div className="vi-card-title">
                  <span className="vi-card-title-ico"><UploadIcon className="h-4 w-4" /></span>
                  上传视频
                </div>
                <span className="vi-card-sub">拖拽 · 点击 · 链接 · 批量</span>
              </div>
              <div className="vi-url-bar mb-3">
                <div className="vi-url-bar__title">
                  <span aria-hidden="true">🔗</span>
                  视频链接直达分析
                </div>
                <div className="vi-url-bar__row">
                  <input
                    ref={sourceUrlInputRef}
                    type="url"
                    placeholder="粘贴视频链接（http/https）"
                    className="vi-input flex-1"
                    value={sourceUrl}
                    disabled={isAnalyzing || importingUrl}
                    onChange={(e) => setSourceUrl(e.target.value)}
                  />
                  <div className="flex shrink-0 gap-2">
                    <button
                      type="button"
                      className="vi-btn vi-btn--sm"
                      disabled={isAnalyzing || importingUrl}
                      onClick={() => void importSourceUrlOnly()}
                    >
                      {importingUrl ? "导入中..." : "导入链接"}
                    </button>
                    <button
                      type="button"
                      className="vi-btn vi-btn--sm vi-btn--primary"
                      disabled={isAnalyzing || importingUrl || hasUploadingFiles}
                      onClick={() => void analyzeBySourceUrl()}
                    >
                      {importingUrl ? "处理中..." : "链接直达分析"}
                    </button>
                  </div>
                </div>
              </div>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2 border-y border-neutral-800/80 py-2.5">
                <span className="text-sm font-medium text-neutral-200">输出模板</span>
                <div className="vi-template-selector inline-flex rounded border border-neutral-700 bg-neutral-950/45 p-0.5" role="group" aria-label="输出模板">
                  <button
                    type="button"
                    aria-pressed={outputTemplate === "operation_guide"}
                    className={cn(
                      "rounded px-3 py-1.5 text-xs transition-colors",
                      outputTemplate === "operation_guide"
                        ? "bg-cyan-500/18 text-cyan-100"
                        : "text-neutral-400 hover:text-neutral-200",
                    )}
                    onClick={() => setOutputTemplate("operation_guide")}
                  >
                    操作教程
                  </button>
                  <button
                    type="button"
                    aria-pressed={outputTemplate === "content_summary"}
                    className={cn(
                      "rounded px-3 py-1.5 text-xs transition-colors",
                      outputTemplate === "content_summary"
                        ? "bg-cyan-500/18 text-cyan-100"
                        : "text-neutral-400 hover:text-neutral-200",
                    )}
                    onClick={() => setOutputTemplate("content_summary")}
                  >
                    内容摘要
                  </button>
                </div>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="video/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = e.target.files;
                  if (files) void uploadBatchFiles(files);
                  e.target.value = "";
                }}
              />
              <div
                className={cn("vi-drop", batchDragOver && "vi-drop--active")}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => {
                  e.preventDefault();
                  setBatchDragOver(true);
                }}
                onDragLeave={() => setBatchDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setBatchDragOver(false);
                  if (e.dataTransfer.files) void uploadBatchFiles(e.dataTransfer.files);
                }}
              >
                <div className="vi-drop-icon">
                  <FolderPlusIcon className="h-7 w-7" />
                </div>
                <p className="vi-drop-title">点击选择 · 或拖拽视频到这里</p>
                <p className="vi-drop-hint">支持 MP4 / AVI / MOV / MKV / WMV / FLV / WebM / M4V 等</p>
              </div>
              <div className="vi-batch-list">
                {batchFiles.map((item, index) => (
                  <div
                    key={item.clientId || item.filepath || `${item.filename}-${index}`}
                    className={cn(
                      "vi-batch-row",
                      item.status === "failed" && "vi-batch-row--fail",
                      item.status === "cancelled" && "vi-batch-row--fail",
                      item.status === "success" && "vi-batch-row--ok",
                    )}
                  >
                    <div className="min-w-0 flex flex-1 items-start gap-2.5">
                      <FileVideoIcon
                        className={cn(
                          "mt-0.5 h-4 w-4 shrink-0 text-neutral-400 transition-colors",
                          item.status === "success" && "text-emerald-300",
                          item.status === "failed" && "text-rose-300",
                          item.status === "cancelled" && "text-neutral-400",
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-neutral-100">{item.filename}</p>
                        <p className={cn("text-xs", item.status === "failed" ? "text-rose-300/90" : "text-neutral-400")}>
                          {batchStatusText(item.status)}
                        </p>
                        {item.error ? (
                          <p className="mt-0.5 text-xs leading-5 text-rose-200/90 break-words">
                            {formatInlineErrorMessage(item.error)}
                          </p>
                        ) : null}
                      </div>
                    </div>
                    <div className="ml-2 flex shrink-0 self-center items-center gap-2">
                      {item.status === "success" ? (
                        <span className="vi-status vi-status--ok">
                          <StatusSuccessIcon /> 成功
                        </span>
                      ) : item.status === "failed" ? (
                        <span className="vi-status vi-status--fail">
                          <StatusFailedIcon /> 失败
                        </span>
                      ) : item.status === "cancelled" ? (
                        <span className="vi-status">
                          <StatusFailedIcon /> 已取消
                        </span>
                      ) : item.status === "uploading" ? (
                        <span className="vi-status vi-status--run">上传中</span>
                      ) : item.status === "processing" ? (
                        <span className="vi-status vi-status--run">分析中</span>
                      ) : (
                        <span className="vi-status">待处理</span>
                      )}
                      {item.status === "uploading" ? (
                        <button
                          type="button"
                          title="取消上传"
                          aria-label={`取消上传 ${item.filename}`}
                          className="vi-icon-btn vi-icon-btn--danger"
                          onClick={() => void cancelFileUpload(item)}
                        >
                          <CloseIcon />
                        </button>
                      ) : null}
                      {batchFiles.length > 1 ? (
                        <button
                          type="button"
                          title="删除文件"
                          aria-label="删除文件"
                          className="vi-icon-btn vi-icon-btn--danger"
                          disabled={isAnalyzing || item.status === "uploading"}
                          onClick={() => setBatchFiles((prev) => prev.filter((_, i) => i !== index))}
                        >
                          <TrashIcon />
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
              {visibleTaskQueue.length > 0 ? (
                <div className="mt-3 space-y-2" aria-label="分析任务状态">
                  {visibleTaskQueue.map((task) => {
                    const busy = taskActionId === task.taskId;
                    const canCancel = task.status === "uploading" || task.status === "queued" || task.status === "analyzing";
                    const canRetry =
                      task.retryable && (task.status === "failed" || task.status === "cancelled");
                    const percent = Math.max(0, Math.min(100, Math.round(task.percent || 0)));
                    return (
                      <div
                        key={task.taskId}
                        className="vi-task-row rounded border border-neutral-800 bg-neutral-950/55 px-3 py-2.5"
                      >
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div className="min-w-0">
                            <p className="truncate text-sm font-medium text-neutral-100" title={task.label}>
                              {task.label}
                            </p>
                            <p className="mt-0.5 text-xs text-neutral-400">
                              {TASK_STATUS_LABELS[task.status]}
                              {task.stage ? ` · 阶段：${STAGE_LABELS[task.stage] || task.stage}` : ""}
                              {task.total > 0 ? ` · ${task.current}/${task.total}` : ""}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            <span
                              className={cn(
                                "vi-status",
                                task.status === "failed" && "vi-status--fail",
                                (task.status === "queued" || task.status === "analyzing" || task.status === "uploading") && "vi-status--run",
                              )}
                            >
                              {TASK_STATUS_LABELS[task.status]}
                            </span>
                            {canCancel ? (
                              <button
                                type="button"
                                className="vi-btn vi-btn--sm"
                                disabled={Boolean(taskActionId) || task.cancelRequested}
                                onClick={() => void cancelAnalysisTask(task)}
                              >
                                {task.cancelRequested ? "取消中..." : "取消"}
                              </button>
                            ) : null}
                            {canRetry ? (
                              <button
                                type="button"
                                className="vi-btn vi-btn--sm vi-btn--primary"
                                disabled={Boolean(taskActionId)}
                                onClick={() => void retryAnalysisTask(task)}
                              >
                                {busy ? "重试中..." : "重试"}
                              </button>
                            ) : null}
                          </div>
                        </div>
                        {task.message ? (
                          <p className={cn(
                            "mt-1.5 text-xs break-words",
                            task.status === "failed" ? "text-rose-300" : "text-neutral-300",
                          )}>
                            {task.message}
                          </p>
                        ) : null}
                        {task.status === "queued" || task.status === "analyzing" || task.status === "uploading" ? (
                          <div className="vi-progress-track mt-2" aria-label={`任务进度 ${percent}%`}>
                            <div className="vi-progress-bar" style={{ width: `${percent}%` }} />
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              ) : null}
              {batchFiles.length > 0 ? (
                <button
                  type="button"
                  className="vi-btn vi-btn--block vi-btn--sm mt-2"
                  disabled={isAnalyzing || hasUploadingFiles}
                  onClick={() => setBatchFiles([])}
                >
                  <ClearIcon className="h-3.5 w-3.5" />
                  清空列表
                </button>
              ) : null}
              <div className="vi-cta">
                {mobilePerfMode ? (
                  <div className="mx-auto w-full rounded-full bg-neutral-950/95 p-2 ring-1 ring-white/5">
                    {analyzeActionButton}
                  </div>
                ) : (
                  <NoiseBackground
                    containerClassName="mx-auto w-full rounded-full bg-neutral-950/95 p-2 ring-1 ring-white/5"
                    className="w-full"
                    gradientColors={theme === "light" ? ANALYZE_BUTTON_LIGHT_GRADIENT_COLORS : ANALYZE_BUTTON_GRADIENT_COLORS}
                    noiseIntensity={0.07}
                    speed={0.13}
                    animating={shouldAnimateNoiseBackground}
                  >
                    {analyzeActionButton}
                  </NoiseBackground>
                )}
              </div>
            </section>
            ) : null}

            {!isResultView ? (
              <BatchTaskCenter
                tasks={taskQueue}
                actionTaskId={taskActionId}
                notificationEnabled={browserNotificationsEnabled}
                notificationPermission={browserNotificationPermission}
                onToggleNotifications={() => void toggleBrowserCompletionNotifications()}
                onCancel={(task) => void cancelAnalysisTask(task)}
                onRetry={(task) => void retryAnalysisTask(task)}
                onOpen={(task) => void openBatchTaskCenterResult(task)}
              />
            ) : null}

            {isResultView ? (
              <div ref={resultsRef} className="result-workspace motion-enter space-y-4">
                <section className="result-header-bar panel-card rounded-xl border border-neutral-800 bg-neutral-900/70 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex min-w-0 items-center gap-2">
                      {savedBatchResult ? (
                        <button
                          type="button"
                          onClick={returnToBatchResult}
                          className="vi-btn vi-btn--sm shrink-0"
                        >
                          ← 返回批量结果
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={goBackToUpload}
                          className="vi-btn vi-btn--sm shrink-0"
                        >
                          ← 返回上传
                        </button>
                      )}
                      <h2 className="truncate text-sm font-semibold text-neutral-100" title={currentResultName}>
                        {currentResultName}
                      </h2>
                    </div>
                  </div>
                  {hasSingleResult && !isBlockedNoticeResult ? (
                    <div className="result-overview mt-3 flex flex-wrap items-center gap-1.5">
                      {confidenceLevel ? (
                        <span
                          className={cn("confidence-badge", `confidence-badge--${confidenceLevel}`)}
                          title={
                            resultData?.quality_score
                              ? `质量分：${Number(resultData.quality_score).toFixed(2)}`
                              : undefined
                          }
                        >
                          <span className="confidence-badge-dot" />
                          {confidenceLabel}
                        </span>
                      ) : null}
                      {hasSubtitlePanel ? (
                        <button
                          type="button"
                          className={cn(
                            "result-overview-chip result-overview-chip--link",
                            activeResultSection === "result-panel-subtitle" && "result-overview-chip--active",
                          )}
                          aria-current={activeResultSection === "result-panel-subtitle" ? "true" : undefined}
                          onClick={() => scrollToPanel("result-panel-subtitle")}
                        >
                          <StepsIcon className="h-3.5 w-3.5" />
                          字幕工作台
                        </button>
                      ) : null}
                      {showStepsPanel ? (
                        <button
                          type="button"
                          className={cn(
                            "result-overview-chip result-overview-chip--link",
                            activeResultSection === "result-panel-steps" && "result-overview-chip--active",
                          )}
                          aria-current={activeResultSection === "result-panel-steps" ? "true" : undefined}
                          onClick={() => scrollToPanel("result-panel-steps")}
                        >
                          <StepsIcon className="h-3.5 w-3.5" />
                          步骤 {singleResultSteps.length}
                        </button>
                      ) : null}
                      {hasDocumentPanel ? (
                        <button
                          type="button"
                          className={cn(
                            "result-overview-chip result-overview-chip--link",
                            activeResultSection === "result-panel-document" && "result-overview-chip--active",
                          )}
                          aria-current={activeResultSection === "result-panel-document" ? "true" : undefined}
                          onClick={() => scrollToPanel("result-panel-document")}
                        >
                          <DocumentIcon className="h-3.5 w-3.5" />
                          总结文档
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </section>
                {hasBatchResult && batchResultData ? (
                  <BatchResultPanel
                    data={batchResultData}
                    retrying={submittingTask}
                    onDownloadAll={() => void downloadBatchZip()}
                    onDownloadItem={(outputDir, filename) =>
                      void downloadSingleFromBatch(outputDir, filename)
                    }
                    onOpenItem={(item) => void openBatchResultItem(item)}
                    onRetryFailed={() => void retryFailedBatchItems()}
                    onRetryItem={(item) => void retryFailedBatchItem(item)}
                  />
                ) : null}

                {hasSingleResult && resultData ? (
                  <div className={cn("result-trio", hasSubtitlePanel && "result-trio--split")}>
                    {hasSubtitlePanel ? (
                      <div id="result-panel-subtitle" className="result-trio-aside result-anchor">
                        <SubtitlePanel
                          resultData={resultData}
                          subtitleWorkbench={subtitleWorkbench}
                          subtitleLines={subtitleLines}
                          filteredSubtitleLines={filteredSubtitleLines}
                          subtitleKeyword={subtitleKeyword}
                          subtitleLoading={subtitleLoading}
                          subtitleRefreshing={subtitleRefreshing}
                          subtitleLoadError={subtitleLoadError}
                          subtitleAssetAvailable={subtitleAssetAvailable}
                          videoRef={subtitleVideoRef}
                          onKeywordChange={setSubtitleKeyword}
                          onRefresh={() => void refreshSubtitleWorkbench()}
                          onDownload={() => void downloadSubtitleZip()}
                          onSeek={seekVideoTo}
                          formatDisplayTime={formatSubtitleDisplayTime}
                        />
                      </div>
                    ) : null}

                    <div className="result-trio-main space-y-4">
                      {showStepsPanel ? (
                        <div id="result-panel-steps" className="result-anchor">
                          <StepsPanel
                            resultData={resultData}
                            steps={singleResultSteps}
                            isEditMode={isEditMode}
                            editedSteps={editedSteps}
                            savingSteps={savingSteps}
                            dragIndex={dragIndex}
                            dragOverIndex={dragOverIndex}
                            setEditedSteps={setEditedSteps}
                            setIsEditMode={setIsEditMode}
                            setDragIndex={setDragIndex}
                            setDragOverIndex={setDragOverIndex}
                            onShowError={showError}
                            onSave={() => void saveEditedSteps()}
                            onSeek={hasSubtitlePanel ? seekVideoTo : undefined}
                          />
                        </div>
                      ) : null}

                      {hasDocumentPanel ? (
                        <div id="result-panel-document" className="result-anchor">
                          <DocumentPanel
                            html={renderedMarkdown}
                            outputTemplate={resultData.output_template || "operation_guide"}
                            onDownloadZip={() => void downloadSingleZip()}
                            onCopyMarkdown={copyMarkdownSource}
                            onCopyText={copyPlainText}
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </main>

      {isResultView ? (
        <button
          type="button"
          aria-label="返回结果顶部"
          title="返回顶部"
          className={cn("back-to-top-btn", showBackToTop && "back-to-top-btn--visible")}
          onClick={() => {
            if (resultsRef.current) {
              resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
            } else if (typeof window !== "undefined") {
              window.scrollTo({ top: 0, behavior: uiScrollBehavior });
            }
          }}
        >
          <svg viewBox="0 0 24 24" fill="none" className="h-4 w-4" aria-hidden="true">
            <path d="M12 19V6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
            <path d="M6 11l6-6 6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span>顶部</span>
        </button>
      ) : null}

      {typeof document !== "undefined"
        ? createPortal(
            <div
              className="history-drawer-overlay fixed inset-0 z-[45]"
              hidden={!historyDrawerOpen}
              aria-hidden={!historyDrawerOpen}
            >
              <button
                type="button"
                aria-label="关闭历史侧边栏"
                className="history-drawer-backdrop absolute inset-0 bg-black/45"
                onClick={() => setHistoryDrawerOpen(false)}
              />
              <div className="pointer-events-none relative h-full w-full">
                <aside
                  id="history-drawer"
                  className="history-drawer-panel pointer-events-auto ml-auto flex h-full w-[min(92vw,360px)] flex-col border-l border-neutral-700/80 bg-neutral-900/97 py-4 shadow-[-16px_0_34px_rgba(2,6,23,0.45)]"
                >
                  <div className="border-b border-neutral-800 px-4 pb-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <HistoryIcon className="h-4 w-4 text-neutral-300" />
                        <h2 className="text-base font-semibold">历史记录</h2>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-rose-400/60 hover:text-rose-200 disabled:cursor-not-allowed disabled:opacity-60"
                          onClick={openClearHistoryConfirm}
                          disabled={clearingHistory || loadingHistory || history.length === 0}
                        >
                          {clearingHistory ? "清空中..." : "清空全部"}
                        </button>
                        <button
                          type="button"
                          title="关闭侧边栏"
                          aria-label="关闭侧边栏"
                          className="inline-flex h-8 w-8 items-center justify-center rounded border border-neutral-700 text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100"
                          onClick={() => setHistoryDrawerOpen(false)}
                        >
                          <CloseIcon className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </div>
                    <p className="history-retention-note mt-2 rounded border border-amber-400/35 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200/95">
                      提醒：历史记录生成的总结文件仅保留 72 小时。
                    </p>
                  </div>
                  <VirtualizedHistoryList
                    active={historyDrawerOpen}
                    history={history}
                    clearingHistory={clearingHistory}
                    deletingHistoryId={deletingHistoryId}
                    onOpenRecord={handleOpenHistoryRecord}
                    onDeleteRecord={handleDeleteHistoryRecord}
                  />
                  <div className="border-t border-neutral-800 px-4 pt-3">
                    <button
                      type="button"
                      className="history-refresh-btn flex w-full items-center justify-center gap-1 rounded-lg border border-neutral-700 px-2.5 py-2 text-xs font-medium"
                      disabled={loadingHistory}
                      aria-busy={loadingHistory}
                      onClick={() => void loadHistory()}
                    >
                      <RefreshIcon className={`h-3.5 w-3.5 ${loadingHistory ? "history-refresh-icon-spin" : ""}`} />
                      {loadingHistory ? "刷新中..." : "刷新"}
                    </button>
                  </div>
                </aside>
              </div>
            </div>,
            document.body,
          )
        : null}

      {showClearHistoryConfirm && typeof document !== "undefined"
        ? createPortal(
            <div className="progress-overlay-anim fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4">
              <button
                type="button"
                className="absolute inset-0"
                aria-label="关闭清空历史确认"
                onClick={closeClearHistoryConfirm}
                disabled={clearingHistory}
              />
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="clear-history-confirm-title"
                className="progress-dialog-anim relative z-10 w-full max-w-sm rounded-xl border border-neutral-700 bg-neutral-900/96 p-4 shadow-[0_18px_36px_rgba(2,6,23,0.45)]"
              >
                <div className="mb-3 flex items-center gap-2">
                  <ClearIcon className="h-4 w-4 text-rose-300" />
                  <h3 id="clear-history-confirm-title" className="text-sm font-semibold text-neutral-100">
                    确认清空全部历史记录？
                  </h3>
                </div>
                <p className="text-sm text-neutral-300">该操作不可撤销，历史中的分析结果入口将被移除。</p>
                <div className="mt-4 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={closeClearHistoryConfirm}
                    disabled={clearingHistory}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="rounded border border-rose-500/60 bg-rose-500/15 px-3 py-1.5 text-xs text-rose-200 transition-colors hover:border-rose-400 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void clearAllHistoryRecords()}
                    disabled={clearingHistory}
                  >
                    {clearingHistory ? "清空中..." : "确认清空"}
                  </button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {pendingDeleteHistory && typeof document !== "undefined"
        ? createPortal(
            <div className="progress-overlay-anim fixed inset-0 z-[60] flex items-center justify-center bg-black/55 p-4">
              <button
                type="button"
                className="absolute inset-0"
                aria-label="关闭删除历史确认"
                onClick={closeDeleteHistoryConfirm}
                disabled={Boolean(deletingHistoryId)}
              />
              <div
                role="dialog"
                aria-modal="true"
                aria-labelledby="delete-history-confirm-title"
                className="progress-dialog-anim relative z-10 w-full max-w-sm rounded-xl border border-neutral-700 bg-neutral-900/96 p-4 shadow-[0_18px_36px_rgba(2,6,23,0.45)]"
              >
                <div className="mb-3 flex items-center gap-2">
                  <TrashIcon className="h-4 w-4 text-rose-300" />
                  <h3 id="delete-history-confirm-title" className="text-sm font-semibold text-neutral-100">
                    确认删除这条历史记录？
                  </h3>
                </div>
                <p className="text-sm text-neutral-300">删除后将无法通过历史列表快速找回该结果。</p>
                <p className="history-delete-record-name mt-2 rounded bg-neutral-900/96 px-2 py-1 text-center text-xs text-neutral-300 break-all">
                  {pendingDeleteHistory.video_name || "未命名记录"}
                </p>
                <div className="mt-4 flex items-center justify-end gap-2">
                  <button
                    type="button"
                    className="rounded border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={closeDeleteHistoryConfirm}
                    disabled={Boolean(deletingHistoryId)}
                  >
                    取消
                  </button>
                  <button
                    type="button"
                    className="rounded border border-rose-500/60 bg-rose-500/15 px-3 py-1.5 text-xs text-rose-200 transition-colors hover:border-rose-400 hover:bg-rose-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                    onClick={() => void removeHistoryRecord()}
                    disabled={Boolean(deletingHistoryId)}
                  >
                    {deletingHistoryId ? "删除中..." : "确认删除"}
                  </button>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}

      {progressVisible ? (
        <div className="progress-overlay-anim fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div className="progress-dialog-anim vi-progress-card">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-base font-semibold text-neutral-50">{progressTitle}</h3>
              <span className="vi-status vi-status--run">{progressPercent}%</span>
            </div>
            <p className="mt-1 text-sm text-neutral-300">{progressText}</p>
            <div className="mt-4">
              <div className="mb-1.5 flex items-center justify-between text-xs text-neutral-400">
                <span>{progressModeText}</span>
                {progressBoard.total > 0 ? (
                  <span>{progressBoard.current}/{progressBoard.total}</span>
                ) : null}
              </div>
              <div className="vi-progress-track">
                <div className="vi-progress-bar" style={{ width: `${progressPercent}%` }} />
              </div>
            </div>
            <div className="mt-3 grid gap-1 text-xs text-neutral-400">
              {progressBoard.success > 0 || progressBoard.failed > 0 ? (
                <p>成功 <span className="text-emerald-300">{progressBoard.success}</span> · 失败 <span className="text-rose-300">{progressBoard.failed}</span></p>
              ) : null}
              <p>
                阶段: {progressBoard.stage && progressBoard.stage !== "idle"
                  ? STAGE_LABELS[progressBoard.stage] || progressBoard.stage
                  : "正在准备分析..."}
              </p>
              {progressBoard.currentFile ? (
                <p className="truncate text-teal-300">当前文件: {progressBoard.currentFile}</p>
              ) : null}
            </div>
          </div>
        </div>
      ) : null}

      {showErrorToast && typeof document !== "undefined"
        ? createPortal(
            <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
              <div className="toast-anim pointer-events-auto w-[min(92vw,560px)] rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-center text-sm text-red-200">
                {errorMessage}
              </div>
            </div>,
            document.body,
          )
        : null}

      {showSuccessToast && typeof document !== "undefined"
        ? createPortal(
            <div className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex justify-center px-4">
              <div className="toast-anim pointer-events-auto w-[min(92vw,560px)] rounded border border-emerald-400/40 bg-emerald-500/10 px-4 py-3 text-center text-sm text-emerald-200">
                {successMessage}
              </div>
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}
