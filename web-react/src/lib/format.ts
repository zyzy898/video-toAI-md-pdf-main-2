import {
  ALIYUN_APIKEY_DOC_URL,
  CONTENT_POLICY_BLOCK_MESSAGE,
  DEGRADE_REASON_LABELS,
  SEGMENT_POLICY_CODE_GUIDES,
  SEGMENT_ZONE_LABELS,
  WEB_SEARCH_ACTIVATION_URL,
  WEB_SEARCH_ERROR_HINTS,
} from "../constants/app";
import type { BatchSegmentPolicy, RiskResult, SegmentPolicy } from "../types/api";

export const extractRequestId = (message: string) => {
  const match = String(message || "").match(
    /request[_\s-]*id['"]?\s*[:：]\s*['"]?([A-Za-z0-9._-]+)/i,
  );
  return match?.[1] || "";
};

export const extractErrorCode = (message: string) => {
  const match = String(message || "").match(/(?:^|\|)\s*code=([A-Za-z0-9._-]+)/i);
  return String(match?.[1] || "").trim().toLowerCase();
};

export const formatContentPolicyViolationMessage = (_message: string) => {
  return CONTENT_POLICY_BLOCK_MESSAGE;
};

export const extractModelNameFromNotFound = (message: string) => {
  const match = String(message || "").match(/model or endpoint\s+([A-Za-z0-9._:-]+)/i);
  return match?.[1] || "";
};

export const formatModelConnectionError = (message: string) => {
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

export const formatRiskHint = (risk?: RiskResult) => {
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
  const parts = [
    level ? `等级: ${level}` : "",
    code ? `规则: ${code}` : "",
    reason,
    scoreText,
  ].filter(Boolean);
  return parts.join(" | ");
};

export const getSegmentZoneLabel = (zone?: string, fallback?: string) =>
  SEGMENT_ZONE_LABELS[String(zone || "").trim().toLowerCase()] ||
  String(fallback || "").trim() ||
  "未知区";

export const formatSegmentPolicyHint = (policy?: SegmentPolicy) => {
  if (!policy) return "";
  const zoneText = getSegmentZoneLabel(policy.zone, policy.zone_label);
  const durationText = String(policy.duration_text || "").trim() || "未知";
  const sizeMb = Number(policy.file_size_mb || 0);
  const sizeText = Number.isFinite(sizeMb) && sizeMb > 0 ? `${sizeMb.toFixed(1)}MB` : "未知大小";
  return `分段策略: ${zoneText}（时长 ${durationText}，大小 ${sizeText}）`;
};

export const formatBatchSegmentPolicyHint = (policy?: BatchSegmentPolicy) => {
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

export const compactErrorDetail = (message: string) => {
  const parts = String(message || "")
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean)
    .filter((item) => !/^code=/i.test(item))
    .filter((item) => !/^等级[:：]/.test(item))
    .filter((item) => !/^规则[:：]/.test(item));
  return parts.slice(0, 2).join("；");
};

export const formatSegmentPolicyGuideByCode = (
  errorCode: string,
  message: string,
  requestIdText: string,
) => {
  const guide = SEGMENT_POLICY_CODE_GUIDES[String(errorCode || "").trim().toLowerCase()];
  if (!guide) return "";
  const detail = compactErrorDetail(message);
  return `${guide}${requestIdText}${detail ? ` ${detail}` : ""}`;
};

export const formatErrorMessage = (rawMessage: string) => {
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

export const formatInlineErrorMessage = (rawMessage: string) => {
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
    return formatContentPolicyViolationMessage(message);
  }
  const lower = message.toLowerCase();

  if (WEB_SEARCH_ERROR_HINTS.some((hint) => lower.includes(hint))) {
    return requestId
      ? `联网搜索未开通（请求 ID：${requestId}）`
      : "联网搜索未开通，请在火山引擎控制台开通后重试";
  }

  const modelConnectionHint = formatModelConnectionError(message);
  if (modelConnectionHint) return modelConnectionHint;

  return message.replace(/\s+/g, " ").trim();
};

export const formatDegradeReason = (rawReason?: string) => {
  const reason = String(rawReason || "").trim();
  if (!reason) return "标准步骤未稳定提炼，已自动降级输出";
  const mapped = DEGRADE_REASON_LABELS[reason.toLowerCase()];
  if (mapped) return mapped;
  if (/[\u4e00-\u9fa5]/u.test(reason)) return reason;
  return "系统未提炼出高置信度标准步骤，已输出可读保底结果";
};

export const formatSegmentPolicyLine = (policy?: SegmentPolicy) => {
  if (!policy) return "";
  const zoneText = getSegmentZoneLabel(policy.zone, policy.zone_label);
  const durationText = String(policy.duration_text || "").trim() || "未知";
  const sizeText =
    typeof policy.file_size_mb === "number" && Number.isFinite(policy.file_size_mb)
      ? `${Number(policy.file_size_mb).toFixed(1)}MB`
      : "未知大小";
  return `${zoneText} · 时长 ${durationText} · 大小 ${sizeText}`;
};
