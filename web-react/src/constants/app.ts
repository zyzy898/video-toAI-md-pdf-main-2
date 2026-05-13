import type { ModelPreset, ProgressBoard, StepItem } from "../types/api";

export const VALID_VIDEO_EXTENSIONS = new Set([
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

export const WEB_SEARCH_ERROR_HINTS = ["toolnotopen", "web search", "联网搜索"];
export const WEB_SEARCH_ACTIVATION_URL =
  "https://console.volcengine.com/common-buy/CC_content_plugin";
export const ALIYUN_APIKEY_DOC_URL =
  "https://help.aliyun.com/zh/model-studio/error-code#apikey-error";
export const CONTENT_POLICY_BLOCK_MESSAGE =
  "上传已被风控强拦截：检测到高风险色情/裸露/血腥/暴力内容，系统已直接拒绝该视频上传。请删除敏感画面后重试";

export const DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024;
export const UPLOAD_RESUME_KEY_PREFIX = "video-upload-resume-v1";
export const HISTORY_CLIENT_ID_KEY = "video-insights-client-id-v1";
export const HISTORY_CLIENT_ID_HEADER = "X-Client-ID";
export const USER_SETTINGS_STORAGE_KEY_PREFIX = "video-insights-user-settings-v1";
export const ERROR_TOAST_DURATION_MS = 9000;
export const ERROR_GUIDE_DURATION_MS = 5200;

export const SEGMENT_ZONE_LABELS: Record<string, string> = {
  standard: "标准区",
  long: "长视频区",
  super_long: "超长区",
  trim_required: "裁剪优先区",
};

export const SEGMENT_POLICY_CODE_GUIDES: Record<string, string> = {
  video_segment_trim_required: "当前视频属于裁剪优先区，请先裁剪后再上传或分析。",
  video_segment_super_long_batch_not_allowed: "批量中包含超长视频，建议改为单文件处理。",
  video_segment_long_batch_limit: "包含长视频时，整批最多允许 2 个视频。",
  video_segment_batch_not_allowed: "当前批次不符合分段策略，请按提示拆分或裁剪后重试。",
};

export const DEGRADE_REASON_LABELS: Record<string, string> = {
  standard_steps_not_detected_subtitle_candidates_generated:
    "未识别到标准步骤，已根据字幕生成候选步骤",
  subtitle_signal_insufficient_timeline_summary_generated: "字幕信号不足，已自动生成时间线摘要",
  user_requested_summary_only: "已按你的选择仅生成摘要版内容",
  content_generation_failed_emergency_summary_generated:
    "标准与候选步骤均不可用，已切换紧急摘要保底",
  content_generation_failed: "内容提炼失败，已返回保底结果",
  content_policy_blocked: "内容触发安全策略，已拦截",
};

export const STAGE_LABELS: Record<string, string> = {
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

export const STAGE_PERCENT: Record<string, number> = {
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

export const MODEL_PRESETS: Record<Exclude<ModelPreset, "custom">, { label: string; baseUrl: string }> =
  {
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

export const MODEL_PRESET_VALUES: ModelPreset[] = [
  "ark",
  "openai",
  "deepseek",
  "qwen",
  "custom",
];
export const WHISPER_MODEL_VALUES = new Set(["tiny", "base", "small", "medium", "large"]);

export const DEFAULT_PROGRESS_BOARD: ProgressBoard = {
  mode: "",
  percent: 0,
  stage: "",
  total: 0,
  current: 0,
  success: 0,
  failed: 0,
  currentFile: "",
};

export const HERO_TITLE_CANVAS_COLORS = [
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

export const HERO_SUBTITLE_CANVAS_COLORS = [
  "rgba(0, 153, 255, 0.9)",
  "rgba(0, 153, 255, 0.75)",
  "rgba(56, 189, 248, 0.68)",
  "rgba(96, 165, 250, 0.56)",
  "rgba(147, 197, 253, 0.46)",
];

export const ANALYZE_BUTTON_GRADIENT_COLORS = [
  "rgb(45, 212, 191)",
  "rgb(56, 189, 248)",
  "rgb(96, 165, 250)",
];

export const NEW_STEP_DEFAULT_TITLE = "新步骤";
export const NEW_STEP_DEFAULT_DESCRIPTION = "请输入步骤描述";
export const NEW_STEP_DEFAULT_TIME = "00:00";
export const MAX_VISION_MIN = 0;
export const MAX_VISION_MAX = 10;
export const FPS_MIN = 0.1;
export const FPS_MAX = 10;
export const FPS_STEP = 0.1;
export const HERO_ANIMATION_TOP_THRESHOLD = 4;
export const MOBILE_PERF_MEDIA_QUERY = "(max-width: 900px) and (pointer: coarse)";
export const REDUCED_MOTION_MEDIA_QUERY = "(prefers-reduced-motion: reduce)";
export const PROGRESS_POLL_INTERVAL_DESKTOP_MS = 5000;
export const PROGRESS_POLL_INTERVAL_MOBILE_MS = 9000;

export const EMPTY_STEPS: StepItem[] = [];
export const HISTORY_VIRTUAL_ITEM_HEIGHT = 74;
export const HISTORY_VIRTUAL_OVERSCAN = 6;
