// Shared API and domain types used across the app.
// Kept as pure TS (no runtime), safe to import from anywhere.

export type Mode = "" | "upload" | "single" | "batch";
export type OutputTemplate = "operation_guide" | "content_summary";
export type FileStatus = "pending" | "uploading" | "processing" | "success" | "failed" | "cancelled";

export type AnalysisTaskKind = "single" | "batch" | "url";
export type AnalysisTaskStatus = "uploading" | "queued" | "analyzing" | "completed" | "failed" | "cancelled";
export type AnalysisTaskFileStatus = "waiting" | "analyzing" | "success" | "failed";

export type AnalysisTaskFileProgress = {
  index: number;
  filename: string;
  status: AnalysisTaskFileStatus;
  stage: string;
  message: string;
};

export type AnalysisTaskPayload = {
  filepath?: string;
  filepaths?: string[];
  url?: string;
  filename?: string;
  summary_only?: boolean;
  web_search?: boolean;
  max_vision?: number;
  output_template?: OutputTemplate;
};

export type AnalysisTaskStatusResponse = {
  task_id: string;
  kind: AnalysisTaskKind;
  status: AnalysisTaskStatus;
  stage?: string;
  message?: string;
  percent?: number;
  total?: number;
  current?: number;
  current_file?: string;
  file_progress?: AnalysisTaskFileProgress[];
  retryable?: boolean;
  cancel_requested?: boolean;
  attempt_count?: number;
  recovery_count?: number;
  created_at?: number | null;
  updated_at?: number | null;
  started_at?: number | null;
  finished_at?: number | null;
};

export type AnalysisTaskListItem = AnalysisTaskStatusResponse & {
  payload: AnalysisTaskPayload;
};

export type AnalysisTaskListResponse = {
  tasks: AnalysisTaskListItem[];
};

export type AnalysisTaskQueueItem = {
  taskId: string;
  kind: AnalysisTaskKind;
  status: AnalysisTaskStatus;
  stage: string;
  message: string;
  percent: number;
  total: number;
  current: number;
  currentFile: string;
  fileProgress: AnalysisTaskFileProgress[];
  retryable: boolean;
  cancelRequested: boolean;
  attemptCount: number;
  recoveryCount: number;
  payload: AnalysisTaskPayload;
  label: string;
  clientId?: string;
  createdAt: string;
};

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
  outputTemplate?: OutputTemplate;
  updatedAt?: string;
};

export type SubtitleEvidence = {
  index?: number | string;
  start_time?: string;
  end_time?: string;
  start_seconds?: number;
  end_seconds?: number;
  raw_text?: string;
  analyzed_text?: string;
};

export type ScreenshotEvidence = {
  path?: string;
  captured_at_seconds?: number;
};

export type StepEvidence = {
  anchor_time_seconds?: number;
  subtitles?: SubtitleEvidence[];
  screenshot?: ScreenshotEvidence;
  external_reference_ids?: string[];
  [key: string]: unknown;
};

export type ExternalReference = {
  id?: string;
  title?: string;
  url?: string;
  source?: "ark_web_search" | "model_reference" | string;
};

export type StepItem = {
  step_id?: string;
  step?: number;
  time?: string;
  time_seconds?: number;
  title?: string;
  description?: string;
  confidence?: number;
  evidence?: StepEvidence;
};

export type BatchFileItem = {
  filename: string;
  filepath: string;
  status: FileStatus;
  error: string;
  clientId?: string;
  sourceKey?: string;
  resumeKey?: string;
  size?: number;
  lastModified?: number;
  needsReselect?: boolean;
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
  output_template?: OutputTemplate;
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
  output_template?: OutputTemplate;
  external_references?: ExternalReference[];
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
  output_template?: OutputTemplate;
  external_references?: ExternalReference[];
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
