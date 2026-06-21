import {
  HISTORY_CLIENT_ID_KEY,
  MOBILE_PERF_MEDIA_QUERY,
  REDUCED_MOTION_MEDIA_QUERY,
  VALID_VIDEO_EXTENSIONS,
} from "../constants/app";
import type {
  ModelPreset,
  NavigatorWithConnection,
  ProgressBoard,
} from "../types/api";

export const createHistoryClientId = () => {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `cid_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
};

export const getOrCreateHistoryClientId = () => {
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

export const normalizeModelBaseUrlForSignature = (value: string) =>
  String(value || "").trim().replace(/\/+$/u, "");

export const buildModelConfigSignature = (
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

export const clampNumber = (
  value: unknown,
  fallback: number,
  min: number,
  max: number,
) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
};

export const safeString = (value: unknown, maxLength: number, fallback = "") =>
  typeof value === "string" ? value.slice(0, Math.max(0, maxLength)) : fallback;

export const shouldEnableMobilePerfMode = () => {
  if (typeof window === "undefined") return false;
  const coarseMobile = window.matchMedia(MOBILE_PERF_MEDIA_QUERY).matches;
  const reducedMotion = window.matchMedia(REDUCED_MOTION_MEDIA_QUERY).matches;
  const saveData = Boolean((navigator as NavigatorWithConnection).connection?.saveData);
  return coarseMobile || reducedMotion || saveData;
};

export const isValidVideo = (filename: string) => {
  const ext = String(filename || "").split(".").pop()?.toLowerCase() || "";
  return VALID_VIDEO_EXTENSIONS.has(ext);
};

export const parseSourceUrls = (raw: string) => {
  const input = String(raw || "");
  if (!input.trim()) return [];

  const candidates: string[] = [];

  const directMatches = input.match(/https?:\/\/[^\s"'<>]+/giu) || [];
  candidates.push(...directMatches);

  const schemeLessPatterns = [
    /v\.douyin\.com\/[A-Za-z0-9/_-]+/giu,
    /(?:www\.)?douyin\.com\/[^\s"'<>]+/giu,
    /b23\.tv\/[^\s"'<>]+/giu,
    /(?:www\.)?bilibili\.com\/[^\s"'<>]+/giu,
    /xhslink\.com\/[A-Za-z0-9/_-]+/giu,
    /(?:www\.)?xiaohongshu\.com\/[^\s"'<>]+/giu,
  ];
  for (const pattern of schemeLessPatterns) {
    const matched = input.match(pattern) || [];
    candidates.push(...matched);
  }

  const normalized: string[] = [];
  for (const rawCandidate of candidates) {
    let url = String(rawCandidate || "").trim();
    if (!url) continue;

    url = url
      .replace(/^[<([{"'“‘]+/u, "")
      .replace(/[>)\]}”’"']+$/u, "")
      .replace(/[，。！？；：、,.;!?]+$/u, "")
      .trim();
    if (!url) continue;

    if (!/^https?:\/\//iu.test(url)) {
      url = `https://${url}`;
    }
    try {
      const parsed = new URL(url);
      if (!/^https?:$/iu.test(parsed.protocol)) continue;
      const canonical = parsed.toString();
      if (canonical && !normalized.includes(canonical)) {
        normalized.push(canonical);
      }
    } catch {
      continue;
    }
  }
  return normalized;
};

export const basename = (value: string | undefined | null) =>
  String(value || "")
    .split(/[\\/]/)
    .filter(Boolean)
    .pop() || "";

export const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

/**
 * Parse a timestamp string ("HH:MM:SS", "MM:SS", or "SS") into seconds.
 * Returns null when the input has no usable numeric segments.
 */
export const parseTimeToSeconds = (value: string | undefined | null): number | null => {
  const text = String(value || "").trim();
  if (!text) return null;
  const matched = text.match(/(\d+(?:\.\d+)?)/g);
  if (!matched || matched.length === 0) return null;
  const parts = matched.slice(-3).map((part) => Number(part));
  if (parts.some((part) => Number.isNaN(part))) return null;
  const seconds = parts.reduce((acc, part) => acc * 60 + part, 0);
  return Number.isFinite(seconds) ? seconds : null;
};

export const isSameProgressBoard = (a: ProgressBoard, b: ProgressBoard) =>
  a.mode === b.mode &&
  a.percent === b.percent &&
  a.stage === b.stage &&
  a.total === b.total &&
  a.current === b.current &&
  a.success === b.success &&
  a.failed === b.failed &&
  a.currentFile === b.currentFile;
