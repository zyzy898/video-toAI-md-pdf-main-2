import DOMPurify from "dompurify";
import { marked } from "marked";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BackgroundBeams } from "@/components/ui/background-beams";
import { CanvasText } from "@/components/ui/canvas-text";
import { NoiseBackground } from "@/components/ui/noise-background";
import { cn } from "@/lib/utils";

import {
  ALIYUN_APIKEY_DOC_URL,
  ANALYZE_BUTTON_GRADIENT_COLORS,
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
  PlayIcon,
  RefreshIcon,
  SettingsIcon,
  StackIcon,
  StatusFailedIcon,
  StatusSuccessIcon,
  StepsIcon,
  TrashIcon,
  UploadIcon,
} from "./components/icons";
import { MarkdownPreview } from "./components/MarkdownPreview";
import { ReadonlyStepsList } from "./components/ReadonlyStepsList";
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
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [modelPreset, setModelPreset] = useState<ModelPreset>("ark");
  const [modelName, setModelName] = useState("");
  const [modelBaseUrl, setModelBaseUrl] = useState("https://ark.cn-beijing.volces.com/api/v3");
  const [whisperModel, setWhisperModel] = useState("base");
  const [maxVision, setMaxVision] = useState(10);
  const [useVideo, setUseVideo] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [fps, setFps] = useState(1);
  const [summaryOnly, setSummaryOnly] = useState(false);
  const [sourceUrl, setSourceUrl] = useState("");
  const [importingUrl, setImportingUrl] = useState(false);

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [savingSteps, setSavingSteps] = useState(false);
  const [, setTestingModel] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [deletingHistoryId, setDeletingHistoryId] = useState("");
  const [pendingDeleteHistory, setPendingDeleteHistory] = useState<HistoryItem | null>(null);
  const [showClearHistoryConfirm, setShowClearHistoryConfirm] = useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [settingsDrawerOpen, setSettingsDrawerOpen] = useState(false);
  const [apiKeyGuideActive, setApiKeyGuideActive] = useState(false);
  const [modelConfigGuideActive, setModelConfigGuideActive] = useState(false);
  const [, setModelTestGuideActive] = useState(false);

  const [batchFiles, setBatchFiles] = useState<BatchFileItem[]>([]);
  const [resultData, setResultData] = useState<SingleResultData | null>(null);
  const [batchResultData, setBatchResultData] = useState<BatchResultData | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [subtitleWorkbench, setSubtitleWorkbench] = useState<SubtitleWorkbenchData | null>(null);
  const [subtitleLoading, setSubtitleLoading] = useState(false);
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
  const apiKeyInputRef = useRef<HTMLInputElement | null>(null);
  const modelBaseUrlInputRef = useRef<HTMLInputElement | null>(null);
  const modelNameInputRef = useRef<HTMLInputElement | null>(null);
  const modelTestButtonRef = useRef<HTMLButtonElement | null>(null);
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const apiKeyGuideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const apiKeyGuideFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelConfigGuideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelConfigGuideFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelTestGuideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const modelTestGuideFocusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const singleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressVisibleRef = useRef(false);
  const batchFilesRef = useRef<BatchFileItem[]>([]);
  const verifiedModelConfigSignatureRef = useRef("");
  const userSettingsStorageKeyRef = useRef("");
  const [userSettingsLoaded, setUserSettingsLoaded] = useState(false);
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

  useEffect(() => {
    if (typeof window === "undefined") return;

    const clientId = getOrCreateHistoryClientId() || "anonymous";
    const storageKey = `${USER_SETTINGS_STORAGE_KEY_PREFIX}:${clientId}`;
    userSettingsStorageKeyRef.current = storageKey;
    try {
      const raw = window.localStorage.getItem(storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as PersistedUserSettings;
      if (!parsed || typeof parsed !== "object") return;

      const presetText = String(parsed.modelPreset || "").trim().toLowerCase();
      if (MODEL_PRESET_VALUES.includes(presetText as ModelPreset)) {
        setModelPreset(presetText as ModelPreset);
      }

      const whisperText = String(parsed.whisperModel || "").trim().toLowerCase();
      if (WHISPER_MODEL_VALUES.has(whisperText)) {
        setWhisperModel(whisperText);
      }

      setApiKey(safeString(parsed.apiKey, 500, ""));
      setModelName(safeString(parsed.modelName, 200, ""));
      setModelBaseUrl(safeString(parsed.modelBaseUrl, 300, "https://ark.cn-beijing.volces.com/api/v3"));
      setMaxVision(Math.round(clampNumber(parsed.maxVision, 10, MAX_VISION_MIN, MAX_VISION_MAX)));
      setFps(Number(clampNumber(parsed.fps, 1, FPS_MIN, FPS_MAX).toFixed(1)));

      if (typeof parsed.useVideo === "boolean") setUseVideo(parsed.useVideo);
      if (typeof parsed.webSearch === "boolean") setWebSearch(parsed.webSearch);
      if (typeof parsed.summaryOnly === "boolean") setSummaryOnly(parsed.summaryOnly);
    } catch {
      // ignore malformed local data
    } finally {
      setUserSettingsLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!userSettingsLoaded) return;

    const storageKey =
      userSettingsStorageKeyRef.current ||
      `${USER_SETTINGS_STORAGE_KEY_PREFIX}:${getOrCreateHistoryClientId() || "anonymous"}`;
    userSettingsStorageKeyRef.current = storageKey;
    const payload: PersistedUserSettings = {
      version: 1,
      apiKey: safeString(apiKey, 500, ""),
      modelPreset,
      modelName: safeString(modelName, 200, ""),
      modelBaseUrl: safeString(modelBaseUrl, 300, ""),
      whisperModel,
      maxVision: Math.round(clampNumber(maxVision, 10, MAX_VISION_MIN, MAX_VISION_MAX)),
      useVideo: Boolean(useVideo),
      webSearch: Boolean(webSearch),
      fps: Number(clampNumber(fps, 1, FPS_MIN, FPS_MAX).toFixed(1)),
      summaryOnly: Boolean(summaryOnly),
      updatedAt: new Date().toISOString(),
    };
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(payload));
    } catch {
      // ignore storage write failure
    }
  }, [apiKey, fps, maxVision, modelBaseUrl, modelName, modelPreset, summaryOnly, useVideo, userSettingsLoaded, webSearch, whisperModel]);

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
      if (apiKeyGuideTimerRef.current) clearTimeout(apiKeyGuideTimerRef.current);
      if (apiKeyGuideFocusTimerRef.current) clearTimeout(apiKeyGuideFocusTimerRef.current);
      if (modelConfigGuideTimerRef.current) clearTimeout(modelConfigGuideTimerRef.current);
      if (modelConfigGuideFocusTimerRef.current) clearTimeout(modelConfigGuideFocusTimerRef.current);
      if (modelTestGuideTimerRef.current) clearTimeout(modelTestGuideTimerRef.current);
      if (modelTestGuideFocusTimerRef.current) clearTimeout(modelTestGuideFocusTimerRef.current);
      if (batchTimerRef.current) clearInterval(batchTimerRef.current);
      if (singleTimerRef.current) clearInterval(singleTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if ((!historyDrawerOpen && !settingsDrawerOpen && !showClearHistoryConfirm && !pendingDeleteHistory) || typeof document === "undefined") return;
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
        setSettingsDrawerOpen(false);
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
    settingsDrawerOpen,
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

  const triggerModelConfigGuide = useCallback(() => {
    setHistoryDrawerOpen(false);
    setSettingsDrawerOpen(true);
    setModelConfigGuideActive(true);

    if (modelConfigGuideTimerRef.current) clearTimeout(modelConfigGuideTimerRef.current);
    modelConfigGuideTimerRef.current = setTimeout(
      () => setModelConfigGuideActive(false),
      ERROR_GUIDE_DURATION_MS,
    );

    if (modelConfigGuideFocusTimerRef.current) clearTimeout(modelConfigGuideFocusTimerRef.current);
    modelConfigGuideFocusTimerRef.current = setTimeout(() => {
      const missingBaseUrl = modelPreset === "custom" && !String(modelBaseUrl || "").trim();
      const missingModelName = !String(modelName || "").trim();
      const target = missingBaseUrl
        ? modelBaseUrlInputRef.current
        : missingModelName
          ? modelNameInputRef.current
          : modelBaseUrlInputRef.current;
      target?.focus();
      target?.scrollIntoView({ behavior: uiScrollBehavior, block: "center" });
    }, 220);
  }, [modelBaseUrl, modelName, modelPreset, uiScrollBehavior]);

  const triggerModelTestGuide = useCallback(() => {
    setHistoryDrawerOpen(false);
    setSettingsDrawerOpen(true);
    setModelTestGuideActive(true);

    if (modelTestGuideTimerRef.current) clearTimeout(modelTestGuideTimerRef.current);
    modelTestGuideTimerRef.current = setTimeout(
      () => setModelTestGuideActive(false),
      ERROR_GUIDE_DURATION_MS,
    );

    if (modelTestGuideFocusTimerRef.current) clearTimeout(modelTestGuideFocusTimerRef.current);
    modelTestGuideFocusTimerRef.current = setTimeout(() => {
      modelTestButtonRef.current?.focus();
      modelTestButtonRef.current?.scrollIntoView({ behavior: uiScrollBehavior, block: "center" });
    }, 260);
  }, [uiScrollBehavior]);

  const validateModelConfig = useCallback(() => {
    const hasBaseUrl = Boolean(String(modelBaseUrl || "").trim());
    const hasModelName = Boolean(String(modelName || "").trim());
    const needBaseUrl = modelPreset === "custom";
    if (hasModelName && (!needBaseUrl || hasBaseUrl)) return true;
    if (needBaseUrl && !hasBaseUrl && !hasModelName) {
      showError("请填写模型接口 Base URL 和模型名称");
    } else if (needBaseUrl && !hasBaseUrl) {
      showError("请填写模型接口 Base URL");
    } else {
      showError("请填写模型名称");
    }
    triggerModelConfigGuide();
    return false;
  }, [modelBaseUrl, modelName, modelPreset, showError, triggerModelConfigGuide]);

  const applyModelPreset = useCallback((preset: ModelPreset) => {
    setModelPreset(preset);
    setModelConfigGuideActive(false);
    if (preset === "custom") {
      setModelBaseUrl("");
      setModelName("");
      return;
    }
    const selected = MODEL_PRESETS[preset];
    setModelBaseUrl(selected.baseUrl);
    setModelName("");
  }, []);

  const testModelConnection = useCallback(async () => {
    if (!apiKey) {
      showError("请输入 API Key");
      return;
    }
    if (!validateModelConfig()) return;

    setTestingModel(true);
    try {
      const data = await fetchJson<{ message?: string; reply?: string }>("/test_model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
        }),
      });

      const responseText = String(data.reply || "").replace(/\s+/g, " ").trim();
      const briefReply = responseText ? ` · 返回：${responseText.slice(0, 48)}` : "";
      verifiedModelConfigSignatureRef.current = buildModelConfigSignature(
        apiKey,
        modelPreset,
        modelName,
        modelBaseUrl,
      );
      showSuccess(`${String(data.message || "模型连接测试成功")}${briefReply}`);
    } catch (error) {
      showError(String((error as Error).message || error));
    } finally {
      setTestingModel(false);
    }
  }, [apiKey, fetchJson, modelBaseUrl, modelName, modelPreset, showError, showSuccess, validateModelConfig]);

  const pickUploadPrecheckError = useCallback((message: string) => {
    const raw = String(message || "").trim();
    const normalized = raw.replace(/^模型连接测试失败[:：]\s*/u, "").trim();
    const errorCode = extractErrorCode(normalized);
    if (errorCode === "risk_model_config_invalid") {
      return "模型配置无效：请检查 Base URL、模型名称是否匹配，并确认模型支持图片理解";
    }
    if (errorCode === "risk_model_auth_failed") {
      return "模型鉴权失败：请检查 API Key 是否有效且与当前平台匹配";
    }
    const parts = normalized.split("|").map((item) => item.trim()).filter(Boolean);
    const preferredHints = [
      "模型鉴权失败",
      "模型连接失败",
      "请求过于频繁",
      "模型服务请求超时",
      "模型服务调用失败",
      "联网搜索功能未开通",
    ];
    for (const hint of preferredHints) {
      const matched = parts.find((item) => item.includes(hint));
      if (matched) return matched;
    }
    return parts[0] || normalized || "模型连通测试失败";
  }, []);

  const verifyModelConnectionForUpload = useCallback(async () => {
    // 模型连通校验已取消：统一由后端 .env 托管模型配置。
    void pickUploadPrecheckError;
    void triggerModelTestGuide;
    void testModelConnection;
    return true;
  }, [pickUploadPrecheckError, testModelConnection, triggerModelTestGuide]);

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
        setProgressTextIfChanged(`正在上传 ${file.name}（${fileIndex}/${totalFiles}，分片 ${chunkIndex + 1}/${totalChunks}）`);
        await fetchJson("/upload_chunk", { method: "POST", body: formData });
      }

      onSafetyCheckStart?.(file, fileIndex, totalFiles);
      setProgressTextIfChanged(`已上传完成，正在进行安全检测：${file.name}（${fileIndex}/${totalFiles}）`);
      const finalized = await fetchJson<{ filename: string; filepath: string }>("/upload_chunk_finalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId }),
      });
      window.localStorage.removeItem(resumeKey);
      return finalized;
    },
    [fetchJson, setProgressTextIfChanged],
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

      showProgress("上传中", "正在上传视频...");
      updateProgressBoard({ mode: "upload", stage: "prepare", total: files.length, percent: 0 });
      try {
        const uploaded: BatchFileItem[] = [];
        let uploadedSuccess = 0;
        let uploadedFailed = 0;
        for (let i = 0; i < files.length; i += 1) {
          const currentFile = files[i];
          try {
            const item = await uploadSingleFileWithResume(
              currentFile,
              i + 1,
              files.length,
              (processingFile, currentIndex, total) => {
                const moderationPercent = Math.min(
                  99,
                  Math.round(((Math.max(0, currentIndex - 1) + STAGE_PERCENT.moderation / 100) / total) * 100),
                );
                setProgressTextIfChanged(`已上传完成，正在进行安全检测：${processingFile.name}（${currentIndex}/${total}）`);
                updateProgressBoard({
                  mode: "upload",
                  stage: "moderation",
                  total,
                  current: currentIndex,
                  success: uploadedSuccess,
                  failed: uploadedFailed,
                  percent: moderationPercent,
                  currentFile: processingFile.name,
                });
              },
            );
            uploaded.push({ filename: item.filename, filepath: item.filepath, status: "pending", error: "" });
            uploadedSuccess += 1;
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
            uploaded.push({
              filename: currentFile.name,
              filepath: "",
              status: "failed",
              error: formatInlineErrorMessage(message),
            });
            uploadedFailed += 1;
          }
          updateProgressBoard({
            mode: "upload",
            stage: i + 1 >= files.length ? "done" : "upload",
            total: files.length,
            current: i + 1,
            success: uploadedSuccess,
            failed: uploadedFailed,
            percent: Math.round(((i + 1) / files.length) * 100),
          });
        }
        setBatchFiles((prev) => [...prev, ...uploaded]);
        if (uploadedFailed > 0) {
          showError(`已跳过 ${uploadedFailed} 个上传失败视频，可继续分析其余视频。`);
        }
      } catch (error) {
        showError(`上传失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [
      hideProgress,
      setProgressTextIfChanged,
      showError,
      showProgress,
      updateProgressBoard,
      uploadSingleFileWithResume,
      verifyModelConnectionForUpload,
    ],
  );
  const analyzeByUploadedFile = useCallback(async (file: BatchFileItem) => {
    setBatchFiles((prev) =>
      prev.map((item) =>
        item.filepath ? { ...item, status: item.filepath === file.filepath ? "pending" : item.status, error: "" } : item,
      ),
    );
    stopBatchPolling();
    setIsAnalyzing(true);
    showProgress("单文件处理中", summaryOnly ? "正在生成摘要版，请稍候..." : "正在分析视频，请稍候...");
    updateProgressBoard({ mode: "single", stage: "prepare", total: 1, percent: 5, currentFile: file.filename });
    startSinglePolling();
    let reveal = false;
    try {
      const data = await fetchJson<SingleResultData>("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filepath: file.filepath,
          web_search: webSearch,
          max_vision: maxVision,
          summary_only: summaryOnly,
        }),
      });
      setResultData(data);
      setBatchResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
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
    showProgress,
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

    setImportingUrl(true);
    showProgress("链接导入中", "正在下载链接视频并执行安全检测...");
    updateProgressBoard({ mode: "upload", stage: "prepare", total: 1, percent: 0, current: 0 });

    try {
      const uploadedItem = await uploadBySourceUrl(urls[0]);
      setBatchFiles((prev) => [uploadedItem, ...prev]);
      setSourceUrl("");
      updateProgressBoard({
        mode: "upload",
        stage: "done",
        total: 1,
        current: 1,
        success: 1,
        failed: 0,
        percent: 100,
        currentFile: uploadedItem.filename,
      });
      showSuccess("链接导入成功，可直接开始分析。");
    } catch (error) {
      showError(`链接导入失败: ${String((error as Error).message || error)}`);
    } finally {
      hideProgress();
      setImportingUrl(false);
    }
  }, [
    hideProgress,
    showError,
    showProgress,
    showSuccess,
    sourceUrl,
    updateProgressBoard,
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

    setImportingUrl(true);
    stopBatchPolling();
    stopSinglePolling();
    setIsAnalyzing(true);
    showProgress("链接处理中", "正在下载链接视频并执行安全检测...");
    updateProgressBoard({ mode: "upload", stage: "prepare", total: 1, percent: 0, current: 0 });

    try {
      const uploadedItem = await uploadBySourceUrl(urls[0]);
      setBatchFiles((prev) => [uploadedItem, ...prev]);
      setSourceUrl("");
      updateProgressBoard({
        mode: "upload",
        stage: "done",
        total: 1,
        current: 1,
        success: 1,
        failed: 0,
        percent: 100,
        currentFile: uploadedItem.filename,
      });
      setProgressTextIfChanged("链接视频导入完成，正在启动分析...");
      await analyzeByUploadedFile(uploadedItem);
    } catch (error) {
      showError(`链接分析失败: ${String((error as Error).message || error)}`);
      hideProgress();
      setIsAnalyzing(false);
    } finally {
      setImportingUrl(false);
    }
  }, [
    analyzeByUploadedFile,
    hideProgress,
    setProgressTextIfChanged,
    showError,
    showProgress,
    sourceUrl,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    uploadBySourceUrl,
    verifyModelConnectionForUpload,
  ]);

  const analyzeBatch = useCallback(async () => {
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length <= 1) return;
    setBatchFiles((prev) =>
      prev.map((item) => (item.filepath ? { ...item, status: "pending", error: "" } : item)),
    );
    stopSinglePolling();
    setIsAnalyzing(true);
    showProgress("批量处理中", summaryOnly ? "正在逐个生成摘要版..." : "正在逐个分析视频...");
    updateProgressBoard({ mode: "batch", stage: "prepare", total: analyzableFiles.length, percent: 0 });
    startBatchPolling();
    let reveal = false;
    try {
      const data = await fetchJson<BatchResultData>("/analyze_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filepaths: analyzableFiles.map((item) => item.filepath),
          web_search: webSearch,
          max_vision: maxVision,
          summary_only: summaryOnly,
        }),
      });
      setBatchResultData(data);
      setResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
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
    showProgress,
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
        setBatchResultData(null);
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

    const requestRegenerate = async (enableWebSearch: boolean) =>
      fetchJson<SingleResultData>("/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          steps: editedSteps,
          output_dir: resultData.output_dir,
          web_search: enableWebSearch,
        }),
      });

    try {
      let data: SingleResultData;
      try {
        data = await requestRegenerate(webSearch);
      } catch (error) {
        const message = String((error as Error).message || error);
        const canFallback = webSearch && WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint));
        if (!canFallback) throw error;
        setWebSearch(false);
        data = await requestRegenerate(false);
      }

      setResultData(data);
      setIsEditMode(false);
      setEditedSteps([]);
    } catch (error) {
      showError(`重新生成失败: ${String((error as Error).message || error)}`);
    } finally {
      setSavingSteps(false);
      hideProgress();
    }
  }, [editedSteps, fetchJson, hideProgress, resultData?.output_dir, showError, showProgress, webSearch]);

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

  const downloadSubtitleFile = useCallback(
    async (format: "srt" | "vtt" | "txt") => {
      const outputDirName = basename(resultData?.output_dir);
      if (!outputDirName) {
        showError("没有可下载字幕的结果");
        return;
      }
      try {
        const blob = await fetchBlob(
          `/download_subtitle/${encodeURIComponent(outputDirName)}?format=${encodeURIComponent(format)}`,
        );
        triggerDownload(blob, `${outputDirName}_subtitle.${format}`);
      } catch (error) {
        showError(`字幕下载失败: ${String((error as Error).message || error)}`);
      }
    },
    [fetchBlob, resultData?.output_dir, showError, triggerDownload],
  );

  const seekVideoTo = useCallback((seconds: number) => {
    const videoEl = subtitleVideoRef.current;
    if (!videoEl) return;
    const targetSeconds = Math.max(0, Number(seconds) || 0);
    videoEl.currentTime = targetSeconds;
    void videoEl.play().catch(() => undefined);
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
          ? "处理中"
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
  const clampMaxVision = useCallback(
    (value: number) => Math.max(MAX_VISION_MIN, Math.min(MAX_VISION_MAX, Math.round(Number(value) || 0))),
    [],
  );
  const handleMaxVisionInput = useCallback(
    (rawValue: string) => {
      const parsed = Number(rawValue);
      if (!Number.isFinite(parsed)) {
        setMaxVision(MAX_VISION_MIN);
        return;
      }
      setMaxVision(clampMaxVision(parsed));
    },
    [clampMaxVision],
  );
  const increaseMaxVision = useCallback(() => {
    setMaxVision((prev) => clampMaxVision(prev + 1));
  }, [clampMaxVision]);
  const decreaseMaxVision = useCallback(() => {
    setMaxVision((prev) => clampMaxVision(prev - 1));
  }, [clampMaxVision]);
  const clampFps = useCallback((value: number) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return FPS_MIN;
    const clamped = Math.max(FPS_MIN, Math.min(FPS_MAX, numeric));
    return Math.round(clamped * 10) / 10;
  }, []);
  const handleFpsInput = useCallback(
    (rawValue: string) => {
      const parsed = Number(rawValue);
      if (!Number.isFinite(parsed)) {
        setFps(FPS_MIN);
        return;
      }
      setFps(clampFps(parsed));
    },
    [clampFps],
  );
  const increaseFps = useCallback(() => {
    setFps((prev) => clampFps(prev + FPS_STEP));
  }, [clampFps]);
  const decreaseFps = useCallback(() => {
    setFps((prev) => clampFps(prev - FPS_STEP));
  }, [clampFps]);
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
  const isDegradedResult = singleResultMode === "candidate_steps" || singleResultMode === "timeline_summary";
  const drawerOverlayActive =
    historyDrawerOpen || settingsDrawerOpen || showClearHistoryConfirm || Boolean(pendingDeleteHistory);
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
            <button
              type="button"
              aria-expanded={settingsDrawerOpen}
              aria-controls="settings-drawer"
              onClick={() => {
                setHistoryDrawerOpen(false);
                setSettingsDrawerOpen((prev) => !prev);
              }}
              className="vi-nav-pill focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              设置
            </button>
            <button
              type="button"
              aria-expanded={historyDrawerOpen}
              aria-controls="history-drawer"
              onClick={() => {
                setSettingsDrawerOpen(false);
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
        <header className="vi-hero hero-panel panel-card motion-enter rounded-xl border-0 bg-transparent p-4">
          <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-3 text-center">
            <span className="vi-hero-eyebrow">AI · 视频理解工作台</span>
            <h1 className="vi-hero-title">
              视频转文档，
              <span className="vi-hero-title-accent"> 不止提取，更是理解</span>
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

        <div className="app-grid grid items-start gap-5 2xl:gap-6">
          <section className="app-workspace motion-enter motion-delay-2 min-w-0 space-y-4">
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
                <p className="vi-url-bar__note">
                  只需提供链接即可下载并分析；平台播放页链接建议安装 <code>yt-dlp</code> 提升兼容性。
                </p>
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
              <div className="vi-kv-grid mt-3">
                <div className="vi-kv-cell">
                  <div className="vi-kv-label">标准推荐</div>
                  <div className="vi-kv-value">20 分钟 · 250 MB 以内</div>
                  <p className="vi-help">处理速度与稳定性最佳</p>
                </div>
                <div className="vi-kv-cell">
                  <div className="vi-kv-label">长视频模式</div>
                  <div className="vi-kv-value">自动切片 · 自动压缩</div>
                  <p className="vi-help">20 分钟 / 250 MB 以上会自动进入，耗时增加</p>
                </div>
                <div className="vi-kv-cell">
                  <div className="vi-kv-label">超长视频</div>
                  <div className="vi-kv-value">建议先裁剪</div>
                  <p className="vi-help">45 分钟+ 建议按章节裁剪，90 分钟+ 请拆分</p>
                </div>
                <div className="vi-kv-cell">
                  <div className="vi-kv-label">批量上限</div>
                  <div className="vi-kv-value">最多 5 个 / 含长视频 ≤ 2</div>
                  <p className="vi-help">稳定性优先，避免单批过大</p>
                </div>
              </div>
              <div className="vi-batch-list">
                {batchFiles.map((item, index) => (
                  <div
                    key={`${item.filepath}-${index}`}
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
                        <span className="vi-status vi-status--run">处理中</span>
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
                    gradientColors={ANALYZE_BUTTON_GRADIENT_COLORS}
                    noiseIntensity={0.07}
                    speed={0.13}
                    animating={shouldAnimateNoiseBackground}
                  >
                    {analyzeActionButton}
                  </NoiseBackground>
                )}
              </div>
              <button
                type="button"
                className={cn(
                  "vi-btn vi-btn--block vi-btn--sm mt-2",
                  summaryOnly && "vi-btn--primary",
                )}
                disabled={isAnalyzing}
                onClick={() => setSummaryOnly((prev) => !prev)}
              >
                {summaryOnly ? "仅生成摘要版：已开启" : "仅生成摘要版"}
              </button>
            </section>

            {hasAnyResult ? (
              <div
                ref={resultsRef}
                className="results-grid grid items-stretch gap-4 xl:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]"
              >
                {hasBatchResult ? (
                  <section className="panel-card motion-enter rounded-xl border border-neutral-800 bg-neutral-900/70 p-4 xl:col-span-2">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <StackIcon className="h-4 w-4 text-neutral-300" />
                        <h2 className="text-base font-semibold">批量处理结果</h2>
                      </div>
                      <button
                        className="zip-download-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
                        onClick={() => void downloadBatchZip()}
                      >
                        <DownloadZipIcon className="h-3.5 w-3.5" />
                        下载批量 ZIP
                      </button>
                    </div>
                    {(batchResultData?.batch_policy_warnings || []).length > 0 ? (
                      <div className="mb-2 rounded border border-amber-400/35 bg-amber-500/10 p-2 text-xs text-amber-200/95">
                        <p className="font-semibold">批次策略提醒</p>
                        <ul className="mt-1 list-disc space-y-1 pl-5">
                          {(batchResultData?.batch_policy_warnings || []).slice(0, 3).map((tip, idx) => (
                            <li key={`batch-policy-warning-${idx}`}>{tip}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    {batchResultData?.batch_segment_policy?.summary ? (
                      <div className="mb-2 rounded border border-sky-400/30 bg-sky-500/8 p-2 text-xs text-sky-100/95">
                        <p className="font-semibold">
                          批次分段统计：总计 {Number(batchResultData.batch_segment_policy.summary.total_files || 0)} 个
                        </p>
                        <p className="mt-1">
                          长视频 {Number(batchResultData.batch_segment_policy.summary.long_count || 0)} · 超长{" "}
                          {Number(batchResultData.batch_segment_policy.summary.super_long_count || 0)} · 裁剪优先{" "}
                          {Number(batchResultData.batch_segment_policy.summary.trim_required_count || 0)}
                        </p>
                      </div>
                    ) : null}
                    <div className="space-y-2">
                      {(batchResultData?.results || []).map((r, i) => (
                        <div key={`${r.filename}-${i}`} className="list-item-pop rounded border border-neutral-800 bg-neutral-950/60 p-2">
                          <div className="flex items-center justify-between">
                            <p className="truncate text-sm font-medium">{r.filename}</p>
                            <span
                              className={`text-xs ${
                                r.success
                                  ? r.result_mode === "candidate_steps" || r.result_mode === "timeline_summary"
                                    ? "text-amber-300"
                                    : "text-emerald-300"
                                  : r.result_mode === "blocked_notice" || r.code === "content_policy_violation"
                                    ? "text-amber-300"
                                    : "text-rose-300"
                              }`}
                            >
                              {r.success
                                ? r.result_mode === "candidate_steps" || r.result_mode === "timeline_summary"
                                  ? "已完成（降级）"
                                  : "成功"
                                : r.result_mode === "blocked_notice" || r.code === "content_policy_violation"
                                  ? "已拦截"
                                  : "失败"}
                            </span>
                          </div>
                          {r.segment_policy ? (
                            <p className="mt-1 text-[11px] text-sky-200/90">
                              分段策略：{formatSegmentPolicyLine(r.segment_policy)}
                            </p>
                          ) : null}
                          {(r.segment_guardrails || []).length > 0 ? (
                            <p className="mt-1 text-[11px] text-amber-200/90">
                              调整：{String((r.segment_guardrails || [])[0] || "")}
                            </p>
                          ) : null}
                          {r.success ? (
                            <>
                              <button
                                className="zip-download-btn mt-1 flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
                                onClick={() => void downloadSingleFromBatch(r.output_dir, r.filename)}
                              >
                                <DownloadSingleIcon className="h-3.5 w-3.5" />
                                下载
                              </button>
                              {r.fallback_used ? (
                                <p className="mt-1 text-xs text-amber-300/90">
                                  {(r.analysis_note || "未识别到标准步骤，已自动生成候选内容。") +
                                    `（质量分：${Number(r.quality_score || 0).toFixed(2)}）`}
                                </p>
                              ) : null}
                            </>
                          ) : r.result_mode === "blocked_notice" || r.code === "content_policy_violation" ? (
                            <div className="mt-1 rounded border border-rose-500/45 bg-rose-500/10 p-2 text-xs text-rose-200/95">
                              <p className="font-semibold">
                                {r.blocked_notice?.title || "安全检测未通过（已拦截）"}
                              </p>
                              <p className="mt-1">
                                等级：{String(r.blocked_notice?.risk_level || r.risk?.risk_level || "high")} · 规则：
                                {String(r.blocked_notice?.reason_code || r.risk?.reason_code || "CONTENT_POLICY_VIOLATION")}
                              </p>
                              <p className="mt-1 break-words">
                                {String(r.blocked_notice?.reason || r.risk?.reason || r.error || CONTENT_POLICY_BLOCK_MESSAGE)}
                              </p>
                              {(r.blocked_notice?.suggestions || []).length > 0 ? (
                                <ul className="mt-1 list-disc space-y-1 pl-4">
                                  {(r.blocked_notice?.suggestions || []).slice(0, 3).map((tip, idx) => (
                                    <li key={`b-tip-${i}-${idx}`}>{tip}</li>
                                  ))}
                                </ul>
                              ) : null}
                            </div>
                          ) : (
                            <p className="mt-1 text-xs text-rose-300">{r.error || "处理失败"}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </section>
                ) : null}

                {hasSingleResult ? (
                  <section className="panel-card motion-enter result-heavy-surface flex h-full min-h-0 flex-col rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <StepsIcon className="h-4 w-4 text-neutral-300" />
                        <h2 className="text-base font-semibold">
                          {isBlockedNoticeResult
                            ? "安全检测结果说明"
                            : isDegradedResult
                              ? singleResultMode === "timeline_summary"
                                ? "时间线摘要（自动降级）"
                                : "候选步骤（自动降级）"
                              : "识别到的步骤"}
                        </h2>
                      </div>
                      {!isEditMode && !isBlockedNoticeResult ? (
                        <button
                          className="steps-edit-btn flex items-center gap-1 rounded px-2 py-1 text-xs"
                          onClick={() => {
                            if (!resultData?.steps?.length) return showError("当前没有可编辑步骤");
                            setEditedSteps(
                              clone(resultData.steps).map((s, i) => ({
                                ...s,
                                step: i + 1,
                                time: s.time || "00:00",
                                title: s.title || "",
                                description: s.description || "",
                              })),
                            );
                            setIsEditMode(true);
                          }}
                        >
                          <EditIcon className="h-3.5 w-3.5" />
                          编辑
                        </button>
                      ) : null}
                    </div>
                    {resultData?.analysis_note ? (
                      <p
                        className={`mb-2 text-xs ${
                          isBlockedNoticeResult ? "text-rose-300/90" : "text-amber-300/90"
                        }`}
                      >
                        {resultData.analysis_note}
                      </p>
                    ) : null}
                    {resultData?.segment_policy ? (
                      <div className="mb-2 rounded border border-sky-400/35 bg-sky-500/8 p-2 text-xs text-sky-100/95">
                        <p className="font-semibold">分段策略：{formatSegmentPolicyLine(resultData.segment_policy)}</p>
                        {(resultData.segment_policy.recommendations || []).length > 0 ? (
                          <ul className="mt-1 list-disc space-y-1 pl-5 text-sky-100/90">
                            {(resultData.segment_policy.recommendations || []).slice(0, 3).map((tip, idx) => (
                              <li key={`single-policy-tip-${idx}`}>{tip}</li>
                            ))}
                          </ul>
                        ) : null}
                        {(resultData.segment_guardrails || []).length > 0 ? (
                          <ul className="mt-1 list-disc space-y-1 pl-5 text-amber-200/90">
                            {(resultData.segment_guardrails || []).slice(0, 3).map((tip, idx) => (
                              <li key={`single-guardrail-${idx}`}>{tip}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    ) : null}
                    {isBlockedNoticeResult ? (
                      <div className="rounded border border-rose-500/45 bg-rose-500/10 p-3 text-sm">
                        <p className="font-semibold text-rose-200">
                          {resultData?.blocked_notice?.title || "安全检测未通过（已拦截）"}
                        </p>
                        <p className="mt-1 text-rose-100/90">
                          风险等级：{String(resultData?.blocked_notice?.risk_level || resultData?.risk?.risk_level || "high")}
                        </p>
                        <p className="text-rose-100/90">
                          规则码：{String(resultData?.blocked_notice?.reason_code || resultData?.risk?.reason_code || "CONTENT_POLICY_VIOLATION")}
                        </p>
                        <p className="mt-1 text-rose-100/95 break-words">
                          {String(resultData?.blocked_notice?.reason || resultData?.risk?.reason || CONTENT_POLICY_BLOCK_MESSAGE)}
                        </p>
                        {(resultData?.blocked_notice?.suggestions || []).length > 0 ? (
                          <ul className="mt-2 list-disc space-y-1 pl-5 text-rose-100/90">
                            {(resultData?.blocked_notice?.suggestions || []).slice(0, 4).map((tip, idx) => (
                              <li key={`bn-tip-${idx}`}>{tip}</li>
                            ))}
                          </ul>
                        ) : null}
                        {resultData?.blocked_notice?.retry_guidance ? (
                          <p className="mt-2 text-rose-100/90">{resultData.blocked_notice.retry_guidance}</p>
                        ) : null}
                      </div>
                    ) : !isEditMode ? (
                      <div className="single-result-scroll history-scroll flex-1 min-h-0 space-y-2 overflow-auto pr-1">
                        {isDegradedResult ? (
                          <div className="space-y-2">
                            <div className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200">
                              置信度较低（质量分：{Number(resultData?.quality_score || 0).toFixed(2)}）。原因：
                              {formatDegradeReason(resultData?.degrade_reason)}
                            </div>
                            {resultData?.content_title ? (
                              <div className="rounded border border-amber-400/30 bg-amber-500/6 p-2 text-xs text-amber-100/95">
                                <p className="font-semibold">标题：{resultData.content_title}</p>
                                {(resultData.key_points || []).length > 0 ? (
                                  <ul className="mt-1 list-disc space-y-1 pl-5">
                                    {(resultData.key_points || []).slice(0, 5).map((item, idx) => (
                                      <li key={`kp-${idx}`}>{item}</li>
                                    ))}
                                  </ul>
                                ) : null}
                                {(resultData.timeline_points || []).length > 0 ? (
                                  <p className="mt-1">
                                    时间点：
                                    {(resultData.timeline_points || [])
                                      .slice(0, 5)
                                      .map((item) => String(item?.time || "00:00"))
                                      .join(" / ")}
                                  </p>
                                ) : null}
                                {resultData?.confidence_note ? (
                                  <p className="mt-1">{resultData.confidence_note}</p>
                                ) : null}
                              </div>
                            ) : null}
                          </div>
                        ) : null}
                        <ReadonlyStepsList steps={singleResultSteps} />
                      </div>
                    ) : (
                      <div className="steps-edit-scroll history-scroll flex-1 min-h-0 overflow-auto pr-1">
                        <div className="steps-edit-actions mb-2 flex gap-2">
                          <button
                            type="button"
                            disabled={savingSteps}
                            className="steps-edit-save-btn"
                            onClick={() => void saveEditedSteps()}
                          >
                            保存并重生成
                          </button>
                          <button
                            type="button"
                            disabled={savingSteps}
                            className="steps-edit-cancel-btn"
                            onClick={() => {
                              setIsEditMode(false);
                              setEditedSteps([]);
                            }}
                          >
                            取消
                          </button>
                        </div>
                        <div className="space-y-2">
                          {editedSteps.map((step, index) => (
                            <div
                              key={`e-${index}`}
                              draggable
                              onDragStart={() => setDragIndex(index)}
                              onDragOver={(e) => {
                                e.preventDefault();
                                setDragOverIndex(index);
                              }}
                              onDrop={(e) => {
                                e.preventDefault();
                                if (dragIndex === null || dragIndex === index) return;
                                setEditedSteps((prev) => {
                                  const next = [...prev];
                                  const [moved] = next.splice(dragIndex, 1);
                                  if (!moved) return prev;
                                  next.splice(index, 0, moved);
                                  return next.map((s, i) => ({ ...s, step: i + 1 }));
                                });
                                setDragIndex(null);
                                setDragOverIndex(null);
                              }}
                              onDragEnd={() => {
                                setDragIndex(null);
                                setDragOverIndex(null);
                              }}
                              className={`rounded border p-2 ${
                                dragIndex === index
                                  ? "border-teal-500/50 opacity-60"
                                  : dragOverIndex === index
                                    ? "border-teal-400"
                                    : "border-neutral-800"
                              }`}
                            >
                              <div className="mb-1 flex gap-2">
                                <input
                                  className="steps-edit-input flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
                                  value={step.title || ""}
                                  placeholder={NEW_STEP_DEFAULT_TITLE}
                                  onChange={(e) =>
                                    setEditedSteps((prev) =>
                                      prev.map((item, idx) => (idx === index ? { ...item, title: e.target.value } : item)),
                                    )
                                  }
                                />
                                <input
                                  className="steps-edit-input w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
                                  value={step.time || ""}
                                  placeholder={NEW_STEP_DEFAULT_TIME}
                                  onChange={(e) =>
                                    setEditedSteps((prev) =>
                                      prev.map((item, idx) => (idx === index ? { ...item, time: e.target.value } : item)),
                                    )
                                  }
                                />
                              </div>
                              <textarea
                                className="steps-edit-textarea min-h-16 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
                                value={step.description || ""}
                                placeholder={NEW_STEP_DEFAULT_DESCRIPTION}
                                onChange={(e) =>
                                  setEditedSteps((prev) =>
                                    prev.map((item, idx) => (idx === index ? { ...item, description: e.target.value } : item)),
                                  )
                                }
                              />
                              <button
                                type="button"
                                title="删除步骤"
                                aria-label="删除步骤"
                                className="mt-1 inline-flex h-7 w-7 items-center justify-center rounded border border-rose-500/40 text-rose-300 transition-colors hover:bg-rose-500/10"
                                onClick={() =>
                                  setEditedSteps((prev) =>
                                    prev.filter((_, idx) => idx !== index).map((s, i) => ({ ...s, step: i + 1 })),
                                  )
                                }
                              >
                                <TrashIcon />
                              </button>
                            </div>
                          ))}
                        </div>
                        <button
                          className="mt-2 w-full rounded-lg border border-dashed border-teal-400/45 bg-gradient-to-b from-teal-500/8 to-cyan-500/6 px-3 py-2 text-sm font-medium text-teal-100/90 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] transition-all duration-200 hover:-translate-y-0.5 hover:border-teal-300/70 hover:from-teal-500/14 hover:to-cyan-500/12 hover:text-teal-50 active:translate-y-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-400/60 focus-visible:ring-offset-2 focus-visible:ring-offset-neutral-950"
                          onClick={() =>
                            setEditedSteps((prev) => [
                              ...prev,
                              {
                                step: prev.length + 1,
                                time: "",
                                title: "",
                                description: "",
                              },
                            ])
                          }
                        >
                          添加新步骤
                        </button>
                      </div>
                    )}
                  </section>
                ) : null}

                {hasSingleResult && !isBlockedNoticeResult && Boolean(resultData?.markdown) ? (
                  <section className="panel-card motion-enter result-heavy-surface rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
                    <div className="mb-2 flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <DocumentIcon className="h-4 w-4 text-neutral-300" />
                        <h2 className="text-base font-semibold">生成的总结文档</h2>
                      </div>
                      <button
                        className="zip-download-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
                        onClick={() => void downloadSingleZip()}
                      >
                        <DownloadZipIcon className="h-3.5 w-3.5" />
                        下载 ZIP
                      </button>
                    </div>
                    <MarkdownPreview
                      html={renderedMarkdown}
                      className={summaryOnly ? "summary-only-scroll-rail" : undefined}
                      contentClassName={
                        summaryOnly ? "summary-only-markdown-content" : "standard-markdown-content"
                      }
                    />
                  </section>
                ) : null}

                {hasSingleResult && !isBlockedNoticeResult && Boolean(resultData?.output_dir) ? (
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
                          disabled={subtitleLoading}
                          onClick={() => void loadSubtitleWorkbench(String(resultData?.output_dir || ""))}
                        >
                          {subtitleLoading ? "加载中..." : "刷新字幕"}
                        </button>
                        <button
                          type="button"
                          className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={subtitleLoading}
                          onClick={() => void downloadSubtitleFile("srt")}
                        >
                          导出 SRT
                        </button>
                        <button
                          type="button"
                          className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={subtitleLoading}
                          onClick={() => void downloadSubtitleFile("vtt")}
                        >
                          导出 VTT
                        </button>
                        <button
                          type="button"
                          className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100 disabled:cursor-not-allowed disabled:opacity-60"
                          disabled={subtitleLoading}
                          onClick={() => void downloadSubtitleFile("txt")}
                        >
                          导出 TXT
                        </button>
                      </div>
                    </div>

                    {String(subtitleWorkbench?.video_preview_url || resultData?.video_preview_url || "").trim() ? (
                      <div className="mb-2 overflow-hidden rounded border border-neutral-800 bg-black/40">
                        <video
                          ref={subtitleVideoRef}
                          controls
                          preload="metadata"
                          className="max-h-[300px] w-full bg-black"
                          src={String(subtitleWorkbench?.video_preview_url || resultData?.video_preview_url || "")}
                        />
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
                            className="w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 placeholder:text-neutral-500 sm:max-w-xs"
                            placeholder="搜索字幕内容或时间点"
                            value={subtitleKeyword}
                            onChange={(e) => setSubtitleKeyword(e.target.value)}
                          />
                          <p className="text-xs text-neutral-400">
                            共 {subtitleLines.length} 行，匹配 {filteredSubtitleLines.length} 行
                          </p>
                        </div>
                        <div className="history-scroll max-h-[340px] space-y-1 overflow-auto pr-1">
                          {filteredSubtitleLines.slice(0, 1200).map((line, idx) => (
                            <button
                              type="button"
                              key={`sub-line-${line.index || idx}-${line.start_time || ""}`}
                              className="w-full rounded border border-neutral-800 bg-neutral-950/60 px-2 py-1.5 text-left text-xs transition-colors hover:border-teal-400/60 hover:bg-teal-500/10"
                              onClick={() => seekVideoTo(Number(line.start_seconds || 0))}
                            >
                              <p className="font-semibold text-teal-200/95">
                                {String(line.start_time || "00:00:00,000")} - {String(line.end_time || "00:00:00,000")}
                              </p>
                              <p className="mt-0.5 whitespace-pre-wrap text-neutral-200">{String(line.text || "")}</p>
                            </button>
                          ))}
                        </div>
                      </>
                    ) : subtitleAssetAvailable ? (
                      <div className="rounded border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
                        <p>
                          已检测到字幕文件，但当前未加载到字幕行。你可以点击“刷新字幕”，或直接导出 SRT/VTT/TXT。
                        </p>
                        {String(subtitleWorkbench?.subtitle_file || resultData?.subtitle_file_name || "").trim() ? (
                          <p className="mt-1 text-xs text-amber-200/90">
                            字幕文件：{String(subtitleWorkbench?.subtitle_file || resultData?.subtitle_file_name || "")}
                            {Number(resultData?.subtitle_line_count || 0) > 0
                              ? `（约 ${Number(resultData?.subtitle_line_count || 0)} 行）`
                              : ""}
                          </p>
                        ) : null}
                        {subtitleLoadError ? (
                          <p className="mt-1 text-xs text-amber-200/90">加载原因：{subtitleLoadError}</p>
                        ) : null}
                      </div>
                    ) : (
                      <p className="rounded border border-neutral-800 bg-neutral-950/60 px-3 py-2 text-sm text-neutral-300">
                        当前结果未检测到可用字幕。你可以切换字幕模式重新分析，或检查音频质量后重试。
                      </p>
                    )}
                  </section>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </main>

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
                    <p className="mt-2 rounded border border-amber-400/35 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200/95">
                      提醒：历史记录与服务器生成的总结文件仅保留 72 小时，系统会自动清理。
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

      {typeof document !== "undefined"
        ? createPortal(
            <div
              className="history-drawer-overlay fixed inset-0 z-[45]"
              hidden={!settingsDrawerOpen}
              aria-hidden={!settingsDrawerOpen}
            >
              <button
                type="button"
                aria-label="关闭设置侧边栏"
                className="history-drawer-backdrop absolute inset-0 bg-black/45"
                onClick={() => setSettingsDrawerOpen(false)}
              />
              <div className="pointer-events-none relative h-full w-full">
                <aside
                  id="settings-drawer"
                  className="history-drawer-panel pointer-events-auto ml-auto flex h-full w-[min(92vw,360px)] flex-col border-l border-neutral-700/80 bg-neutral-900/97 py-4 shadow-[-16px_0_34px_rgba(2,6,23,0.45)]"
                >
                  <div className="border-b border-neutral-800 px-4 pb-3">
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2">
                        <SettingsIcon className="h-4 w-4 text-neutral-300" />
                        <h2 className="text-base font-semibold">设置</h2>
                      </div>
                      <button
                        type="button"
                        title="关闭侧边栏"
                        aria-label="关闭侧边栏"
                        className="inline-flex h-8 w-8 items-center justify-center rounded border border-neutral-700 text-neutral-300 transition-colors hover:border-neutral-500 hover:text-neutral-100"
                        onClick={() => setSettingsDrawerOpen(false)}
                      >
                        <CloseIcon className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </div>
                  <div className="history-scroll flex-1 overflow-auto px-4 py-3">
                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">
                        <span className="mr-1 text-rose-300">*</span>模型 API Key
                      </label>
                      <div className="relative">
                        <input
                          ref={apiKeyInputRef}
                          className={cn(
                            "w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 pr-9 text-sm",
                            apiKeyGuideActive && "api-key-guide-input",
                          )}
                          type={showApiKey ? "text" : "password"}
                          placeholder="请输入 API Key"
                          value={apiKey}
                          onChange={(e) => {
                            setApiKey(e.target.value);
                            if (apiKeyGuideActive) setApiKeyGuideActive(false);
                          }}
                        />
                        <button
                          type="button"
                          className="absolute inset-y-0 right-0 inline-flex w-8 items-center justify-center rounded-r text-neutral-400 transition-colors hover:text-neutral-100"
                          title={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                          aria-label={showApiKey ? "隐藏 API Key" : "显示 API Key"}
                          onClick={() => setShowApiKey((prev) => !prev)}
                        >
                          {showApiKey ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
                        </button>
                      </div>
                      <p className="text-xs text-neutral-500">可填写任意兼容平台的 API Key</p>
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">模型预设</label>
                      <select
                        className="settings-select"
                        value={modelPreset}
                        onChange={(e) => applyModelPreset(e.target.value as ModelPreset)}
                      >
                        <option value="ark">{MODEL_PRESETS.ark.label}</option>
                        <option value="openai">{MODEL_PRESETS.openai.label}</option>
                        <option value="deepseek">{MODEL_PRESETS.deepseek.label}</option>
                        <option value="qwen">{MODEL_PRESETS.qwen.label}</option>
                        <option value="custom">自定义</option>
                      </select>
                      <p className="text-xs text-neutral-500">一键填充常见平台的 Base URL（模型名称需手动填写）</p>
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">
                        {modelPreset === "custom" ? <span className="mr-1 text-rose-300">*</span> : null}
                        模型接口 Base URL
                      </label>
                      <input
                        ref={modelBaseUrlInputRef}
                        className={cn(
                          "w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm",
                          modelPreset === "custom" && modelConfigGuideActive && !String(modelBaseUrl || "").trim() && "model-required-guide-input",
                        )}
                        type="text"
                        placeholder="例如: https://api.openai.com/v1"
                        value={modelBaseUrl}
                        required={modelPreset === "custom"}
                        aria-required={modelPreset === "custom"}
                        onChange={(e) => {
                          const nextBaseUrl = e.target.value;
                          setModelPreset("custom");
                          setModelBaseUrl(nextBaseUrl);
                          if (modelConfigGuideActive && nextBaseUrl.trim() && String(modelName || "").trim()) {
                            setModelConfigGuideActive(false);
                          }
                        }}
                      />
                      <p className="text-xs text-neutral-500">支持兼容接口（Ark / OpenAI / DeepSeek / Qwen 等）</p>
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">
                        <span className="mr-1 text-rose-300">*</span>
                        模型名称
                      </label>
                      <input
                        ref={modelNameInputRef}
                        className={cn(
                          "w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm",
                          modelConfigGuideActive && !String(modelName || "").trim() && "model-required-guide-input",
                        )}
                        type="text"
                        placeholder="例如: gpt-5.4 / deepseek-chat / qwen-plus / doubao-seed-2-0-pro-260215"
                        value={modelName}
                        required
                        aria-required
                        onChange={(e) => {
                          const nextModelName = e.target.value;
                          setModelName(nextModelName);
                          const hasBaseUrl = Boolean(String(modelBaseUrl || "").trim());
                          if (modelConfigGuideActive && nextModelName.trim() && (modelPreset !== "custom" || hasBaseUrl)) {
                            setModelConfigGuideActive(false);
                          }
                        }}
                      />
                      <p className="text-xs text-neutral-500">按你所用平台的模型 ID 填写（必填）</p>
                      {modelPreset === "custom" ? <p className="text-xs text-rose-300">自定义预设下，Base URL 与模型名称均必填</p> : null}
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <div className="rounded-lg border border-neutral-700/80 bg-neutral-900/70 px-2.5 py-2 text-xs text-neutral-400">
                        测试链接按钮已停用，模型连通性由后端启动分析时自动处理。
                      </div>
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">Whisper 字幕识别模型</label>
                      <select
                        className="settings-select"
                        value={whisperModel}
                        onChange={(e) => setWhisperModel(e.target.value)}
                      >
                        <option value="tiny">tiny - 最快，精度较低</option>
                        <option value="base">base - 快速，平衡精度</option>
                        <option value="small">small - 中等速度，较高精度</option>
                        <option value="medium">medium - 较慢，更高精度</option>
                        <option value="large">large - 最慢，最高精度</option>
                      </select>
                    </div>

                    <div className="config-field mb-3 space-y-1">
                      <label className="text-sm">AI 看图增强次数</label>
                      <div className="settings-stepper">
                        <input
                          className="settings-number-input"
                          type="number"
                          min={MAX_VISION_MIN}
                          max={MAX_VISION_MAX}
                          value={maxVision}
                          onChange={(e) => handleMaxVisionInput(e.target.value)}
                          onBlur={() => setMaxVision((prev) => clampMaxVision(prev))}
                        />
                        <div className="settings-stepper-controls">
                          <button
                            type="button"
                            className="settings-stepper-btn"
                            aria-label="增加 AI 看图增强次数"
                            onClick={increaseMaxVision}
                            disabled={maxVision >= MAX_VISION_MAX}
                          >
                            ▲
                          </button>
                          <button
                            type="button"
                            className="settings-stepper-btn"
                            aria-label="减少 AI 看图增强次数"
                            onClick={decreaseMaxVision}
                            disabled={maxVision <= MAX_VISION_MIN}
                          >
                            ▼
                          </button>
                        </div>
                      </div>
                      <p className="text-xs text-neutral-500">对低置信度步骤进行 AI 看图增强（0-10 次）</p>
                    </div>

                    <label className="feature-toggle mb-3 flex items-start gap-2 text-sm">
                      <input
                        className="feature-checkbox mt-0.5"
                        type="checkbox"
                        checked={useVideo}
                        onChange={(e) => setUseVideo(e.target.checked)}
                      />
                      <span>
                        <strong className="block font-semibold">视频上传模式</strong>
                        <span className="feature-note text-xs text-neutral-500">直接上传视频给 AI 识别（更准确，费用更高）</span>
                      </span>
                    </label>

                    {useVideo ? (
                      <div className="fps-reveal mb-3 space-y-1">
                        <label className="text-sm">抽帧频率 (FPS)</label>
                        <div className="settings-stepper">
                          <input
                            className="settings-number-input"
                            type="number"
                            min={FPS_MIN}
                            max={FPS_MAX}
                            step={FPS_STEP}
                            value={fps}
                            onChange={(e) => handleFpsInput(e.target.value)}
                            onBlur={() => setFps((prev) => clampFps(prev))}
                          />
                          <div className="settings-stepper-controls">
                            <button
                              type="button"
                              className="settings-stepper-btn"
                              aria-label="增加抽帧频率"
                              onClick={increaseFps}
                              disabled={fps >= FPS_MAX}
                            >
                              ▲
                            </button>
                            <button
                              type="button"
                              className="settings-stepper-btn"
                              aria-label="减少抽帧频率"
                              onClick={decreaseFps}
                              disabled={fps <= FPS_MIN}
                            >
                              ▼
                            </button>
                          </div>
                        </div>
                        <p className="text-xs text-neutral-500">视频上传模式下的抽帧频率，默认 1 帧/秒</p>
                      </div>
                    ) : null}

                  </div>
                </aside>
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

