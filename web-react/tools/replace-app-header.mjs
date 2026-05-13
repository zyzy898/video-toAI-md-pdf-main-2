import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const appPath = path.resolve(__dirname, "..", "src", "App.tsx");
const content = readFileSync(appPath, "utf8");

const marker = "export default function App()";
const idx = content.indexOf(marker);
if (idx < 0) {
  throw new Error("Cannot find App() marker in App.tsx");
}

// Identifiers imported from the new modules. We emit a `void X;` line for every
// value identifier so TypeScript `noUnusedLocals` can't fail if the App body
// happens not to use some of them.
const iconNames = [
  "BrandStudioIcon",
  "ClearIcon",
  "CloseIcon",
  "DocumentIcon",
  "DownloadSingleIcon",
  "DownloadZipIcon",
  "EditIcon",
  "EyeIcon",
  "EyeOffIcon",
  "FileVideoIcon",
  "FolderPlusIcon",
  "HistoryEmptyIllustration",
  "HistoryIcon",
  "PlayIcon",
  "RefreshIcon",
  "SettingsIcon",
  "StackIcon",
  "StatusFailedIcon",
  "StatusSuccessIcon",
  "StepsIcon",
  "TrashIcon",
  "UploadIcon",
];

const constNames = [
  "ALIYUN_APIKEY_DOC_URL",
  "ANALYZE_BUTTON_GRADIENT_COLORS",
  "CONTENT_POLICY_BLOCK_MESSAGE",
  "DEFAULT_PROGRESS_BOARD",
  "DEFAULT_UPLOAD_CHUNK_SIZE",
  "EMPTY_STEPS",
  "ERROR_GUIDE_DURATION_MS",
  "ERROR_TOAST_DURATION_MS",
  "FPS_MAX",
  "FPS_MIN",
  "FPS_STEP",
  "HERO_ANIMATION_TOP_THRESHOLD",
  "HERO_SUBTITLE_CANVAS_COLORS",
  "HERO_TITLE_CANVAS_COLORS",
  "HISTORY_CLIENT_ID_HEADER",
  "HISTORY_CLIENT_ID_KEY",
  "MAX_VISION_MAX",
  "MAX_VISION_MIN",
  "MOBILE_PERF_MEDIA_QUERY",
  "MODEL_PRESETS",
  "MODEL_PRESET_VALUES",
  "NEW_STEP_DEFAULT_DESCRIPTION",
  "NEW_STEP_DEFAULT_TIME",
  "NEW_STEP_DEFAULT_TITLE",
  "PROGRESS_POLL_INTERVAL_DESKTOP_MS",
  "PROGRESS_POLL_INTERVAL_MOBILE_MS",
  "REDUCED_MOTION_MEDIA_QUERY",
  "SEGMENT_POLICY_CODE_GUIDES",
  "SEGMENT_ZONE_LABELS",
  "STAGE_LABELS",
  "STAGE_PERCENT",
  "UPLOAD_RESUME_KEY_PREFIX",
  "USER_SETTINGS_STORAGE_KEY_PREFIX",
  "VALID_VIDEO_EXTENSIONS",
  "WEB_SEARCH_ACTIVATION_URL",
  "WEB_SEARCH_ERROR_HINTS",
  "WHISPER_MODEL_VALUES",
];

const utilsNames = [
  "basename",
  "buildModelConfigSignature",
  "clampNumber",
  "clone",
  "createHistoryClientId",
  "getOrCreateHistoryClientId",
  "isSameProgressBoard",
  "isValidVideo",
  "normalizeModelBaseUrlForSignature",
  "parseSourceUrls",
  "safeString",
  "shouldEnableMobilePerfMode",
];

const formatNames = [
  "compactErrorDetail",
  "extractErrorCode",
  "extractModelNameFromNotFound",
  "extractRequestId",
  "formatBatchSegmentPolicyHint",
  "formatContentPolicyViolationMessage",
  "formatDegradeReason",
  "formatErrorMessage",
  "formatInlineErrorMessage",
  "formatModelConnectionError",
  "formatRiskHint",
  "formatSegmentPolicyGuideByCode",
  "formatSegmentPolicyHint",
  "formatSegmentPolicyLine",
  "getSegmentZoneLabel",
];

const voidedPresentational = [
  "ReadonlyStepsList",
  "VirtualizedHistoryList",
  "MarkdownPreview",
];

const voids = [
  ...iconNames,
  ...constNames,
  ...utilsNames,
  ...formatNames,
  "ApiRequestError",
  ...voidedPresentational,
]
  .map((name) => `void ${name};`)
  .join("\n");

const newHeader = `import DOMPurify from "dompurify";
import { marked } from "marked";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { BackgroundBeams } from "@/components/ui/background-beams";
import { CanvasText } from "@/components/ui/canvas-text";
import { NoiseBackground } from "@/components/ui/noise-background";
import { cn } from "@/lib/utils";

import {
${constNames.map((n) => `  ${n},`).join("\n")}
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
${utilsNames.map((n) => `  ${n},`).join("\n")}
} from "./lib/utils-app";
import {
${formatNames.map((n) => `  ${n},`).join("\n")}
} from "./lib/format";
import {
${iconNames.map((n) => `  ${n},`).join("\n")}
} from "./components/icons";
import { MarkdownPreview } from "./components/MarkdownPreview";
import { ReadonlyStepsList } from "./components/ReadonlyStepsList";
import { VirtualizedHistoryList } from "./components/VirtualizedHistoryList";

${voids}

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

`;

const rest = content.slice(idx);
const output = newHeader + rest;
writeFileSync(appPath, output, "utf8");
console.log("App.tsx header rewritten; tail length =", rest.length);
