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
  CONTENT_POLICY_BLOCK_MESSAGE,
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
  STAGE_PERCENT,
  UPLOAD_RESUME_KEY_PREFIX,
  USER_SETTINGS_STORAGE_KEY_PREFIX,
  THEME_STORAGE_KEY,
  VALID_VIDEO_EXTENSIONS,
  WEB_SEARCH_ACTIVATION_URL,
  WEB_SEARCH_ERROR_HINTS,
  WHISPER_MODEL_VALUES,
} from "./constants/app";
import type {
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
import {
  basename,
  buildModelConfigSignature,
  clampNumber,
  clone,
  createHistoryClientId,
  getOrCreateHistoryClientId,
  isSameProgressBoard,
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
void CONTENT_POLICY_BLOCK_MESSAGE;
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
void STAGE_PERCENT;
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
void isSameProgressBoard;
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
  PersistedUserSettings,
  ProgressBoard,
  RiskResult,
  SegmentPolicy,
  SingleResultData,
  StepItem,
  SubtitleLine,
  SubtitleWorkbenchData,
};

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
  const [maxVision] = useState(10);
  const [webSearch, setWebSearch] = useState(false);
  const [summaryOnly] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [importingUrl, setImportingUrl] = useState(false);

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [savingSteps, setSavingSteps] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [deletingHistoryId, setDeletingHistoryId] = useState("");
  const [pendingDeleteHistory, setPendingDeleteHistory] = useState<HistoryItem | null>(null);
  const [showClearHistoryConfirm, setShowClearHistoryConfirm] = useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);

  const [batchFiles, setBatchFiles] = useState<BatchFileItem[]>([]);
  const [resultData, setResultData] = useState<SingleResultData | null>(null);
  const [batchResultData, setBatchResultData] = useState<BatchResultData | null>(null);
  const [savedBatchResult, setSavedBatchResult] = useState<BatchResultData | null>(null);
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
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const singleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressVisibleRef = useRef(false);
  const batchFilesRef = useRef<BatchFileItem[]>([]);
  const pendingFileSeqRef = useRef(0);
  const subtitleVideoRef = useRef<HTMLVideoElement | null>(null);
  const progressPollIntervalMs = mobilePerfMode
    ? PROGRESS_POLL_INTERVAL_MOBILE_MS
    : PROGRESS_POLL_INTERVAL_DESKTOP_MS;
  const uiScrollBehavior: ScrollBehavior = mobilePerfMode ? "auto" : "smooth";

  useEffect(() => {
    progressVisibleRef.current = progressVisible;
  }, [progressVisible]);

  useEffect(() => {
    batchFilesRef.current = batchFiles;
  }, [batchFiles]);

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
    return () => {
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (successTimerRef.current) clearTimeout(successTimerRef.current);
      if (batchTimerRef.current) clearInterval(batchTimerRef.current);
      if (singleTimerRef.current) clearInterval(singleTimerRef.current);
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

  const updateProgressBoard = useCallback((patch: Partial<ProgressBoard>) => {
    setProgressBoard((prev) => {
      const next = { ...prev, ...patch };
      next.percent = Math.max(0, Math.min(100, Number(next.percent) || 0));
      next.total = Math.max(0, Number(next.total) || 0);
      next.current = Math.max(0, Number(next.current) || 0);
      next.success = Math.max(0, Number(next.success) || 0);
      next.failed = Math.max(0, Number(next.failed) || 0);
      return isSameProgressBoard(prev, next) ? prev : next;
    });
  }, []);

  const getStageProgress = useCallback((stage: string) => STAGE_PERCENT[String(stage || "").toLowerCase()] || 0, []);

  const countBatchStatus = useCallback(() => {
    let success = 0;
    let failed = 0;
    batchFilesRef.current.forEach((item) => {
      if (!item.filepath) return;
      if (item.status === "success") success += 1;
      if (item.status === "failed") failed += 1;
    });
    return { success, failed };
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

  const stopBatchPolling = useCallback(() => {
    if (!batchTimerRef.current) return;
    clearInterval(batchTimerRef.current);
    batchTimerRef.current = null;
  }, []);

  const stopSinglePolling = useCallback(() => {
    if (!singleTimerRef.current) return;
    clearInterval(singleTimerRef.current);
    singleTimerRef.current = null;
  }, []);

  const pullSingleProgress = useCallback(async () => {
    try {
      const progress = await fetchJson<{ current_file?: string; status?: string; stage?: string; message?: string }>(
        "/single_progress",
      );
      const stage = String(progress.stage || "").toLowerCase();
      const status = String(progress.status || "").toLowerCase();
      const done = status === "completed" || stage === "done";
      const failed = status === "failed" || stage === "failed";
      if (progressVisibleRef.current) {
        setProgressTextIfChanged(String(progress.message || "正在分析视频..."));
      }
      updateProgressBoard({
        mode: "single",
        stage,
        percent: done || failed ? 100 : getStageProgress(stage),
        total: 1,
        current: done || failed ? 1 : 0,
        success: done ? 1 : 0,
        failed: failed ? 1 : 0,
        currentFile: String(progress.current_file || ""),
      });
    } catch {
      // ignore polling errors
    }
  }, [fetchJson, getStageProgress, setProgressTextIfChanged, updateProgressBoard]);

  const pullBatchProgress = useCallback(async () => {
    try {
      const progress = await fetchJson<{
        current_file?: string;
        status?: string;
        stage?: string;
        total?: number;
        current?: number;
        message?: string;
      }>("/batch_progress");
      const stage = String(progress.stage || "").toLowerCase();
      const status = String(progress.status || "").toLowerCase();
      const currentFile = String(progress.current_file || "");
      const total = Number(progress.total) || getAnalyzableBatchFiles().length;
      const current = Number(progress.current) || 0;
      const { success, failed } = countBatchStatus();
      let percent = 0;
      if (total > 0) {
        const doneFiles = Math.max(0, current - 1);
        percent = ((doneFiles + getStageProgress(stage) / 100) / total) * 100;
      }
      if (status === "completed" || stage === "done") {
        percent = 100;
      } else {
        percent = Math.min(99, percent);
      }
      if (progressVisibleRef.current) setProgressTextIfChanged(String(progress.message || "正在批量分析..."));
      updateProgressBoard({
        mode: "batch",
        stage,
        percent,
        total,
        current,
        success,
        failed,
        currentFile,
      });

      if (currentFile) {
        setBatchFiles((prev) => {
          let changed = false;
          const next: BatchFileItem[] = prev.map((item): BatchFileItem => {
            if (item.status === "success" || item.status === "failed") {
              return item;
            }
            if (item.filename === currentFile && item.status !== "processing") {
              changed = true;
              return { ...item, status: "processing" as FileStatus };
            }
            return item;
          });
          return changed ? next : prev;
        });
      }
    } catch {
      // ignore polling errors
    }
  }, [countBatchStatus, fetchJson, getAnalyzableBatchFiles, getStageProgress, setProgressTextIfChanged, updateProgressBoard]);

  const startSinglePolling = useCallback(() => {
    stopSinglePolling();
    void pullSingleProgress();
    singleTimerRef.current = setInterval(() => void pullSingleProgress(), progressPollIntervalMs);
  }, [progressPollIntervalMs, pullSingleProgress, stopSinglePolling]);

  const startBatchPolling = useCallback(() => {
    stopBatchPolling();
    void pullBatchProgress();
    batchTimerRef.current = setInterval(() => void pullBatchProgress(), progressPollIntervalMs);
  }, [progressPollIntervalMs, pullBatchProgress, stopBatchPolling]);

  useEffect(() => {
    if (singleTimerRef.current) startSinglePolling();
    if (batchTimerRef.current) startBatchPolling();
  }, [progressPollIntervalMs, startBatchPolling, startSinglePolling]);

  const uploadSingleFileWithResume = useCallback(
    async (
      file: File,
      fileIndex: number,
      totalFiles: number,
      onSafetyCheckStart?: (currentFile: File, currentIndex: number, total: number) => void,
    ) => {
      const resumeKey = `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`;
      const storedUploadId = window.localStorage.getItem(resumeKey) || "";
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
      });
      const uploadId = String(initData.upload_id || "");
      if (!uploadId) throw new Error("初始化上传失败");
      window.localStorage.setItem(resumeKey, uploadId);

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
        await fetchJson("/upload_chunk", { method: "POST", body: formData });
      }

      onSafetyCheckStart?.(file, fileIndex, totalFiles);
      const finalized = await fetchJson<{ filename: string; filepath: string }>("/upload_chunk_finalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId }),
      });
      window.localStorage.removeItem(resumeKey);
      return finalized;
    },
    [fetchJson],
  );

  const uploadBatchFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList || []).filter((file) => isValidVideo(file.name));
      if (files.length === 0) {
        showError("没有可用的视频文件");
        return;
      }

      const readyForUpload = await verifyModelConnectionForUpload();
      if (!readyForUpload) return;

      const placeholders = files.map((file) => ({
        filename: file.name,
        filepath: "",
        status: "processing" as FileStatus,
        error: "等待上传...",
        clientId: nextPendingFileId("upload"),
      }));
      setBatchFiles((prev) => [...prev, ...placeholders]);
      try {
        let uploadedFailed = 0;
        for (let i = 0; i < files.length; i += 1) {
          const currentFile = files[i];
          const placeholder = placeholders[i];
          try {
            replaceBatchFileByClientId(placeholder.clientId || "", {
              ...placeholder,
              error: `正在上传（${i + 1}/${files.length}）...`,
            });
            const item = await uploadSingleFileWithResume(
              currentFile,
              i + 1,
              files.length,
              (processingFile, currentIndex, total) => {
                replaceBatchFileByClientId(placeholder.clientId || "", {
                  ...placeholder,
                  filename: processingFile.name,
                  error: `正在保存视频（${currentIndex}/${total}）...`,
                });
              },
            );
            replaceBatchFileByClientId(placeholder.clientId || "", {
              filename: item.filename,
              filepath: item.filepath,
              status: "pending",
              error: "",
              clientId: placeholder.clientId,
            });
          } catch (error) {
            const apiError = error instanceof ApiRequestError ? error : null;
            let message = String((error as Error).message || error || "上传失败");
            if (apiError?.payload?.code === "content_policy_violation") {
              message = formatContentPolicyViolationMessage("");
            } else if (apiError?.payload?.error) {
              message = String(apiError.payload.error);
            }
            const segmentHint = formatSegmentPolicyHint(apiError?.payload?.segment_policy);
            if (segmentHint) message = [message, segmentHint].filter(Boolean).join(" | ");
            replaceBatchFileByClientId(placeholder.clientId || "", {
              filename: currentFile.name,
              filepath: "",
              status: "failed",
              error: formatInlineErrorMessage(message),
              clientId: placeholder.clientId,
            });
            uploadedFailed += 1;
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
  const analyzeByUploadedFile = useCallback(async (file: BatchFileItem) => {
    setBatchFiles((prev) =>
      prev.map((item) =>
        item.filepath
          ? {
              ...item,
              status: item.filepath === file.filepath ? ("processing" as FileStatus) : item.status,
              error: item.filepath === file.filepath ? (summaryOnly ? "正在生成摘要版..." : "正在分析视频...") : "",
            }
          : item,
      ),
    );
    stopBatchPolling();
    setIsAnalyzing(true);
    hideProgress();
    updateProgressBoard({ mode: "single", stage: "prepare", total: 1, percent: 5, currentFile: file.filename });
    startSinglePolling();
    let reveal = false;
    try {
      const data = await fetchJson<SingleResultData>("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filepath: file.filepath,
        }),
      });
      setResultData(data);
      setBatchResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
      setActiveResultTab("steps");
      setView("result");
      if (data?.fallback_used) {
        showSuccess(String(data.analysis_note || "未识别到标准步骤，已自动生成候选内容。"));
      }
      setBatchFiles((prev) =>
        prev.map((item) =>
          item.filepath === file.filepath ? { ...item, status: "success", error: "" } : item,
        ),
      );
      updateProgressBoard({
        mode: "single",
        stage: "done",
        total: 1,
        current: 1,
        success: 1,
        failed: 0,
        currentFile: file.filename,
        percent: 100,
      });
      reveal = true;
      await loadHistory();
    } catch (error) {
      const apiError = error instanceof ApiRequestError ? error : null;
      if (apiError?.payload?.code === "content_policy_violation") {
        const blockedNotice = apiError.payload.blocked_notice || {
          title: "安全检测未通过（已拦截）",
          risk_level: String(apiError.payload.risk?.risk_level || "high"),
          reason_code: String(apiError.payload.risk?.reason_code || "CONTENT_POLICY_VIOLATION"),
          reason: String(apiError.payload.risk?.reason || CONTENT_POLICY_BLOCK_MESSAGE),
          suggestions: ["删除敏感片段后重新上传检测。"],
          retry_guidance: "请整改后重试。",
        };
        setResultData({
          steps: [],
          markdown: "",
          output_dir: "",
          pdf_path: "",
          result_mode: "blocked_notice",
          fallback_used: false,
          analysis_note: String(apiError.payload.analysis_note || "已生成安全检测说明卡。"),
          quality_score: Number(apiError.payload.quality_score || 0),
          degrade_reason: String(apiError.payload.degrade_reason || "content_policy_blocked"),
          blocked_notice: blockedNotice,
          risk: apiError.payload.risk,
        });
        setBatchResultData(null);
        setIsEditMode(false);
        setEditedSteps([]);
        setActiveResultTab("steps");
        setView("result");
        setBatchFiles((prev) =>
          prev.map((item) =>
            item.filepath === file.filepath ? { ...item, status: "failed", error: "安全检测未通过" } : item,
          ),
        );
        updateProgressBoard({
          mode: "single",
          stage: "done",
          total: 1,
          current: 1,
          success: 0,
          failed: 1,
          currentFile: file.filename,
          percent: 100,
        });
        showSuccess("安全检测未通过，已生成检测结果说明卡。");
        reveal = true;
        return;
      }
      const message = String((error as Error).message || error);
      if (WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint))) setWebSearch(false);
      setBatchFiles((prev) =>
        prev.map((item) =>
          item.filepath === file.filepath ? { ...item, status: "failed", error: message } : item,
        ),
      );
      updateProgressBoard({
        mode: "single",
        stage: "failed",
        total: 1,
        current: 1,
        success: 0,
        failed: 1,
        currentFile: file.filename,
        percent: 100,
      });
      showError(`单文件分析失败: ${message}`);
    } finally {
      stopSinglePolling();
      setIsAnalyzing(false);
      hideProgress();
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
    }
  }, [
    fetchJson,
    hideProgress,
    loadHistory,
    maxVision,
    showError,
    showSuccess,
    startSinglePolling,
    stopBatchPolling,
    stopSinglePolling,
    summaryOnly,
    uiScrollBehavior,
    updateProgressBoard,
    webSearch,
  ]);

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
      error: "正在导入链接视频...",
      clientId,
    };
    setBatchFiles((prev) => [placeholder, ...prev]);
    setImportingUrl(true);
    stopBatchPolling();
    stopSinglePolling();
    setIsAnalyzing(true);

    try {
      const uploadedItem = await uploadBySourceUrl(urls[0]);
      replaceBatchFileByClientId(clientId, { ...uploadedItem, clientId });
      setSourceUrl("");
      await analyzeByUploadedFile(uploadedItem);
    } catch (error) {
      const message = `链接分析失败: ${String((error as Error).message || error)}`;
      replaceBatchFileByClientId(clientId, {
        ...placeholder,
        status: "failed",
        error: formatInlineErrorMessage(message),
      });
      showError(message);
      hideProgress();
      setIsAnalyzing(false);
    } finally {
      setImportingUrl(false);
    }
  }, [
    analyzeByUploadedFile,
    guessUrlVideoName,
    hideProgress,
    nextPendingFileId,
    replaceBatchFileByClientId,
    showError,
    sourceUrl,
    stopBatchPolling,
    stopSinglePolling,
    uploadBySourceUrl,
    verifyModelConnectionForUpload,
  ]);

  const analyzeBatch = useCallback(async () => {
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length <= 1) return;
    setBatchFiles((prev) =>
      prev.map((item) => (item.filepath ? { ...item, status: "processing", error: "正在等待批量分析..." } : item)),
    );
    stopSinglePolling();
    setIsAnalyzing(true);
    hideProgress();
    updateProgressBoard({ mode: "batch", stage: "prepare", total: analyzableFiles.length, percent: 0 });
    startBatchPolling();
    let reveal = false;
    try {
      const data = await fetchJson<BatchResultData>("/analyze_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filepaths: analyzableFiles.map((item) => item.filepath),
        }),
      });
      setBatchResultData(data);
      setResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
      setView("result");
      let resultIndex = 0;
      const nextFiles: BatchFileItem[] = batchFilesRef.current.map((item) => {
        if (!item.filepath) return item;
        const result = data.results?.[resultIndex];
        resultIndex += 1;
        const base = String(result?.error || "");
        const riskHint = formatRiskHint(result?.risk);
        const codeText = result?.code ? `code=${result.code}` : "";
        return {
          ...item,
          status: result?.success ? "success" : "failed",
          error: [base, codeText, riskHint].filter(Boolean).join(" | "),
        };
      });
      setBatchFiles(nextFiles);
      const success = nextFiles.filter((item) => item.filepath && item.status === "success").length;
      const failed = nextFiles.filter((item) => item.filepath && item.status === "failed").length;
      updateProgressBoard({
        mode: "batch",
        stage: "done",
        total: Number(data?.summary?.total) || analyzableFiles.length,
        current: Number(data?.summary?.total) || analyzableFiles.length,
        success: Number(data?.summary?.success) || success,
        failed: Number(data?.summary?.failed) || failed,
        currentFile: "",
        percent: 100,
      });
      reveal = true;
      await loadHistory();
    } catch (error) {
      const message = String((error as Error).message || error);
      if (WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint))) setWebSearch(false);
      const { success, failed } = countBatchStatus();
      updateProgressBoard({
        mode: "batch",
        stage: "failed",
        total: analyzableFiles.length,
        current: success + failed,
        success,
        failed,
        percent: 100,
      });
      showError(`批量分析失败: ${message}`);
    } finally {
      stopBatchPolling();
      setIsAnalyzing(false);
      hideProgress();
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
    }
  }, [
    fetchJson,
    hideProgress,
    loadHistory,
    maxVision,
    countBatchStatus,
    showError,
    startBatchPolling,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    uiScrollBehavior,
    webSearch,
    getAnalyzableBatchFiles,
    summaryOnly,
  ]);

  const startAnalyze = useCallback(async () => {
    setSavedBatchResult(null);
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

  const openHistoryRecord = useCallback(
    async (recordId: string) => {
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
        setBatchResultData(null);
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
    [fetchJson, hideProgress, showError, showProgress, uiScrollBehavior],
  );

  const openBatchResultItem = useCallback(
    async (item: BatchResultItem) => {
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
        setBatchResultData(null);
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
    [batchResultData, hideProgress, showError, showProgress, uiScrollBehavior, withHistoryClientHeader],
  );

  const returnToBatchResult = useCallback(() => {
    if (!savedBatchResult) return;
    setBatchResultData(savedBatchResult);
    setSavedBatchResult(null);
    setResultData(null);
    setIsEditMode(false);
    setEditedSteps([]);
    if (resultsRef.current) {
      resultsRef.current.scrollIntoView({ behavior: uiScrollBehavior, block: "start" });
    } else if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: uiScrollBehavior });
    }
  }, [savedBatchResult, uiScrollBehavior]);

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
  }, [editedSteps, fetchJson, hideProgress, resultData?.output_dir, showError, showProgress]);

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
        : status === "processing"
          ? "正在准备文件"
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
  const hasSourceUrlInput = useMemo(() => parseSourceUrls(sourceUrl).length > 0, [sourceUrl]);
  const canAnalyze = !isAnalyzing && (analyzableBatchCount > 0 || hasSourceUrlInput);
  const analyzeButtonText = isAnalyzing
    ? analyzableBatchCount === 1
      ? "单文件处理中..."
      : "批量处理中..."
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
    setView("upload");
    setSavedBatchResult(null);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: uiScrollBehavior });
    }
  }, [uiScrollBehavior]);
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
      className="start-analyze-btn h-full w-full cursor-pointer rounded-full bg-linear-to-r from-neutral-950 via-black to-neutral-900 px-4 py-2 text-neutral-100 shadow-[0px_1px_0px_0px_rgba(255,255,255,0.09)_inset,0px_0.5px_1px_0px_rgba(148,163,184,0.32)] transition-all duration-150 active:scale-98 disabled:cursor-not-allowed disabled:opacity-60"
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
                      disabled={isAnalyzing || importingUrl}
                      onClick={() => void analyzeBySourceUrl()}
                    >
                      {importingUrl ? "处理中..." : "链接直达分析"}
                    </button>
                  </div>
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
                      item.status === "success" && "vi-batch-row--ok",
                    )}
                  >
                    <div className="min-w-0 flex flex-1 items-start gap-2.5">
                      <FileVideoIcon
                        className={cn(
                          "mt-0.5 h-4 w-4 shrink-0 text-neutral-400 transition-colors",
                          item.status === "success" && "text-emerald-300",
                          item.status === "failed" && "text-rose-300",
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
                      ) : item.status === "processing" ? (
                        <span className="vi-inline-spinner" aria-label="处理中" />
                      ) : (
                        <span className="vi-status">待处理</span>
                      )}
                      {batchFiles.length > 1 ? (
                        <button
                          type="button"
                          title="删除文件"
                          aria-label="删除文件"
                          className="vi-icon-btn vi-icon-btn--danger"
                          disabled={isAnalyzing}
                          onClick={() => setBatchFiles((prev) => prev.filter((_, i) => i !== index))}
                        >
                          <TrashIcon />
                        </button>
                      ) : null}
                    </div>
                  </div>
                ))}
              </div>
              {batchFiles.length > 0 ? (
                <button
                  type="button"
                  className="vi-btn vi-btn--block vi-btn--sm mt-2"
                  disabled={isAnalyzing}
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
                    onDownloadAll={() => void downloadBatchZip()}
                    onDownloadItem={(outputDir, filename) =>
                      void downloadSingleFromBatch(outputDir, filename)
                    }
                    onOpenItem={(item) => void openBatchResultItem(item)}
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
                            summaryOnly={summaryOnly}
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
                <p className="mt-2 rounded bg-neutral-900/96 px-2 py-1 text-center text-xs text-neutral-300 break-all">
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
