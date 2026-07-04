// Shared API and domain types used across the app.
// Kept as pure TS (no runtime), safe to import from anywhere.

export type Mode = "" | "upload" | "single" | "batch";
export type FileStatus = "pending" | "processing" | "success" | "failed";

export type ModelPreset = "ark" | "openai" | "deepseek" | "qwen" | "custom";

export type PersistedUserSettings = {
  version?: number;
  apiKey?: string;
  modelPreset?: ModelPreset | string;
  modelName?: string;
  modelBaseUrl?: string;
  whisperModel?: string;
  maxVision?: number;
  useVideo?: boolean;
  webSearch?: boolean;
  fps?: number;
  summaryOnly?: boolean;
  updatedAt?: string;
};

export type StepItem = {
  step?: number;
  time?: string;
  title?: string;
  description?: string;
  confidence?: number;
};

export type BatchFileItem = {
  filename: string;
  filepath: string;
  status: FileStatus;
  error: string;
  clientId?: string;
  sourceKey?: string;
};

export type RiskResult = {
  decision?: "allow" | "restrict" | "block" | string;
  risk_level?: "low" | "medium" | "high" | string;
  reason_code?: string;
  reason?: string;
  scores?: Partial<Record<"nudity" | "violence" | "gore", number>>;
};

export type BlockedNotice = {
  title?: string;
  risk_level?: string;
  reason_code?: string;
  reason?: string;
  suggestions?: string[];
  retry_guidance?: string;
};

export type SegmentPolicy = {
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

export type BatchSegmentPolicy = {
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

export type EffectiveOptions = {
  use_video?: boolean;
  web_search?: boolean;
  max_vision?: number;
  summary_only?: boolean;
};

export type ApiErrorPayload = {
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

export type SingleResultData = {
  steps: StepItem[];
  markdown: string;
  output_dir: string;
  output_dir_name?: string;
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
  video_preview_url?: string;
  subtitle_available?: boolean;
  subtitle_file_name?: string;
  subtitle_line_count?: number;
  subtitle_exports?: Record<string, string>;
  subtitle_workbench_url?: string;
};

export type BatchResultItem = {
  index?: number;
  filename: string;
  success: boolean;
  steps_count?: number;
  output_dir?: string;
  output_dir_name?: string;
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
  video_preview_url?: string;
  subtitle_available?: boolean;
  subtitle_file_name?: string;
  subtitle_line_count?: number;
  subtitle_exports?: Record<string, string>;
  subtitle_workbench_url?: string;
};

export type BatchResultData = {
  results: BatchResultItem[];
  batch_segment_policy?: BatchSegmentPolicy;
  batch_policy_warnings?: string[];
  summary?: {
    total?: number;
    success?: number;
    failed?: number;
  };
};

export type HistoryItem = {
  id: string;
  video_name: string;
  mode?: string;
  steps_count?: number;
  timestamp?: string;
};

export type SubtitleLine = {
  index?: number;
  start_time?: string;
  end_time?: string;
  start_seconds?: number;
  end_seconds?: number;
  text?: string;
};

export type SubtitleWorkbenchData = {
  subtitle_file?: string;
  subtitle_available?: boolean;
  line_count?: number;
  lines?: SubtitleLine[];
  video_preview_url?: string;
  video_preview_optimized?: boolean;
  subtitle_exports?: Record<string, string>;
};

export type ProgressBoard = {
  mode: Mode;
  percent: number;
  stage: string;
  total: number;
  current: number;
  success: number;
  failed: number;
  currentFile: string;
};

export type NavigatorWithConnection = Navigator & {
  connection?: {
    saveData?: boolean;
    addEventListener?: (type: "change", listener: () => void) => void;
    removeEventListener?: (type: "change", listener: () => void) => void;
  };
};
