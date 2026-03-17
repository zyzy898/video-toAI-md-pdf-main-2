
import DOMPurify from "dompurify";
import { marked } from "marked";
import { memo, useCallback, useEffect, useMemo, useRef, useState, type UIEvent } from "react";
import { createPortal } from "react-dom";
import { BackgroundBeams } from "@/components/ui/background-beams";
import { CanvasText } from "@/components/ui/canvas-text";
import { NoiseBackground } from "@/components/ui/noise-background";
import { cn } from "@/lib/utils";

const VALID_VIDEO_EXTENSIONS = new Set([
  "mp4",
  "avi",
  "mov",
  "mkv",
  "wmv",
  "flv",
  "webm",
  "m4v",
  "mpg",
  "mpeg",
  "3gp",
  "ts",
  "m2ts",
]);

const WEB_SEARCH_ERROR_HINTS = ["toolnotopen", "web search", "联网搜索"];
const WEB_SEARCH_ACTIVATION_URL = "https://console.volcengine.com/common-buy/CC_content_plugin";
const ALIYUN_APIKEY_DOC_URL = "https://help.aliyun.com/zh/model-studio/error-code#apikey-error";
const CONTENT_POLICY_BLOCK_MESSAGE =
  "上传已被风控强拦截：检测到高风险色情/裸露/血腥/暴力内容，系统已直接拒绝该视频上传。请删除敏感画面后重试";
const DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024;
const UPLOAD_RESUME_KEY_PREFIX = "video-upload-resume-v1";
const HISTORY_CLIENT_ID_KEY = "video-insights-client-id-v1";
const HISTORY_CLIENT_ID_HEADER = "X-Client-ID";
const ERROR_TOAST_DURATION_MS = 9000;
const ERROR_GUIDE_DURATION_MS = 5200;

const createHistoryClientId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `cid_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
};

const getOrCreateHistoryClientId = () => {
  if (typeof window === "undefined") return "";
  try {
    const stored = window.localStorage.getItem(HISTORY_CLIENT_ID_KEY) || "";
    if (stored) return stored;
    const next = createHistoryClientId();
    window.localStorage.setItem(HISTORY_CLIENT_ID_KEY, next);
    return next;
  } catch {
    return "";
  }
};

const extractRequestId = (message: string) => {
  const match = String(message || "").match(/request[_\s-]*id['"]?\s*[:：]\s*['"]?([A-Za-z0-9._-]+)/i);
  return match?.[1] || "";
};

const extractErrorCode = (message: string) => {
  const match = String(message || "").match(/(?:^|\|)\s*code=([A-Za-z0-9._-]+)/i);
  return String(match?.[1] || "").trim().toLowerCase();
};

const formatContentPolicyViolationMessage = (_message: string, _inline = false) => {
  return CONTENT_POLICY_BLOCK_MESSAGE;
};

const extractModelNameFromNotFound = (message: string) => {
  const match = String(message || "").match(/model or endpoint\s+([A-Za-z0-9._:-]+)/i);
  return match?.[1] || "";
};

const formatModelConnectionError = (message: string) => {
  const lower = String(message || "").toLowerCase();
  const requestId = extractRequestId(message);
  const requestIdText = requestId ? `（请求 ID：${requestId}）` : "";

  if (
    lower.includes("authentication fails") ||
    (lower.includes("your api key") && lower.includes("is invalid")) ||
    (lower.includes("api key") && lower.includes("is invalid"))
  ) {
    return `模型连接失败：API Key 无效，或与当前平台不匹配。请检查 API Key 与 Base URL 是否对应${requestIdText}`;
  }

  if (lower.includes("authenticationerror") || lower.includes("api key format is incorrect")) {
    return `模型连接失败：API Key 格式不正确，请检查密钥后重试${requestIdText}`;
  }

  if (
    lower.includes("invalid_api_key") ||
    lower.includes("incorrect api key provided") ||
    lower.includes("apikey-error")
  ) {
    return `模型连接失败：API Key 无效，或与当前平台不匹配。请检查 API Key 与 Base URL 是否对应（可参考：${ALIYUN_APIKEY_DOC_URL}）${requestIdText}`;
  }

  if (
    lower.includes("invalidendpointormodel.notfound") ||
    lower.includes("does not exist or you do not have access")
  ) {
    const modelName = extractModelNameFromNotFound(message);
    const modelText = modelName ? `（${modelName}）` : "";
    return `模型连接失败：模型或接口不存在，或当前账号无权限访问${modelText}。请检查 Base URL 和模型名称${requestIdText}`;
  }

  return "";
};

const formatRiskHint = (risk?: RiskResult) => {
  if (!risk) return "";
  const level = String(risk.risk_level || "").trim();
  const code = String(risk.reason_code || "").trim();
  const reason = String(risk.reason || "").trim();
  const scoreText = risk.scores
    ? Object.entries(risk.scores)
        .filter(([, value]) => typeof value === "number")
        .map(([key, value]) => `${key}:${Number(value).toFixed(2)}`)
        .join(" / ")
    : "";
  const parts = [level ? `等级: ${level}` : "", code ? `规则: ${code}` : "", reason, scoreText].filter(Boolean);
  return parts.join(" | ");
};

const SEGMENT_ZONE_LABELS: Record<string, string> = {
  standard: "标准区",
  long: "长视频区",
  super_long: "超长区",
  trim_required: "裁剪优先区",
};

const SEGMENT_POLICY_CODE_GUIDES: Record<string, string> = {
  video_segment_trim_required: "当前视频属于裁剪优先区，请先裁剪后再上传或分析。",
  video_segment_super_long_batch_not_allowed: "批量中包含超长视频，建议改为单文件处理。",
  video_segment_long_batch_limit: "包含长视频时，整批最多允许 2 个视频。",
  video_segment_batch_not_allowed: "当前批次不符合分段策略，请按提示拆分或裁剪后重试。",
};

const getSegmentZoneLabel = (zone?: string, fallback?: string) =>
  SEGMENT_ZONE_LABELS[String(zone || "").trim().toLowerCase()] || String(fallback || "").trim() || "未知区";

const formatSegmentPolicyHint = (policy?: SegmentPolicy) => {
  if (!policy) return "";
  const zoneText = getSegmentZoneLabel(policy.zone, policy.zone_label);
  const durationText = String(policy.duration_text || "").trim() || "未知";
  const sizeMb = Number(policy.file_size_mb || 0);
  const sizeText = Number.isFinite(sizeMb) && sizeMb > 0 ? `${sizeMb.toFixed(1)}MB` : "未知大小";
  return `分段策略: ${zoneText}（时长 ${durationText}，大小 ${sizeText}）`;
};

const formatBatchSegmentPolicyHint = (policy?: BatchSegmentPolicy) => {
  if (!policy) return "";
  const total = Number(policy.summary?.total_files || 0);
  const longCount = Number(policy.summary?.long_count || 0);
  const superLongCount = Number(policy.summary?.super_long_count || 0);
  const trimCount = Number(policy.summary?.trim_required_count || 0);
  const parts = [
    total > 0 ? `批次: ${total} 个` : "",
    longCount > 0 ? `长视频 ${longCount}` : "",
    superLongCount > 0 ? `超长 ${superLongCount}` : "",
    trimCount > 0 ? `裁剪优先 ${trimCount}` : "",
  ].filter(Boolean);
  return parts.length > 0 ? `分段策略: ${parts.join(" / ")}` : "";
};

const compactErrorDetail = (message: string) => {
  const parts = String(message || "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !/^code=/i.test(item))
    .filter((item) => !/^等级[:：]/.test(item))
    .filter((item) => !/^规则[:：]/.test(item));
  return parts.slice(0, 2).join("；");
};

const formatSegmentPolicyGuideByCode = (errorCode: string, message: string, requestIdText: string) => {
  const guide = SEGMENT_POLICY_CODE_GUIDES[String(errorCode || "").trim().toLowerCase()];
  if (!guide) return "";
  const detail = compactErrorDetail(message);
  return `${guide}${requestIdText}${detail ? ` ${detail}` : ""}`;
};

const formatErrorMessage = (rawMessage: string) => {
  const message = String(rawMessage || "").trim();
  if (!message) return "操作失败";
  const requestId = extractRequestId(message);
  const requestIdText = requestId ? `（请求 ID：${requestId}）` : "";
  const errorCode = extractErrorCode(message);

  if (errorCode === "risk_model_config_invalid") {
    return `上传前模型配置校验失败：请检查 Base URL 与模型名称是否匹配当前平台，并确认模型支持图片理解（风控检测依赖图片输入）${requestIdText}`;
  }
  if (errorCode === "risk_model_auth_failed") {
    return `上传前模型鉴权失败：请检查 API Key 是否有效，并确认与当前 Base URL/平台匹配${requestIdText}`;
  }
  const segmentPolicyGuide = formatSegmentPolicyGuideByCode(errorCode, message, requestIdText);
  if (segmentPolicyGuide) return segmentPolicyGuide;
  if (errorCode === "content_policy_violation" || message.includes("上传被拒绝")) {
    return formatContentPolicyViolationMessage(message);
  }

  const lower = message.toLowerCase();
  if (WEB_SEARCH_ERROR_HINTS.some((hint) => lower.includes(hint))) {
    return `联网搜索功能未开通。请前往火山引擎控制台开通后重试：${WEB_SEARCH_ACTIVATION_URL}${requestIdText}`;
  }

  const modelConnectionHint = formatModelConnectionError(message);
  if (modelConnectionHint) return modelConnectionHint;

  return message;
};

const formatInlineErrorMessage = (rawMessage: string) => {
  const message = String(rawMessage || "").trim();
  if (!message) return "";
  const requestId = extractRequestId(message);
  const requestIdText = requestId ? `（请求 ID：${requestId}）` : "";
  const errorCode = extractErrorCode(message);

  if (errorCode === "risk_model_config_invalid") {
    return `模型配置校验失败，请检查 Base URL、模型名称与视觉能力${requestIdText}`;
  }
  if (errorCode === "risk_model_auth_failed") {
    return `模型鉴权失败，请检查 API Key 与平台匹配关系${requestIdText}`;
  }
  const segmentPolicyGuide = formatSegmentPolicyGuideByCode(errorCode, message, requestIdText);
  if (segmentPolicyGuide) return segmentPolicyGuide;
  if (errorCode === "content_policy_violation" || message.includes("上传被拒绝")) {
    return formatContentPolicyViolationMessage(message, true);
  }
  const lower = message.toLowerCase();

  if (WEB_SEARCH_ERROR_HINTS.some((hint) => lower.includes(hint))) {
    return requestId ? `联网搜索未开通（请求 ID：${requestId}）` : "联网搜索未开通，请在火山引擎控制台开通后重试";
  }

  const modelConnectionHint = formatModelConnectionError(message);
  if (modelConnectionHint) return modelConnectionHint;

  return message.replace(/\s+/g, " ").trim();
};

const DEGRADE_REASON_LABELS: Record<string, string> = {
  standard_steps_not_detected_subtitle_candidates_generated: "未识别到标准步骤，已根据字幕生成候选步骤",
  subtitle_signal_insufficient_timeline_summary_generated: "字幕信号不足，已自动生成时间线摘要",
  user_requested_summary_only: "已按你的选择仅生成摘要版内容",
  content_generation_failed_emergency_summary_generated: "标准与候选步骤均不可用，已切换紧急摘要保底",
  content_generation_failed: "内容提炼失败，已返回保底结果",
  content_policy_blocked: "内容触发安全策略，已拦截",
};

const formatDegradeReason = (rawReason?: string) => {
  const reason = String(rawReason || "").trim();
  if (!reason) return "标准步骤未稳定提炼，已自动降级输出";
  const mapped = DEGRADE_REASON_LABELS[reason.toLowerCase()];
  if (mapped) return mapped;
  if (/[\u4e00-\u9fa5]/u.test(reason)) return reason;
  return "系统未提炼出高置信度标准步骤，已输出可读保底结果";
};

const formatSegmentPolicyLine = (policy?: SegmentPolicy) => {
  if (!policy) return "";
  const zoneText = getSegmentZoneLabel(policy.zone, policy.zone_label);
  const durationText = String(policy.duration_text || "").trim() || "未知";
  const sizeText =
    typeof policy.file_size_mb === "number" && Number.isFinite(policy.file_size_mb)
      ? `${Number(policy.file_size_mb).toFixed(1)}MB`
      : "未知大小";
  return `${zoneText} · 时长 ${durationText} · 大小 ${sizeText}`;
};

const STAGE_LABELS: Record<string, string> = {
  prepare: "准备中",
  upload: "上传中",
  moderation: "安全检测",
  subtitle: "字幕识别",
  analysis: "内容分析",
  screenshots: "截图生成",
  vision: "视觉增强",
  document: "文档生成",
  pdf: "PDF 生成",
  done: "已完成",
  failed: "失败",
};

const STAGE_PERCENT: Record<string, number> = {
  prepare: 8,
  upload: 35,
  moderation: 70,
  subtitle: 28,
  analysis: 55,
  screenshots: 75,
  vision: 84,
  document: 90,
  pdf: 96,
  done: 100,
  failed: 100,
};

type ModelPreset = "ark" | "openai" | "deepseek" | "qwen" | "custom";

const normalizeModelBaseUrlForSignature = (value: string) =>
  String(value || "").trim().replace(/\/+$/u, "");

const buildModelConfigSignature = (
  apiKey: string,
  modelPreset: ModelPreset,
  modelName: string,
  modelBaseUrl: string,
) =>
  [
    modelPreset,
    String(apiKey || "").trim(),
    String(modelName || "").trim(),
    normalizeModelBaseUrlForSignature(modelBaseUrl),
  ].join("||");

const MODEL_PRESETS: Record<Exclude<ModelPreset, "custom">, { label: string; baseUrl: string }> = {
  ark: {
    label: "Ark (火山引擎)",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
  },
  deepseek: {
    label: "DeepSeek",
    baseUrl: "https://api.deepseek.com/v1",
  },
  qwen: {
    label: "Qwen",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
  },
};

type Mode = "" | "upload" | "single" | "batch";
type FileStatus = "pending" | "processing" | "success" | "failed";

type StepItem = {
  step?: number;
  time?: string;
  title?: string;
  description?: string;
  confidence?: number;
};

type BatchFileItem = {
  filename: string;
  filepath: string;
  status: FileStatus;
  error: string;
};

type RiskResult = {
  decision?: "allow" | "restrict" | "block" | string;
  risk_level?: "low" | "medium" | "high" | string;
  reason_code?: string;
  reason?: string;
  scores?: Partial<Record<"nudity" | "violence" | "gore", number>>;
};

type BlockedNotice = {
  title?: string;
  risk_level?: string;
  reason_code?: string;
  reason?: string;
  suggestions?: string[];
  retry_guidance?: string;
};

type SegmentPolicy = {
  filename?: string;
  zone?: string;
  zone_label?: string;
  duration_seconds?: number | null;
  duration_text?: string;
  file_size_mb?: number;
  allow_upload?: boolean;
  allow_batch?: boolean;
  requires_trim?: boolean;
  recommendations?: string[];
};

type BatchSegmentPolicy = {
  allowed?: boolean;
  code?: string;
  error?: string;
  warnings?: string[];
  summary?: {
    total_files?: number;
    long_count?: number;
    super_long_count?: number;
    trim_required_count?: number;
    total_duration_seconds?: number;
  };
};

type EffectiveOptions = {
  use_video?: boolean;
  web_search?: boolean;
  max_vision?: number;
  summary_only?: boolean;
};

type ApiErrorPayload = {
  error?: string;
  code?: string;
  risk?: RiskResult;
  result_mode?: string;
  quality_score?: number;
  degrade_reason?: string;
  blocked_notice?: BlockedNotice;
  analysis_note?: string;
  segment_policy?: SegmentPolicy;
  batch_segment_policy?: BatchSegmentPolicy;
  file_segment_policies?: SegmentPolicy[];
  batch_policy_warnings?: string[];
};

type SingleResultData = {
  steps: StepItem[];
  markdown: string;
  output_dir: string;
  pdf_path?: string;
  has_steps?: boolean;
  result_mode?: string;
  fallback_used?: boolean;
  analysis_note?: string;
  quality_score?: number;
  degrade_reason?: string;
  content_title?: string;
  key_points?: string[];
  timeline_points?: Array<{ time?: string; text?: string }>;
  confidence_note?: string;
  blocked_notice?: BlockedNotice;
  risk?: RiskResult;
  segment_policy?: SegmentPolicy;
  segment_guardrails?: string[];
  effective_options?: EffectiveOptions;
};

type BatchResultItem = {
  index?: number;
  filename: string;
  success: boolean;
  steps_count?: number;
  output_dir?: string;
  error?: string;
  code?: string;
  risk?: RiskResult;
  result_mode?: string;
  fallback_used?: boolean;
  analysis_note?: string;
  quality_score?: number;
  degrade_reason?: string;
  content_title?: string;
  key_points?: string[];
  timeline_points?: Array<{ time?: string; text?: string }>;
  confidence_note?: string;
  blocked_notice?: BlockedNotice;
  segment_policy?: SegmentPolicy;
  segment_guardrails?: string[];
  effective_options?: EffectiveOptions;
};

type BatchResultData = {
  results: BatchResultItem[];
  batch_segment_policy?: BatchSegmentPolicy;
  batch_policy_warnings?: string[];
  summary?: {
    total?: number;
    success?: number;
    failed?: number;
  };
};

type HistoryItem = {
  id: string;
  video_name: string;
  mode?: string;
  steps_count?: number;
  timestamp?: string;
};

class ApiRequestError extends Error {
  status: number;
  payload: ApiErrorPayload;

  constructor(message: string, status: number, payload: ApiErrorPayload) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.payload = payload;
  }
}

type ProgressBoard = {
  mode: Mode;
  percent: number;
  stage: string;
  total: number;
  current: number;
  success: number;
  failed: number;
  currentFile: string;
};

const DEFAULT_PROGRESS_BOARD: ProgressBoard = {
  mode: "",
  percent: 0,
  stage: "",
  total: 0,
  current: 0,
  success: 0,
  failed: 0,
  currentFile: "",
};

const HERO_TITLE_CANVAS_COLORS = [
  "rgba(0, 153, 255, 1)",
  "rgba(0, 153, 255, 0.9)",
  "rgba(0, 153, 255, 0.8)",
  "rgba(0, 153, 255, 0.7)",
  "rgba(0, 153, 255, 0.6)",
  "rgba(0, 153, 255, 0.5)",
  "rgba(0, 153, 255, 0.4)",
  "rgba(0, 153, 255, 0.3)",
  "rgba(0, 153, 255, 0.2)",
  "rgba(0, 153, 255, 0.1)",
];

const HERO_SUBTITLE_CANVAS_COLORS = [
  "rgba(0, 153, 255, 0.9)",
  "rgba(0, 153, 255, 0.75)",
  "rgba(56, 189, 248, 0.68)",
  "rgba(96, 165, 250, 0.56)",
  "rgba(147, 197, 253, 0.46)",
];

const ANALYZE_BUTTON_GRADIENT_COLORS = [
  "rgb(45, 212, 191)",
  "rgb(56, 189, 248)",
  "rgb(96, 165, 250)",
];

const NEW_STEP_DEFAULT_TITLE = "新步骤";
const NEW_STEP_DEFAULT_DESCRIPTION = "请输入步骤描述";
const NEW_STEP_DEFAULT_TIME = "00:00";
const MAX_VISION_MIN = 0;
const MAX_VISION_MAX = 10;
const FPS_MIN = 0.1;
const FPS_MAX = 10;
const FPS_STEP = 0.1;
const HERO_ANIMATION_TOP_THRESHOLD = 4;

const isValidVideo = (filename: string) => {
  const ext = String(filename || "").split(".").pop()?.toLowerCase() || "";
  return VALID_VIDEO_EXTENSIONS.has(ext);
};

const basename = (value: string | undefined | null) =>
  String(value || "")
    .split(/[\\/]/)
    .filter(Boolean)
    .pop() || "";

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

const isSameProgressBoard = (a: ProgressBoard, b: ProgressBoard) =>
  a.mode === b.mode &&
  a.percent === b.percent &&
  a.stage === b.stage &&
  a.total === b.total &&
  a.current === b.current &&
  a.success === b.success &&
  a.failed === b.failed &&
  a.currentFile === b.currentFile;

function BrandStudioIcon({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M861.44 246.8864a68.266667 68.266667 0 0 1 93.422933 58.965333l0.136534 4.3008 0.477866 232.5504a68.266667 68.266667 0 0 1-89.361066 65.0752l-4.061867-1.467733-157.832533-62.583467a34.133333 34.133333 0 0 1 22.647466-64.341333l2.5088 0.887467 157.832534 62.5664-0.477867-232.533334-157.2864 62.737067a34.133333 34.133333 0 0 1-27.733333-62.327467l2.440533-1.092266 157.2864-62.737067z" fill="currentColor" />
      <path d="M682.666667 119.466667H136.533333a68.266667 68.266667 0 0 0-68.266666 68.266666v477.866667a68.266667 68.266667 0 0 0 68.266666 68.266667h546.133334a68.266667 68.266667 0 0 0 68.266666-68.266667V187.733333a68.266667 68.266667 0 0 0-68.266666-68.266666zM136.533333 187.733333h546.133334v477.866667H136.533333V187.733333z" fill="currentColor" />
      <path d="M242.5344 701.5424a34.133333 34.133333 0 0 1 62.1568 28.091733l-1.092267 2.423467-85.333333 170.666667a34.133333 34.133333 0 0 1-62.1568-28.091734l1.092267-2.423466 85.333333-170.666667zM530.875733 686.267733a34.133333 34.133333 0 0 1 44.509867 12.919467l1.28 2.3552 85.333333 170.666667a34.133333 34.133333 0 0 1-59.784533 32.8704l-1.28-2.3552-85.333333-170.666667a34.133333 34.133333 0 0 1 15.274666-45.789867z" fill="currentColor" />
      <path d="M512 529.066667v34.133333a34.133333 34.133333 0 0 1-34.133333 34.133333H238.933333a34.133333 34.133333 0 0 1-34.133333-34.133333v-34.133333h307.2z" fill="currentColor" />
    </svg>
  );
}

function SettingsIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M571.06 957.11H453.14c-37.5 0-72.68-26.47-83.4-62.14-2.76-5.92-6.63-15.3-9.57-26.78-7.21 5.58-14.28 10.74-22.3 14.76-18.62 9.3-30.34 9.3-43.92 9.3-20.62 0-40.2-9.14-58.21-27.14l-82.55-82.55c-26.3-26.31-30.76-64.5-11.93-102.13l2.33-4.68 3.7-3.7c2.86-2.87 5.91-7.82 9.14-13.17-0.9-0.17-1.8-0.33-2.66-0.48-4.79-0.88-10.75-1.98-13.12-1.98l-7.83-0.97c-37.48-9.37-65.74-45.65-65.74-84.38V453.15c0-38.75 28.27-75.03 65.75-84.4l7.82-0.96c2.37 0 8.33-1.09 13.12-1.98 0.58-0.11 1.18-0.21 1.78-0.33-5.4-7.01-10.4-13.92-14.3-21.72-18.82-37.64-14.36-75.82 11.93-102.13l86.01-80.29c13.76-20.15 40.22-29.4 60.64-29.4 7.58 0 25.31 0 43.93 9.3l4.69 2.34 3.7 3.71c3.91 3.91 8.11 7.14 12.88 10.72 0.26-1.46 0.52-2.88 0.77-4.26 0.88-4.78 1.98-10.74 1.98-13.11l0.96-7.82c9.37-37.48 45.65-65.75 84.4-65.75h117.92c37.49 0 72.67 26.46 83.4 62.13a155.84 155.84 0 0 1 9.57 26.79c7.2-5.57 14.28-10.74 22.3-14.76 18.62-9.3 30.34-9.3 43.92-9.3 20.6 0 40.19 9.14 58.21 27.15l82.53 82.53c26.31 26.3 30.77 64.48 11.95 102.14l-2.34 4.69-3.71 3.7c-2.92 2.93-6.06 8.04-9.36 13.55 5.91 1.18 10.73 2.07 16.01 2.07l7.82 0.96c37.48 9.36 65.74 45.65 65.74 84.4v117.92c0 38.74-28.26 75.02-65.72 84.38l-7.83 0.97c-2.37 0-8.33 1.09-13.12 1.98-0.58 0.11-1.18 0.21-1.78 0.33 4.99 6.49 9.65 12.88 13.4 19.98 17.73 28.37 18.51 74.29-11.06 103.85l-79.72 79.74c-13.66 20.53-40.42 29.95-61.03 29.95-15.6 0-36.95 0-52.31-15.36-3.08-3.07-8.58-6.37-14.4-9.87-0.59-0.35-1.19-0.7-1.78-1.06-0.02 0.11-0.05 0.22-0.07 0.34-1.51 7.57-3.22 16.11-6.57 26.38-9.87 36.85-45.76 64.46-84.05 64.46zM385.1 799.33c0.53 0.18 1.07 0.35 1.61 0.53 6.4 2.13 16.07 5.36 24.41 13.7l9.46 9.46v13.37c0 11.76 4.33 24.61 8.38 32.7l2.46 6.63c2.19 8.79 12.54 16.8 21.72 16.8h117.92c9.17 0 19.52-8.01 21.73-16.81l0.69-2.39c2.31-6.93 3.49-12.85 4.87-19.7 1.57-7.83 3.34-16.7 6.93-27.46l2.41-7.21 5.37-5.38c8.34-8.36 18.02-11.58 24.43-13.72 0.53-0.18 1.06-0.35 1.59-0.53l20.42-20.41 22.83 22.83c3.09 3.09 8.6 6.39 14.43 9.89 7.2 4.32 15.22 9.14 22.8 15.8 4.99 0.37 13.68 0.62 18.26-1.79l1.26-2.51 86.24-86.25c6.24-6.24 5.45-18.73 1.86-24.09l-2.02-3.48c-1.86-3.74-6.32-9.44-11.04-15.49-5.11-6.55-10.75-13.82-16.42-22.32l-14.69-22.02 16.31-16.31c0.17-0.53 0.34-1.06 0.52-1.59 2.13-6.4 5.36-16.07 13.7-24.41l9.46-9.46h13.37c6.79 0 14.73-1.45 22.39-2.86 6.58-1.21 12.89-2.37 19.22-2.83 7.85-3.24 14.53-12.6 14.53-20.97v-117.9c0-8.3-6.56-17.59-14.33-20.89-9.66-0.47-17.81-2.1-24.57-3.45-6.48-1.3-11.6-2.32-17.24-2.32H823l-9.46-9.46c-8.35-8.34-11.56-18.01-13.7-24.42-0.18-0.53-0.35-1.06-0.53-1.59L778.9 370.6l22.85-22.83c3.08-3.08 6.38-8.59 9.88-14.41 4.21-7.01 8.88-14.8 15.26-22.19 6.63-15.63 0.95-21.31-1.58-23.84l-82.53-82.53c-6.08-6.08-10.55-8.23-12.54-8.23-10.06 0-10.06 0-15.03 2.49-3.73 1.86-9.42 6.31-15.45 11.02-6.56 5.12-13.85 10.78-22.36 16.45l-22 14.65-16.3-16.28c-0.53-0.18-1.06-0.34-1.6-0.52-6.41-2.13-16.09-5.36-24.44-13.73l-9.44-9.45v-13.36c0-11.76-4.33-24.62-8.39-32.73l-2.44-6.61c-2.21-8.8-12.56-16.81-21.73-16.81H453.14c-8.38 0-17.73 6.68-20.97 14.53-0.46 6.34-1.62 12.64-2.83 19.22-1.41 7.67-2.86 15.6-2.86 22.4v19.96l-17.85 8.93c-7.97 3.97-14.09 6.01-19.01 7.65-3.14 1.05-6.31 2.05-10.5 4.14l-20.82 10.39-16.44-16.45c-4.27-4.27-8.88-7.73-14.22-11.73-4.96-3.72-10.43-7.83-16.15-12.99-4.14-1.19-8.52-1.19-11.65-1.19-2.22 0-5.69 1.03-7.56 2l-1.51 3.04-92.7 86.51c-1.91 1.94-8.28 8.32 0.97 26.81 1.86 3.74 6.32 9.44 11.03 15.47 5.12 6.56 10.76 13.82 16.42 22.32l14.68 22.01-17.48 17.5c-0.27 0.69-0.54 1.43-0.84 2.23-1.49 3.93-3.28 8.52-6.12 14.2l-8.93 17.85h-19.96c-6.79 0-14.73 1.45-22.39 2.86-6.59 1.21-12.89 2.37-19.23 2.83-7.85 3.24-14.53 12.59-14.53 20.97v117.92c0 8.37 6.68 17.72 14.54 20.97 6.33 0.46 12.64 1.62 19.22 2.83 7.66 1.41 15.6 2.86 22.39 2.86h13.37l9.46 9.46c8.35 8.34 11.57 18.02 13.71 24.42 0.17 0.54 0.34 1.07 0.52 1.6l20.37 20.41-22.8 22.81c-3.08 3.09-6.39 8.6-9.88 14.42-4.22 7.02-8.88 14.81-15.27 22.21-6.63 15.62-0.96 21.31 1.58 23.83l82.53 82.55c6.08 6.07 10.55 8.22 12.54 8.22 10.06 0 10.06 0 15.03-2.49 3.74-1.87 9.45-6.33 15.5-11.04 6.55-5.12 13.8-10.75 22.29-16.42l22.01-14.68 16.3 16.3z m338.47 31.87z m-6.37-4.06z m21.48-2.02zM291.42 199.09z" fill="currentColor" />
      <path d="M512.09 668.22c-84.62 0-156.1-71.49-156.1-156.11 0-84.62 71.49-156.1 156.1-156.1 84.63 0 156.11 71.49 156.11 156.1 0.01 84.63-71.48 156.11-156.11 156.11z m0-247.62c-48.75 0-91.51 42.77-91.51 91.51 0 48.76 42.77 91.52 91.51 91.52 48.76 0 91.52-42.77 91.52-91.52 0.01-48.75-42.76-91.51-91.52-91.51z" fill="currentColor" />
    </svg>
  );
}

function HistoryIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M762.805186 140.938939c-14.335497-9.66922-33.725102-5.887081-43.373857 8.398274-9.648754 14.295588-5.897314 33.714869 8.398274 43.373857 106.369609 71.852468 169.864736 191.267185 169.864736 319.445496 0 212.414831-172.802648 385.217479-385.217479 385.217479S127.259382 724.571397 127.259382 512.156566c0-128.178311 63.494103-247.593028 169.864736-319.445496 14.295588-9.658987 18.047028-29.078269 8.398274-43.373857-9.658987-14.285355-29.088502-18.067494-43.373857-8.398274C138.575102 224.432539 64.791655 363.206162 64.791655 512.156566c0 246.851131 200.834074 447.685205 447.685205 447.685205S960.162066 759.007697 960.162066 512.156566C960.162066 363.206162 886.377596 224.432539 762.805186 140.938939z" fill="currentColor" />
      <path d="M401.003 64.47136c-17.253966 0-31.234375 13.980409-31.234375 31.233352l0 30.470989c0 17.253966 13.980409 31.234375 31.234375 31.234375s31.234375-13.980409 31.234375-31.234375L432.237375 95.704712C432.236352 78.450746 418.256966 64.47136 401.003 64.47136z" fill="currentColor" />
      <path d="M623.950721 64.47136c-17.253966 0-31.233352 13.980409-31.233352 31.233352l0 30.470989c0 17.253966 13.980409 31.234375 31.233352 31.234375s31.234375-13.980409 31.234375-31.234375L655.185097 95.704712C655.184073 78.450746 641.204687 64.47136 623.950721 64.47136z" fill="currentColor" />
      <path d="M426.012603 227.493248c11.214413 18.047028 41.970904 48.589648 86.157265 48.589648 43.963281 0 75.105558-30.318516 86.574774-48.223305 9.222035-14.396895 5.03262-33.358759-9.242502-42.763966-14.304797-9.405207-33.593096-5.398964-43.159986 8.764618-0.132006 0.193405-13.614066 19.754926-34.172287 19.754926-19.989263 0-32.423457-18.098193-33.267685-19.36914-9.160637-14.427594-28.264741-18.799158-42.834574-9.770528C421.416935 193.584973 416.912341 212.841549 426.012603 227.493248z" fill="currentColor" />
      <path d="M510.781242 335.164502c-17.253966 0-31.233352 13.980409-31.233352 31.233352l0 208.225415c0 0.63445 0.149403 1.227967 0.187265 1.853208 0.067538 1.115404 0.148379 2.217505 0.333598 3.314489 0.168846 1.00898 0.416486 1.978051 0.679475 2.951215 0.258896 0.954745 0.529049 1.895163 0.87595 2.821255 0.36839 0.981351 0.801249 1.916653 1.26276 2.847861 0.431835 0.876973 0.880043 1.734504 1.393743 2.569522 0.532119 0.860601 1.115404 1.670036 1.727341 2.472308 0.610914 0.805342 1.235131 1.588171 1.926886 2.336208 0.688685 0.74292 1.424442 1.420349 2.181689 2.093684 0.741897 0.659009 1.484817 1.303692 2.298346 1.89721 0.899486 0.657986 1.850138 1.222851 2.819209 1.783623 0.544399 0.314155 1.00898 0.714268 1.577938 0.998747l208.225415 104.113219c4.484128 2.236947 9.252735 3.304256 13.94971 3.304256 11.44875 0 22.479991-6.334265 27.959795-17.274432 7.706519-15.433504 1.454118-34.192753-13.970176-41.909505l-190.961216-95.480608L542.015617 366.397854C542.015617 349.143888 528.035208 335.164502 510.781242 335.164502z" fill="currentColor" />
    </svg>
  );
}

function CloseIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function EyeIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M2.8 12c1.9-3.9 5.3-6 9.2-6s7.3 2.1 9.2 6c-1.9 3.9-5.3 6-9.2 6s-7.3-2.1-9.2-6Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  );
}

function EyeOffIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M3.3 8.5A12.3 12.3 0 0 0 2.8 12c1.9 3.9 5.3 6 9.2 6 1.7 0 3.3-.4 4.6-1.2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8.3 6.8A9.7 9.7 0 0 1 12 6c3.9 0 7.3 2.1 9.2 6-.6 1.3-1.4 2.4-2.3 3.2"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="m3 3 18 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function RefreshIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M698.569 531.322a39.825 39.825 0 0 0-23.898 7.949c-17.702 13.216-21.34 38.28-8.124 55.982l95.716 128.212c7.854 10.521 19.893 16.073 32.084 16.073a39.825 39.825 0 0 0 23.898-7.949c17.702-13.216 21.34-38.28 8.124-55.982l-95.716-128.212c-7.853-10.521-19.892-16.074-32.084-16.073z" fill="currentColor" />
      <path d="M922.498 563.818a39.825 39.825 0 0 0-23.898 7.949l-128.212 95.716c-17.703 13.216-21.34 38.28-8.124 55.982 7.854 10.521 19.893 16.073 32.084 16.073a39.825 39.825 0 0 0 23.898-7.949l128.212-95.716c17.702-13.216 21.34-38.28 8.124-55.982-7.854-10.521-19.893-16.074-32.084-16.073zM229.652 282.148a39.825 39.825 0 0 0-23.898 7.949c-17.702 13.216-21.34 38.28-8.124 55.982l95.716 128.212c7.854 10.521 19.893 16.073 32.084 16.073a39.825 39.825 0 0 0 23.898-7.949c17.702-13.216 21.34-38.28 8.124-55.982l-95.716-128.212c-7.854-10.521-19.892-16.074-32.084-16.073z" fill="currentColor" />
      <path d="M229.652 282.148a39.825 39.825 0 0 0-23.898 7.949L77.542 385.813c-17.702 13.216-21.34 38.28-8.124 55.982 7.854 10.521 19.893 16.073 32.084 16.073a39.825 39.825 0 0 0 23.898-7.949l128.213-95.716c17.702-13.216 21.34-38.28 8.124-55.982-7.855-10.521-19.893-16.073-32.085-16.073z" fill="currentColor" />
      <path d="M614.968 763.65c-44.13 18.171-94.005 25.121-146.168 16.968C353.747 762.636 261.364 670.253 243.381 555.2c-9.681-61.936 1.932-120.646 28.337-170.344l-58.657-58.657c-40.139 64.442-60.11 142.746-50.806 226.152 17.993 161.306 148.088 291.401 309.394 309.394 62.041 6.92 121.259-2.357 174.048-24.083 26.535-10.921 33.625-45.203 13.335-65.493l-0.098-0.098c-11.555-11.555-28.854-14.643-43.966-8.421zM409.033 260.35c44.131-18.171 94.007-25.122 146.169-16.968 115.051 17.985 207.431 110.365 225.416 225.416 9.682 61.935-1.931 120.646-28.337 170.346l58.658 58.658c40.139-64.443 60.109-142.747 50.805-226.155-17.993-161.305-148.087-291.399-309.391-309.391-62.042-6.92-121.26 2.356-174.05 24.082-26.535 10.921-33.625 45.203-13.335 65.493l0.099 0.099c11.555 11.554 28.854 14.642 43.966 8.42z" fill="currentColor" />
    </svg>
  );
}

function UploadIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M565.333333 779.914667l51.445334-54.912a31.733333 31.733333 0 0 1 45.226666-1.226667 32.64 32.64 0 0 1 1.216 45.770667l-97.418666 104a37.034667 37.034667 0 0 1-52.821334 1.397333l-108.362666-104.202667a32.64 32.64 0 0 1-1.152-45.770666 31.733333 31.733333 0 0 1 45.248-1.173334L501.333333 774.421333V512.074667c0-17.877333 14.325333-32.373333 32-32.373334s32 14.506667 32 32.373334v267.84zM512 138.666667c123.018667 0 228.213333 86.709333 259.424 206.88C864.298667 347.146667 938.666667 426.090667 938.666667 522.688c0 97.6-75.914667 177.173333-170.133334 177.173333-17.674667 0-32-14.496-32-32.373333 0-17.877333 14.325333-32.373333 32-32.373333 58.357333 0 106.133333-50.08 106.133334-112.426667 0-62.336-47.776-112.416-106.133334-112.416-5.856 0-11.626667 0.501333-17.301333 1.482667-17.621333 3.050667-34.304-9.098667-37.024-26.986667C698.346667 280.693333 612.714667 203.424 512 203.424c-73.834667 0-140.928 41.536-177.376 107.861333a31.914667 31.914667 0 0 1-30.122667 16.576 140.373333 140.373333 0 0 0-9.568-0.32c-80.149333 0-145.6 68.586667-145.6 153.781334 0 85.184 65.450667 153.792 145.6 153.792 17.674667 0 32 14.496 32 32.373333 0 17.877333-14.325333 32.373333-32 32.373333C178.912 699.861333 85.333333 601.770667 85.333333 481.322667c0-118.314667 90.293333-215.061333 203.456-218.453334C338.090667 186.24 421.013333 138.666667 512 138.666667z" fill="currentColor" />
    </svg>
  );
}

function FolderPlusIcon({ className = "h-10 w-10" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M693.748069 172.723618H146.000839C77.597461 172.723618 21.95045 228.370629 21.95045 296.774007v603.175604c0 68.403378 55.647011 124.050389 124.050389 124.050389h547.74723c68.403378 0 124.057928-55.647011 124.057929-124.050389V296.774007c0.007539-68.403378-55.647011-124.050389-124.057929-124.050389z m48.673229 727.225993a48.718464 48.718464 0 0 1-48.66569 48.658151H146.000839A48.718464 48.718464 0 0 1 97.342689 899.949611V296.774007a48.718464 48.718464 0 0 1 48.65815-48.65815h547.74723a48.718464 48.718464 0 0 1 48.66569 48.65815v603.175604z" fill="currentColor" />
      <path d="M877.991621 0H330.236852c-68.403378 0-124.057928 55.65455-124.057928 124.057928a37.696119 37.696119 0 1 0 75.392238 0A48.718464 48.718464 0 0 1 330.236852 75.392238h547.754769A48.718464 48.718464 0 0 1 926.657311 124.057928V727.233532a48.718464 48.718464 0 0 1-48.66569 48.658151 37.696119 37.696119 0 1 0 0 75.392238c68.403378 0 124.057928-55.647011 124.057929-124.050389V124.057928C1002.04955 55.65455 946.394999 0 877.991621 0zM599.696252 580.128196L316.997975 416.911539a37.696119 37.696119 0 0 0-56.544179 32.64484v326.433313a37.696119 37.696119 0 0 0 56.544179 32.64484l282.698277-163.209118a37.703658 37.703658 0 0 0 0-65.297218zM335.846035 710.700014V514.846057l169.609919 97.926978-169.609919 97.926979z" fill="currentColor" />
    </svg>
  );
}

function FileVideoIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M915.4048 420.3008c-11.0592 0-21.248-7.2192-24.5248-18.3808a373.1456 373.1456 0 0 0-10.24-30.1568c-5.0688-13.2096 1.4848-28.0064 14.6944-33.0752 13.1584-5.12 28.0064 1.4848 33.0752 14.6944 4.3008 11.1616 8.192 22.6304 11.5712 34.0992 3.9936 13.568-3.7888 27.8016-17.3056 31.7952-2.4576 0.6656-4.864 1.024-7.2704 1.024z" fill="currentColor" />
      <path d="M514.7648 956.0064c-244.3776 0-443.1872-198.8096-443.1872-443.1872S270.3872 69.632 514.7648 69.632c147.8144 0 285.3376 73.3184 367.9744 196.096 7.8848 11.7248 4.7616 27.648-6.9632 35.5328s-27.648 4.7616-35.5328-6.9632c-73.0624-108.5952-194.7648-173.4656-325.4784-173.4656-216.1664 0-391.9872 175.872-391.9872 391.9872 0 216.1664 175.872 391.9872 391.9872 391.9872 216.1664 0 391.9872-175.872 391.9872-391.9872 0-14.1312 11.4688-25.6 25.6-25.6s25.6 11.4688 25.6 25.6c0 244.3776-198.8096 443.1872-443.1872 443.1872z" fill="currentColor" />
      <path d="M439.2448 691.8144c-11.776 0-23.6032-3.1232-34.3552-9.3184-21.504-12.3904-34.304-34.6112-34.304-59.4432V392.3456c0-24.832 12.8512-47.0528 34.3552-59.4432s47.1552-12.3904 68.6592 0l199.7824 115.3536c21.504 12.3904 34.304 34.6112 34.304 59.4432s-12.8512 47.0528-34.304 59.4432L473.6 682.496c-10.752 6.1952-22.528 9.3184-34.3552 9.3184z m0.1024-316.9792c-4.0448 0-7.2192 1.4848-8.8064 2.4064-2.6112 1.536-8.7552 6.0416-8.7552 15.104v230.7072c0 9.1136 6.0928 13.6192 8.7552 15.104s9.5744 4.5568 17.4592 0l199.7824-115.3536c7.8848-4.5568 8.704-12.0832 8.704-15.104s-0.8704-10.5472-8.704-15.104L448 377.2416c-3.1232-1.792-6.0416-2.4064-8.6528-2.4064z" fill="currentColor" />
    </svg>
  );
}

function StatusSuccessIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="m8.4 12.2 2.4 2.4 4.8-5.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StatusFailedIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.8" />
      <path d="m9 9 6 6m0-6-6 6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function PlayIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M266.059294 139.565176l542.117647 331.294118a48.188235 48.188235 0 0 1 0 82.281412l-542.117647 331.294118A48.188235 48.188235 0 0 1 192.752941 843.294118V180.705882a48.188235 48.188235 0 0 1 73.306353-41.140706zM289.129412 266.480941v490.917647l197.812706-120.892235L690.657882 512 486.881882 387.493647 289.069176 266.480941z" fill="currentColor" />
    </svg>
  );
}

function StackIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M704 265.130667l17.024-3.498667c104.96-21.76 153.642667-21.76 153.642667 20.906667 0 96.853333-62.933333 234.666667-149.333334 234.666666h-21.333333V265.088z m42.666667 203.52c43.605333-23.338667 81.92-112.170667 85.12-177.493334a88.96 88.96 0 0 0-10.453334-0.554666c-16.768 0-41.813333 3.114667-74.666666 9.386666v168.704zM320 265.130667l-17.024-3.498667c-104.96-21.76-153.642667-21.76-153.642667 20.906667 0 96.853333 62.933333 234.666667 149.333334 234.666666h21.333333V265.088z m-42.666667 34.858666v168.704c-43.605333-23.381333-81.92-112.213333-85.12-177.578666 2.730667-0.341333 6.229333-0.512 10.453334-0.512 16.768 0 41.813333 3.114667 74.666666 9.386666z m-89.813333-8.106666a4.138667 4.138667 0 0 1-0.426667 0.298666l0.426667-0.256z" fill="currentColor" />
      <path d="M277.333333 256A64 64 0 0 1 341.333333 192h341.333334A64 64 0 0 1 746.666667 256v213.333333c0 117.632-105.173333 234.666667-234.666667 234.666667S277.333333 586.965333 277.333333 469.333333V256z m42.666667 0v213.333333c0 95.018667 87.168 192 192 192s192-96.981333 192-192V256a21.333333 21.333333 0 0 0-21.333333-21.333333H341.333333a21.333333 21.333333 0 0 0-21.333333 21.333333z" fill="currentColor" />
      <path d="M362.666667 469.333333a21.333333 21.333333 0 1 1 42.666666 0 106.666667 106.666667 0 0 0 106.666667 106.666667 21.333333 21.333333 0 1 1 0 42.666667A149.333333 149.333333 0 0 1 362.666667 469.333333z" fill="currentColor" />
      <path d="M490.666667 682.666667h42.666666v170.666666h-42.666666z" fill="currentColor" />
      <path d="M682.666667 832a21.333333 21.333333 0 0 1-21.333334 21.333333h-298.666666a21.333333 21.333333 0 1 1 0-42.666666h298.666666a21.333333 21.333333 0 0 1 21.333334 21.333333z" fill="currentColor" />
    </svg>
  );
}

function DownloadZipIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M853.333333 1024c46.933333 0 85.333333-38.4 85.333334-85.333333v-85.333334h-85.333334v85.333334H170.666667v-85.333334H85.333333v85.333334c0 46.933333 38.4 85.333333 85.333334 85.333333h682.666666zM85.333333 341.333333h85.333334V85.333333h469.333333c4.266667 4.266667 17.066667 17.066667 29.866667 34.133334C729.6 174.933333 836.266667 281.6 853.333333 298.666667v42.666666h85.333334V290.133333c0-21.333333-8.533333-42.666667-25.6-59.733333L708.266667 25.6c-12.8-17.066667-34.133333-25.6-59.733334-25.6H170.666667C123.733333 0 85.333333 38.4 85.333333 85.333333v256z" fill="currentColor" />
      <path d="M938.666667 341.333333H85.333333c-46.933333 0-85.333333 38.4-85.333333 85.333334v341.333333c0 46.933333 38.4 85.333333 85.333333 85.333333h853.333334c46.933333 0 85.333333-38.4 85.333333-85.333333v-341.333333c0-46.933333-38.4-85.333333-85.333333-85.333334z m0 426.666667H85.333333v-341.333333h853.333334v341.333333z" fill="currentColor" />
      <path d="M273.066667 725.333333h187.733333v-51.2H349.866667l110.933333-166.4V469.333333H285.866667v51.2H384l-110.933333 166.4v38.4zM503.466667 725.333333h59.733333v-256h-59.733333v256zM622.933333 725.333333H682.666667v-85.333333h29.866666c55.466667 0 102.4-25.6 102.4-85.333333 0-64-46.933333-81.066667-102.4-81.066667h-89.6V725.333333z m59.733334-132.266666v-72.533334h25.6c29.866667 0 46.933333 8.533333 46.933333 34.133334 0 25.6-12.8 38.4-42.666667 38.4H682.666667z" fill="currentColor" />
    </svg>
  );
}

function DownloadSingleIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M1015.7056 62.1568A102.8096 102.8096 0 0 0 921.6 0h-166.4a38.4 38.4 0 0 0 0 76.8H896a51.2 51.2 0 0 1 51.2 51.2v768a51.2 51.2 0 0 1-51.2 51.2H128a51.2 51.2 0 0 1-51.2-51.2V128a51.2 51.2 0 0 1 51.2-51.2h140.8a38.4 38.4 0 0 0 0-76.8H102.4A102.8096 102.8096 0 0 0 8.2944 62.1568 101.5808 101.5808 0 0 0 0 102.4v819.2a102.7072 102.7072 0 0 0 102.4 102.4h819.2a102.7072 102.7072 0 0 0 102.4-102.4V102.4a101.5808 101.5808 0 0 0-8.2944-40.2432z" fill="currentColor" />
      <path d="M256 742.4m38.4 0l435.2 0q38.4 0 38.4 38.4l0 0q0 38.4-38.4 38.4l-435.2 0q-38.4 0-38.4-38.4l0 0q0-38.4 38.4-38.4Z" fill="currentColor" />
      <path d="M720.128 422.1952l-180.0704 180.0192-0.8704 0.9728a38.1952 38.1952 0 0 1-23.1424 11.008 37.0688 37.0688 0 0 1-7.7824 0 38.1952 38.1952 0 0 1-23.1424-11.008l-0.8704-0.9728-180.3776-180.0192A38.4 38.4 0 0 1 358.4 367.872l115.2 115.4048V38.4a38.4 38.4 0 0 1 76.8 0v444.8768L665.6 367.872a38.4 38.4 0 0 1 54.3232 54.3232z" fill="currentColor" />
    </svg>
  );
}

function StepsIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M852.5824 219.9552H353.6896V280.576h498.8928c14.2336-0.2048 25.7024-15.9744 25.7024-30.3104 0-14.336-11.4688-30.0032-25.7024-30.3104z m-628.6336-48.5376c-43.4176 0-78.6432 35.2256-78.6432 78.6432s35.2256 78.6432 78.6432 78.6432 78.6432-35.2256 78.6432-78.6432-35.2256-78.6432-78.6432-78.6432z m0 104.8576c-14.5408 0-26.2144-11.6736-26.2144-26.2144 0-14.5408 11.6736-26.2144 26.2144-26.2144s26.2144 11.6736 26.2144 26.2144c0 14.5408-11.776 26.2144-26.2144 26.2144z m628.6336 205.824H353.6896V542.72h498.8928c14.2336-0.2048 25.7024-15.9744 25.7024-30.3104 0-14.336-11.4688-30.0032-25.7024-30.3104z m-628.6336-48.5376c-43.4176 0-78.6432 35.2256-78.6432 78.6432s35.2256 78.6432 78.6432 78.6432 78.6432-35.2256 78.6432-78.6432-35.2256-78.6432-78.6432-78.6432z m0 104.8576c-14.5408 0-26.2144-11.6736-26.2144-26.2144 0-14.5408 11.6736-26.2144 26.2144-26.2144s26.2144 11.6736 26.2144 26.2144c0 14.5408-11.776 26.2144-26.2144 26.2144z m0 0M852.5824 744.2432H353.6896V804.864h498.8928c14.2336-0.2048 25.7024-15.9744 25.7024-30.3104s-11.4688-30.0032-25.7024-30.3104z m-628.6336-48.5376c-43.4176 0-78.6432 35.2256-78.6432 78.6432s35.2256 78.6432 78.6432 78.6432 78.6432-35.2256 78.6432-78.6432-35.2256-78.6432-78.6432-78.6432z m0 104.8576c-14.5408 0-26.2144-11.6736-26.2144-26.2144s11.6736-26.2144 26.2144-26.2144 26.2144 11.6736 26.2144 26.2144-11.776 26.2144-26.2144 26.2144z m0 0" fill="currentColor" />
    </svg>
  );
}

function EditIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M882.553 207.403l-66.652-66.652L894.352 62.3s67.244-1.399 67.244 65.845l-79.043 79.258z m-727.882 34.214v627.609H782.28V443.348l89.658-89.658v515.536c0 49.518-40.14 89.658-89.658 89.658H154.671c-49.518 0-89.658-40.14-89.658-89.658V241.617c0-49.518 40.14-89.658 89.658-89.658h515.536l-89.658 89.658H154.671zM378.817 645.08v-67.244l33.622-33.622 67.199 67.199-33.578 33.667h-67.243z m458.965-392.789L502.021 588.967 434.853 521.8l336.219-336.219 66.71 66.71z" fill="currentColor" />
    </svg>
  );
}

function DocumentIcon({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M814.9 264.6L687 142c-11.3-10.8-26.3-16.3-41.5-15.8-0.5 0-1-0.1-1.5-0.1H332.6c-77.4 0-140.4 60.7-140.4 135.2v501.3c0 74.6 63 135.2 140.4 135.2h358.7c77.4 0 140.4-60.7 140.4-135.2V305.3c0.7-15-5.2-29.6-16.8-40.7zM623.1 181c0-13.4 10.8-19.1 14.1-20.5 3-1.3 6.6-2.1 10.5-2.1 5.7 0 11.8 1.9 17.1 6.9l127.9 122.6c6.7 6.4 8.7 15.2 5.3 23.6-2.9 7.1-10.3 14.7-22.7 14.7h-128c-13.4 0-24.2-10.1-24.2-22.6V181z m176.4 581.7c0 56.8-48.5 103-108.2 103H332.6c-59.7 0-108.2-46.2-108.2-103V261.3c0-56.8 48.5-103 108.2-103h263.1c-3.2 6.9-4.9 14.6-4.9 22.6v122.6c0 30.2 25.3 54.8 56.5 54.8h127.9c8.6 0 16.9-1.9 24.3-5.3v409.7z" fill="currentColor" />
      <path d="M498.4 424.9H325.1c-8.9 0-16.1-7.2-16.1-16.1s7.2-16.1 16.1-16.1h173.4c8.9 0 16.1 7.2 16.1 16.1s-7.3 16.1-16.2 16.1zM696.8 559.5H325.1c-8.9 0-16.1-7.2-16.1-16.1s7.2-16.1 16.1-16.1h371.7c8.9 0 16.1 7.2 16.1 16.1s-7.2 16.1-16.1 16.1zM696.8 694.2H325.1c-8.9 0-16.1-7.2-16.1-16.1s7.2-16.1 16.1-16.1h371.7c8.9 0 16.1 7.2 16.1 16.1s-7.2 16.1-16.1 16.1z" fill="currentColor" />
    </svg>
  );
}

function ClearIcon({ className = "h-4 w-4" }: { className?: string }) {
  return (
    <svg viewBox="0 0 1024 1024" fill="none" className={className} aria-hidden="true">
      <path d="M274.56 798.997333l19.434667-25.130666-33.792 68.565333a18.133333 18.133333 0 0 0 11.562666 25.536l59.733334 16a18.133333 18.133333 0 0 0 17.28-4.48c20.522667-19.818667 35.626667-35.989333 45.290666-48.469333l19.456-25.130667-33.813333 68.565333a18.133333 18.133333 0 0 0 11.562667 25.536l84.48 22.634667a18.133333 18.133333 0 0 0 17.28-4.48c20.522667-19.84 35.626667-35.989333 45.269333-48.469333l19.456-25.130667-33.813333 68.565333A18.133333 18.133333 0 0 0 535.530667 938.666667l72.106666 19.328a18.133333 18.133333 0 0 0 17.28-4.48c20.522667-19.84 35.626667-36.010667 45.269334-48.490667l19.456-25.130667-33.813334 68.586667a18.133333 18.133333 0 0 0 11.584 25.514667l86.421334 23.338666 3.84-0.213333c13.269333-0.704 29.056-5.034667 43.84-12.8 29.781333-15.701333 48.170667-43.2 52.181333-78.250667 2.133333-18.517333 4.778667-38.549333 8.405333-63.530666 1.642667-11.221333 2.944-20.010667 6.229334-41.834667 11.050667-73.322667 14.634667-101.034667 17.130666-133.674667l0.938667-12.373333 2.837333-2.922667 12.330667-1.344a41.813333 41.813333 0 0 0 24.810667-11.221333c10.730667-10.24 14.805333-25.386667 11.093333-42.197333l-37.546667-171.584c-3.029333-13.696-11.264-27.946667-23.146666-39.829334-11.648-11.626667-25.92-20.138667-39.893334-23.893333L723.626667 331.306667l-2.261334-3.925334L774.250667 130.133333c8.32-31.061333-11.754667-63.744-44.970667-72.64l-79.509333-21.312c-33.194667-8.896-66.922667 9.365333-75.264 40.426667l-52.842667 197.269333-3.925333 2.261334-118.101334-31.637334c-13.994667-3.754667-30.634667-3.498667-46.506666 0.746667-16.256 4.352-30.506667 12.586667-39.957334 22.933333l-118.314666 129.792c-11.605333 12.714667-15.658667 27.84-11.52 42.090667 4.16 14.229333 15.850667 25.194667 32.896 30.528l13.610666 4.266667 2.133334 3.882666-3.626667 13.802667c-21.12 79.850667-52.885333 136.917333-85.717333 150.890667-47.530667 20.202667-72.938667 49.429333-78.421334 85.034666-5.034667 32.682667 9.28 67.114667 37.589334 91.541334l22.037333 8.341333 74.666667 20.010667a42.666667 42.666667 0 0 0 41.216-11.050667c15.274667-15.274667 26.88-28.032 34.837333-38.293333z m551.381333-396.565333c14.144 3.797333 29.952 19.2 32.768 32l34.56 157.781333a10.666667 10.666667 0 0 1-13.184 12.586667L240.64 433.493333a10.666667 10.666667 0 0 1-5.12-17.493333l108.8-119.36c8.832-9.685333 30.229333-15.146667 44.373333-11.349333l141.333334 37.866666a21.333333 21.333333 0 0 0 26.133333-15.082666l58.304-217.642667a21.333333 21.333333 0 0 1 26.133333-15.082667l77.056 20.650667a21.333333 21.333333 0 0 1 15.082667 26.133333l-58.325333 217.642667a21.333333 21.333333 0 0 0 15.082666 26.112l136.448 36.565333zM315.456 701.568c-33.664 45.141333-64.597333 79.082667-92.8 101.802667l-5.909333 4.778666-2.837334 0.597334-88.106666-24.106667-2.922667-3.2c-13.034667-14.165333-19.370667-31.04-16.981333-46.592 3.285333-21.333333 22.058667-39.338667 53.205333-52.586667 31.722667-13.482667 59.818667-47.104 82.922667-99.904 10.026667-22.954667 18.88-48.725333 26.389333-76.586666l3.882667-14.4 3.904-2.261334 566.165333 151.701334 2.346667 3.306666-0.789334 12.224c-1.984 30.592-30.336 229.397333-32.128 244.906667-2.346667 20.416-11.306667 34.986667-27.605333 44.394667a73.237333 73.237333 0 0 1-21.397333 8.106666l-5.013334 0.725334-60.373333-16.170667 11.242667-20.288c8.277333-14.976 22.656-43.84 43.093333-86.613333a21.12 21.12 0 0 0-9.962667-28.16l-3.136-1.493334a21.333333 21.333333 0 0 0-26.261333 6.485334c-33.642667 45.056-64.533333 78.912-92.672 101.546666l-5.909333 4.757334-2.837334 0.597333-52.544-14.08 11.114667-20.266667c3.562667-6.485333 7.04-13.013333 10.453333-19.626666 7.04-13.504 17.898667-35.797333 32.597334-66.816a21.290667 21.290667 0 0 0-9.984-28.309334l-3.029334-1.450666a21.333333 21.333333 0 0 0-26.368 6.442666c-33.6 45.013333-64.469333 78.826667-92.608 101.482667l-5.909333 4.757333-2.837333 0.597334-52.138667-13.973334 11.114667-20.266666c3.242667-5.888 6.72-12.416 10.453333-19.626667 6.997333-13.461333 17.962667-35.946667 32.896-67.434667a20.970667 20.970667 0 0 0-10.112-28.010666l-3.328-1.536a21.333333 21.333333 0 0 0-26.069333 6.613333c-33.642667 45.056-64.554667 78.976-92.778667 101.696l-5.909333 4.757333-2.837334 0.597334-32.64-8.746667 11.093334-20.245333c3.541333-6.506667 7.04-13.034667 10.453333-19.626667 6.976-13.482667 17.941333-35.968 32.874667-67.456a21.056 21.056 0 0 0-10.069334-28.074667l-3.242666-1.514666a21.333333 21.333333 0 0 0-26.154667 6.549333z" fill="currentColor" />
    </svg>
  );
}

function TrashIcon({ className = "h-3.5 w-3.5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M4 7h16" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M9 7V5.5A1.5 1.5 0 0 1 10.5 4h3A1.5 1.5 0 0 1 15 5.5V7" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M7 7.5 8 19a2 2 0 0 0 2 1.8h4a2 2 0 0 0 2-1.8l1-11.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M10 11v6M14 11v6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function HistoryEmptyIllustration({ className = "h-24 w-24" }: { className?: string }) {
  return (
    <svg viewBox="0 0 128 128" fill="none" className={className} aria-hidden="true">
      <defs>
        <linearGradient id="history-empty-bg" x1="20" y1="16" x2="102" y2="108" gradientUnits="userSpaceOnUse">
          <stop stopColor="#22d3ee" stopOpacity="0.28" />
          <stop offset="1" stopColor="#60a5fa" stopOpacity="0.1" />
        </linearGradient>
        <linearGradient id="history-empty-card" x1="36" y1="30" x2="88" y2="88" gradientUnits="userSpaceOnUse">
          <stop stopColor="#a5f3fc" stopOpacity="0.95" />
          <stop offset="1" stopColor="#67e8f9" stopOpacity="0.7" />
        </linearGradient>
      </defs>
      <circle cx="64" cy="64" r="52" fill="url(#history-empty-bg)" />
      <rect x="36" y="30" width="56" height="68" rx="11" fill="url(#history-empty-card)" />
      <rect x="44" y="45" width="40" height="6" rx="3" fill="#0f172a" fillOpacity="0.34" />
      <rect x="44" y="58" width="31" height="6" rx="3" fill="#0f172a" fillOpacity="0.24" />
      <rect x="44" y="71" width="36" height="6" rx="3" fill="#0f172a" fillOpacity="0.24" />
      <path d="M64 90c12.15 0 22-9.85 22-22" stroke="#0f172a" strokeOpacity="0.34" strokeWidth="4" strokeLinecap="round" />
      <circle cx="64" cy="68" r="3.5" fill="#0f172a" fillOpacity="0.48" />
      <path d="m96 26 5 5m0-5-5 5" stroke="#67e8f9" strokeWidth="2.2" strokeLinecap="round" />
      <path d="m27 93 4 4m0-4-4 4" stroke="#7dd3fc" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  );
}

const EMPTY_STEPS: StepItem[] = [];
const HISTORY_VIRTUAL_ITEM_HEIGHT = 74;
const HISTORY_VIRTUAL_OVERSCAN = 6;

const ReadonlyStepsList = memo(function ReadonlyStepsList({ steps }: { steps: StepItem[] }) {
  return (
    <div className="space-y-2">
      {steps.map((step, i) => (
        <div key={`s-${i}`} className="rounded border border-neutral-800 bg-neutral-950/60 p-2">
          <p className="text-xs text-neutral-500">
            #{step.step || i + 1} · {step.time || "00:00"}
          </p>
          <p className="text-sm font-medium">{step.title || "未命名步骤"}</p>
          <p className="text-sm text-neutral-300">{step.description || ""}</p>
        </div>
      ))}
    </div>
  );
});

type VirtualizedHistoryListProps = {
  active: boolean;
  history: HistoryItem[];
  clearingHistory: boolean;
  deletingHistoryId: string;
  onOpenRecord: (id: string) => void;
  onDeleteRecord: (record: HistoryItem) => void;
};

const VirtualizedHistoryList = memo(function VirtualizedHistoryList({
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

  const totalHeight = useMemo(() => history.length * HISTORY_VIRTUAL_ITEM_HEIGHT, [history.length]);

  const startIndex = useMemo(
    () => Math.max(0, Math.floor(scrollTop / HISTORY_VIRTUAL_ITEM_HEIGHT) - HISTORY_VIRTUAL_OVERSCAN),
    [scrollTop],
  );

  const endIndex = useMemo(() => {
    const visibleCount = Math.ceil((viewportHeight || 1) / HISTORY_VIRTUAL_ITEM_HEIGHT) + HISTORY_VIRTUAL_OVERSCAN * 2;
    return Math.min(history.length, startIndex + visibleCount);
  }, [history.length, startIndex, viewportHeight]);

  const visibleItems = useMemo(() => history.slice(startIndex, endIndex), [endIndex, history, startIndex]);

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
    <div ref={containerRef} className="history-scroll flex-1 overflow-auto px-4 py-3" onScroll={handleScroll}>
      <div className="relative" style={{ height: `${totalHeight}px` }}>
        {visibleItems.map((record, offset) => {
          const index = startIndex + offset;
          return (
            <div
              key={record.id}
              className="history-virtual-item absolute left-0 right-0"
              style={{ top: `${index * HISTORY_VIRTUAL_ITEM_HEIGHT}px`, paddingBottom: "8px" }}
            >
              <div className="list-item-pop rounded border border-neutral-800 bg-neutral-950/60 p-2">
                <div className="flex items-start justify-between gap-2">
                  <button className="min-w-0 flex-1 text-left" onClick={() => onOpenRecord(record.id)}>
                    <p className="truncate text-sm font-medium">{record.video_name}</p>
                    <p className="truncate text-xs text-neutral-500">
                      {record.mode === "video" ? "视频模式" : "字幕模式"} · {record.steps_count || 0} 步 · {record.timestamp || ""}
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

const MarkdownPreview = memo(function MarkdownPreview({
  html,
  className,
  contentClassName,
}: {
  html: string;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <div
      className={cn(
        "history-scroll max-h-[min(62vh,40rem)] overflow-auto pr-1 xl:h-[min(62vh,40rem)]",
        className,
      )}
    >
      <div
        className={cn("prose prose-invert max-w-none text-sm", contentClassName)}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
});



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

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [savingSteps, setSavingSteps] = useState(false);
  const [testingModel, setTestingModel] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [deletingHistoryId, setDeletingHistoryId] = useState("");
  const [pendingDeleteHistory, setPendingDeleteHistory] = useState<HistoryItem | null>(null);
  const [showClearHistoryConfirm, setShowClearHistoryConfirm] = useState(false);
  const [historyDrawerOpen, setHistoryDrawerOpen] = useState(false);
  const [settingsDrawerOpen, setSettingsDrawerOpen] = useState(false);
  const [apiKeyGuideActive, setApiKeyGuideActive] = useState(false);
  const [modelConfigGuideActive, setModelConfigGuideActive] = useState(false);
  const [modelTestGuideActive, setModelTestGuideActive] = useState(false);

  const [batchFiles, setBatchFiles] = useState<BatchFileItem[]>([]);
  const [resultData, setResultData] = useState<SingleResultData | null>(null);
  const [batchResultData, setBatchResultData] = useState<BatchResultData | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);

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

  const fileInputRef = useRef<HTMLInputElement | null>(null);
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

  useEffect(() => {
    progressVisibleRef.current = progressVisible;
  }, [progressVisible]);

  useEffect(() => {
    batchFilesRef.current = batchFiles;
  }, [batchFiles]);

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
  }, []);

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

    const isUploadRiskUnavailable =
      rawMessage.includes("上传风控服务不可用") || rawMessage.includes("code=risk_service_unavailable");
    const isApiKeyMissing =
      rawMessage.includes("请输入 ARK API Key") ||
      rawMessage.includes("请输入 API Key") ||
      rawMessage.includes("code=risk_model_auth_failed");
    const isModelConfigMissing =
      rawMessage.includes("请填写模型名称") ||
      rawMessage.includes("请填写模型接口 Base URL") ||
      rawMessage.includes("模型连接失败：模型或接口不存在") ||
      rawMessage.includes("code=risk_model_config_invalid");
    const needApiGuide = isUploadRiskUnavailable || isApiKeyMissing;
    const needModelGuide = isUploadRiskUnavailable || isModelConfigMissing;

    if (needApiGuide || needModelGuide) {
      setHistoryDrawerOpen(false);
      setSettingsDrawerOpen(true);

      if (needApiGuide) {
        setApiKeyGuideActive(true);

        if (apiKeyGuideTimerRef.current) clearTimeout(apiKeyGuideTimerRef.current);
        apiKeyGuideTimerRef.current = setTimeout(
          () => setApiKeyGuideActive(false),
          ERROR_GUIDE_DURATION_MS,
        );
      }

      if (needModelGuide) {
        setModelConfigGuideActive(true);
        if (modelConfigGuideTimerRef.current) clearTimeout(modelConfigGuideTimerRef.current);
        modelConfigGuideTimerRef.current = setTimeout(
          () => setModelConfigGuideActive(false),
          ERROR_GUIDE_DURATION_MS,
        );
      }

      if (needApiGuide) {
        if (apiKeyGuideFocusTimerRef.current) clearTimeout(apiKeyGuideFocusTimerRef.current);
        apiKeyGuideFocusTimerRef.current = setTimeout(() => {
          apiKeyInputRef.current?.focus();
          apiKeyInputRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 220);
      } else if (needModelGuide) {
        if (modelConfigGuideFocusTimerRef.current) clearTimeout(modelConfigGuideFocusTimerRef.current);
        modelConfigGuideFocusTimerRef.current = setTimeout(() => {
          const missingBaseUrl = modelPreset === "custom" && !String(modelBaseUrl || "").trim();
          const missingModelName = !String(modelName || "").trim();
          const target = missingBaseUrl
            ? modelBaseUrlInputRef.current
            : missingModelName
              ? modelNameInputRef.current
              : modelNameInputRef.current;
          target?.focus();
          target?.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 220);
      }
    }
  }, [modelBaseUrl, modelName, modelPreset]);

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
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 220);
  }, [modelBaseUrl, modelName, modelPreset]);

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
      modelTestButtonRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 260);
  }, []);

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
    if (!apiKey) {
      showError("请输入 API Key");
      return false;
    }
    if (!validateModelConfig()) return false;
    const currentSignature = buildModelConfigSignature(apiKey, modelPreset, modelName, modelBaseUrl);
    if (verifiedModelConfigSignatureRef.current === currentSignature) return true;
    if (!settingsDrawerOpen) triggerModelTestGuide();

    setTestingModel(true);
    try {
      await fetchJson("/test_model", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
        }),
      });
      verifiedModelConfigSignatureRef.current = currentSignature;
      return true;
    } catch (error) {
      const message = String((error as Error).message || error);
      showError(`上传前模型校验失败：${pickUploadPrecheckError(message)}`);
      return false;
    } finally {
      setTestingModel(false);
    }
  }, [
    apiKey,
    fetchJson,
    modelBaseUrl,
    modelName,
    modelPreset,
    pickUploadPrecheckError,
    settingsDrawerOpen,
    showError,
    triggerModelTestGuide,
    validateModelConfig,
  ]);

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
    singleTimerRef.current = setInterval(() => void pullSingleProgress(), 5000);
  }, [pullSingleProgress, stopSinglePolling]);

  const startBatchPolling = useCallback(() => {
    stopBatchPolling();
    void pullBatchProgress();
    batchTimerRef.current = setInterval(() => void pullBatchProgress(), 5000);
  }, [pullBatchProgress, stopBatchPolling]);

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
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
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
    [apiKey, fetchJson, modelBaseUrl, modelName, setProgressTextIfChanged],
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
              message = formatContentPolicyViolationMessage("", true);
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
  const analyzeSingle = useCallback(async () => {
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length !== 1) return;
    const file = analyzableFiles[0];
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
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
          filepath: file.filepath,
          whisper_model: whisperModel,
          use_video: useVideo,
          web_search: webSearch,
          max_vision: maxVision,
          fps,
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
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [
    apiKey,
    fetchJson,
    fps,
    hideProgress,
    loadHistory,
    maxVision,
    modelBaseUrl,
    modelName,
    showError,
    showSuccess,
    showProgress,
    startSinglePolling,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    useVideo,
    webSearch,
    whisperModel,
    getAnalyzableBatchFiles,
    summaryOnly,
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
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
          filepaths: analyzableFiles.map((item) => item.filepath),
          whisper_model: whisperModel,
          use_video: useVideo,
          web_search: webSearch,
          max_vision: maxVision,
          fps,
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
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [
    apiKey,
    fetchJson,
    fps,
    hideProgress,
    loadHistory,
    maxVision,
    modelBaseUrl,
    modelName,
    countBatchStatus,
    showError,
    showProgress,
    startBatchPolling,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    useVideo,
    webSearch,
    whisperModel,
    getAnalyzableBatchFiles,
    summaryOnly,
  ]);

  const startAnalyze = useCallback(async () => {
    if (!apiKey) {
      showError("请输入 API Key");
      return;
    }
    if (!validateModelConfig()) return;
    const analyzableFiles = getAnalyzableBatchFiles();
    if (analyzableFiles.length === 1) return analyzeSingle();
    if (analyzableFiles.length > 1) return analyzeBatch();
    if (batchFilesRef.current.length > 0) {
      showError("没有可分析的视频，请查看失败原因后重试上传。");
      return;
    }
    showError("请先上传视频文件");
  }, [analyzeBatch, analyzeSingle, apiKey, getAnalyzableBatchFiles, showError, validateModelConfig]);

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
          pdf_path: record.pdf_path || "",
          has_steps: Boolean(record.steps && Array.isArray(record.steps) && record.steps.length > 0),
          result_mode: String(record.result_mode || ""),
          fallback_used: Boolean(record.fallback_used),
          analysis_note: String(record.analysis_note || ""),
          quality_score: Number(record.quality_score || 0),
          degrade_reason: String(record.degrade_reason || ""),
          content_title: String(record.content_title || ""),
          confidence_note: String(record.confidence_note || ""),
        });
        setBatchResultData(null);
        if (resultsRef.current) {
          resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (error) {
        showError(`加载历史失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [fetchJson, hideProgress, showError, showProgress],
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
    if (!apiKey) return showError("请输入 API Key");
    if (!validateModelConfig()) return;
    if (!resultData?.output_dir) return showError("缺少输出目录信息");
    setSavingSteps(true);
    showProgress("重新生成中", "根据编辑步骤生成新文档...");

    const requestRegenerate = async (enableWebSearch: boolean) =>
      fetchJson<SingleResultData>("/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          model_name: modelName,
          model_base_url: modelBaseUrl,
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
  }, [apiKey, editedSteps, fetchJson, hideProgress, modelBaseUrl, modelName, resultData?.output_dir, showError, showProgress, validateModelConfig, webSearch]);

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
  const canAnalyze = !isAnalyzing && analyzableBatchCount > 0;
  const analyzeButtonText = isAnalyzing
    ? analyzableBatchCount === 1
      ? "单文件处理中..."
      : "批量处理中..."
    : analyzableBatchCount === 1
      ? "开始单文件分析"
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
  const heroCanvasAnimating = !drawerOverlayActive && heroAnimationActive;
  const handleStudioClick = useCallback(() => {
    if (typeof window === "undefined") return;

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
  }, []);

  return (
    <div className="app-root relative min-h-screen bg-neutral-950 text-neutral-100">
      <div className="pointer-events-none absolute inset-0">
        <BackgroundBeams className="opacity-70" />
      </div>
      <nav className="fixed inset-x-0 top-0 z-40 w-full border-y border-neutral-800 bg-neutral-900/80 backdrop-blur-md">
        <div className="mx-auto flex min-h-[52px] w-full max-w-[1320px] items-center justify-between px-4 sm:px-6 md:px-8">
          <button
            type="button"
            onClick={handleStudioClick}
            className="brand-nav-btn inline-flex items-center gap-1.5 rounded-sm text-sm font-bold uppercase tracking-[0.14em] text-neutral-400 transition-colors hover:text-neutral-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/70"
          >
            <span className="brand-nav-icon-wrap" aria-hidden="true">
              <img src="/vite.ico" alt="" className="brand-nav-icon" />
            </span>
            <span>Video Insights</span>
          </button>
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-expanded={historyDrawerOpen}
              aria-controls="history-drawer"
              onClick={() => {
                setSettingsDrawerOpen(false);
                setHistoryDrawerOpen((prev) => !prev);
              }}
              className="history-nav-btn inline-flex items-center gap-1.5 rounded-full bg-neutral-900/60 px-3 py-1.5 text-base font-medium text-neutral-200 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
            >
              <HistoryIcon className="h-3.5 w-3.5" />
              历史
            </button>
            <button
              type="button"
              aria-expanded={settingsDrawerOpen}
              aria-controls="settings-drawer"
              onClick={() => {
                setHistoryDrawerOpen(false);
                setSettingsDrawerOpen((prev) => !prev);
              }}
              className="history-nav-btn inline-flex items-center gap-1.5 rounded-full bg-neutral-900/60 px-3 py-1.5 text-base font-medium text-neutral-200 transition-colors hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-500/60"
            >
              <SettingsIcon className="h-3.5 w-3.5" />
              设置
            </button>
          </div>
        </div>
      </nav>
      <main className="app-main relative z-10 mx-auto w-full max-w-[1320px] space-y-6 px-4 pb-8 pt-[5.25rem] sm:px-6 md:space-y-7 md:px-8 md:pb-10 md:pt-24">
        <header className="hero-panel panel-card motion-enter rounded-xl border-0 bg-transparent p-4">
          <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-3 text-center">
            <div className="hero-icon-float rounded-full border border-neutral-700 bg-neutral-950/70 p-2 text-neutral-300">
              <BrandStudioIcon className="h-8 w-8" />
            </div>
            <h1
              className={cn(
                "group relative mx-auto max-w-2xl text-balance text-center text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl xl:text-7xl",
              )}
            >
              视频转文档 
              <CanvasText
                text=" 不止是提取   更是理解"
                className="hero-toast-anchor inline align-middle"
                backgroundClassName="bg-blue-600 dark:bg-blue-700"
                colors={HERO_TITLE_CANVAS_COLORS}
                animating={heroCanvasAnimating}
                lineGap={4}
                animationDuration={20}
              />
            </h1>
            <p className="mx-auto max-w-3xl text-balance text-center text-sm font-medium text-neutral-300 sm:text-base md:text-lg">
              AI 自动分析视频内容，抓取关键截图，拆解核心步骤，输出结构清晰、重点明确的总结文档。
            </p>
            <p className="mx-auto max-w-3xl text-balance text-center text-sm font-medium text-neutral-300 sm:text-base">
              <CanvasText
                text="让信息沉淀更高效，Turn insights into docs。"
                className="inline align-middle"
                backgroundClassName="bg-blue-600/80 dark:bg-blue-700/80"
                colors={HERO_SUBTITLE_CANVAS_COLORS}
                animating={heroCanvasAnimating}
                lineGap={4}
                animationDuration={22}
              />
            </p>
            <div className="mt-2 flex flex-wrap justify-center gap-2">
              <span className="hero-chip rounded-full border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300">Whisper</span>
              <span className="hero-chip rounded-full border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300">Batch Ready</span>
              <span className="hero-chip rounded-full border border-neutral-700 px-2.5 py-1 text-xs text-neutral-300">Markdown + PDF</span>
            </div>
          </div>
        </header>

        <div className="app-grid grid items-start gap-5 2xl:gap-6">
          <section className="app-workspace motion-enter motion-delay-2 min-w-0 space-y-4">
            <section className="panel-card rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
              <div className="mb-2 flex items-center gap-2">
                <UploadIcon className="h-4 w-4 text-neutral-300" />
                <h2 className="text-base font-semibold">上传视频</h2>
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
                className={`rounded border-2 border-dashed p-5 text-center ${
                  batchDragOver ? "border-teal-400 bg-teal-500/10" : "border-neutral-700 bg-neutral-950/50"
                } upload-dropzone`}
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
                <div className="mb-2 flex justify-center text-neutral-300">
                  <FolderPlusIcon className="h-12 w-12" />
                </div>
                <p>点击选择单个/多个视频文件</p>
                <p className="mt-1 text-xs text-neutral-500">支持 MP4, AVI, MOV, MKV, WMV, FLV, WebM, M4V 等格式</p>
              </div>
              <div className="mt-2 rounded-lg border border-sky-400/30 bg-sky-500/8 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold tracking-wide text-sky-100/95">上传策略建议</p>
                  <span className="rounded-full border border-sky-300/35 bg-sky-500/15 px-2 py-0.5 text-[11px] text-sky-100/90">
                    稳定性优先
                  </span>
                </div>
                <div className="grid gap-2 sm:grid-cols-2">
                  <div className="rounded-md border border-sky-300/20 bg-sky-500/10 p-2">
                    <p className="text-[11px] font-medium text-sky-200/95">标准推荐</p>
                    <p className="mt-1 text-xs leading-5 text-sky-100/95">
                      推荐上传 20 分钟以内、250MB 以内的视频，处理速度和稳定性最佳。
                    </p>
                  </div>
                  <div className="rounded-md border border-sky-300/20 bg-sky-500/10 p-2">
                    <p className="text-[11px] font-medium text-sky-200/95">长视频模式</p>
                    <p className="mt-1 text-xs leading-5 text-sky-100/95">
                      20 分钟以上或 250MB 以上的视频会自动进入长视频处理模式，系统将进行切片/压缩后再分析，耗时会明显增加。
                    </p>
                  </div>
                  <div className="rounded-md border border-sky-300/20 bg-sky-500/10 p-2">
                    <p className="text-[11px] font-medium text-sky-200/95">超长视频建议</p>
                    <p className="mt-1 text-xs leading-5 text-sky-100/95">
                      45 分钟以上的视频建议先按章节裁剪后再上传；90 分钟以上的超长视频请拆分后上传，以保证处理稳定性。
                    </p>
                  </div>
                  <div className="rounded-md border border-sky-300/20 bg-sky-500/10 p-2">
                    <p className="text-[11px] font-medium text-sky-200/95">批量建议</p>
                    <p className="mt-1 text-xs leading-5 text-sky-100/95">
                      批量上传建议最多 5 个视频；若包含长视频，建议最多 2 个。
                    </p>
                  </div>
                </div>
              </div>
              <div className="mt-2 space-y-2">
                {batchFiles.map((item, index) => (
                  <div
                    key={`${item.filepath}-${index}`}
                    className={cn(
                      "flex items-start justify-between rounded border p-2 transition-colors",
                      item.status === "failed"
                        ? "border-rose-500/45 bg-rose-500/12"
                        : "border-neutral-800 bg-neutral-950/60",
                    )}
                  >
                    <div
                      className={cn(
                        "min-w-0 flex flex-1 items-start gap-2 rounded-md px-1 py-0.5 transition-colors",
                        "bg-transparent",
                      )}
                    >
                      <FileVideoIcon
                        className={cn(
                          "mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-400 transition-[color,transform,filter] duration-300 ease-out",
                          item.status === "success" && "text-emerald-300 drop-shadow-[0_0_6px_rgba(52,211,153,0.35)]",
                          item.status === "failed" && "text-rose-300 drop-shadow-[0_0_6px_rgba(244,63,94,0.32)]",
                        )}
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm">{item.filename}</p>
                        <p className={cn("text-xs", item.status === "failed" ? "text-rose-300/90" : "text-neutral-500")}>
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
                      {(item.status === "success" || item.status === "failed") && (
                        <span
                          className={cn(
                            "file-status-chip",
                            item.status === "success" ? "file-status-chip-success" : "file-status-chip-failed",
                          )}
                        >
                          {item.status === "success" ? <StatusSuccessIcon /> : <StatusFailedIcon />}
                          <span>{item.status === "success" ? "成功" : "失败"}</span>
                        </span>
                      )}
                      {batchFiles.length > 1 ? (
                        <button
                          type="button"
                          title="删除文件"
                          aria-label="删除文件"
                          className="inline-flex h-7 w-7 items-center justify-center rounded border border-rose-500/40 text-rose-300 transition-colors hover:bg-rose-500/10"
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
                  className="clear-list-btn mt-2 flex w-full items-center justify-center gap-1 rounded border border-neutral-700 px-3 py-1.5 text-sm"
                  onClick={() => setBatchFiles([])}
                >
                  <ClearIcon className="clear-list-icon h-3.5 w-3.5" />
                  清空列表
                </button>
              ) : null}
              <NoiseBackground
                containerClassName="mt-3 mx-auto w-full rounded-full bg-neutral-950/95 p-2 ring-1 ring-white/5"
                className="w-full"
                gradientColors={ANALYZE_BUTTON_GRADIENT_COLORS}
                noiseIntensity={0.07}
                speed={0.13}
                animating={!drawerOverlayActive}
              >
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
              </NoiseBackground>
              <button
                type="button"
                className={`mt-2 w-full rounded border px-3 py-1.5 text-xs transition-colors ${
                  summaryOnly
                    ? "border-amber-400/60 bg-amber-500/15 text-amber-200"
                    : "border-neutral-700 text-neutral-300 hover:border-amber-400/45 hover:text-amber-200"
                }`}
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
                      <button
                        ref={modelTestButtonRef}
                        type="button"
                        className={cn(
                          "history-refresh-btn flex w-full items-center justify-center gap-1 rounded-lg border border-neutral-700 px-2.5 py-2 text-xs font-medium",
                          modelTestGuideActive && "model-test-guide-btn",
                        )}
                        disabled={testingModel}
                        aria-busy={testingModel}
                        onClick={() => {
                          if (modelTestGuideActive) setModelTestGuideActive(false);
                          void testModelConnection();
                        }}
                      >
                        <RefreshIcon className={`h-3.5 w-3.5 ${testingModel ? "history-refresh-icon-spin" : ""}`} />
                        {testingModel ? "测试中..." : "测试链接"}
                      </button>
                      <p className="text-xs text-neutral-500">测试当前参数是否可连通模型（API Key / Base URL / 模型名称）</p>
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
          <div className="progress-dialog-anim w-full max-w-md rounded-xl border border-neutral-700 bg-neutral-900 p-4">
            <h3 className="text-base font-semibold">{progressTitle}</h3>
            <p className="mt-1 text-sm text-neutral-300">{progressText}</p>
            <div className="mt-3 rounded border border-neutral-800 bg-neutral-950/70 p-3">
              <div className="mb-1 flex items-center justify-between text-xs text-neutral-400"><span>{progressModeText}</span><span>{progressPercent}%</span></div>
              <div className="h-2 overflow-hidden rounded bg-neutral-800"><div className="progress-fill-anim h-full bg-teal-500" style={{ width: `${progressPercent}%` }} /></div>
              {progressBoard.total > 0 ? <p className="mt-1 text-xs text-neutral-400">进度 {progressBoard.current}/{progressBoard.total}</p> : null}
              {progressBoard.success > 0 || progressBoard.failed > 0 ? <p className="text-xs text-neutral-400">成功 {progressBoard.success} · 失败 {progressBoard.failed}</p> : null}
              {progressBoard.stage ? (
                <p className="text-xs text-neutral-400">
                  阶段: {progressBoard.stage === "idle" ? "正在准备分析..." : STAGE_LABELS[progressBoard.stage] || progressBoard.stage}
                </p>
              ) : (
                <p className="text-xs text-neutral-400">阶段: 正在准备分析...</p>
              )}
              {progressBoard.currentFile ? <p className="truncate text-xs text-teal-300">当前文件: {progressBoard.currentFile}</p> : null}
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

