import { memo } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { SingleResultData, StepItem } from "../types/api";
import { EditIcon, StepsIcon, TrashIcon } from "./icons";
import { ReadonlyStepsList } from "./ReadonlyStepsList";
import { clone } from "../lib/utils-app";
import { formatDegradeReason } from "../lib/format";
import {
  CONTENT_POLICY_BLOCK_MESSAGE,
  NEW_STEP_DEFAULT_DESCRIPTION,
  NEW_STEP_DEFAULT_TIME,
  NEW_STEP_DEFAULT_TITLE,
} from "../constants/app";

type StepsPanelProps = {
  resultData: SingleResultData;
  steps: StepItem[];
  isEditMode: boolean;
  editedSteps: StepItem[];
  savingSteps: boolean;
  dragIndex: number | null;
  dragOverIndex: number | null;
  setEditedSteps: Dispatch<SetStateAction<StepItem[]>>;
  setIsEditMode: Dispatch<SetStateAction<boolean>>;
  setDragIndex: Dispatch<SetStateAction<number | null>>;
  setDragOverIndex: Dispatch<SetStateAction<number | null>>;
  onShowError: (message: string) => void;
  onSave: () => void;
  onSeek?: (seconds: number) => void;
};

export const StepsPanel = memo(function StepsPanel({
  resultData,
  steps,
  isEditMode,
  editedSteps,
  savingSteps,
  dragIndex,
  dragOverIndex,
  setEditedSteps,
  setIsEditMode,
  setDragIndex,
  setDragOverIndex,
  onShowError,
  onSave,
  onSeek,
}: StepsPanelProps) {
  const singleResultMode = String(resultData?.result_mode || "").trim().toLowerCase();
  const isBlockedNoticeResult = singleResultMode === "blocked_notice";
  const isDegradedResult = singleResultMode === "candidate_steps" || singleResultMode === "timeline_summary";

  return (
    <section className="panel-card motion-enter result-heavy-surface flex min-h-0 flex-col rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
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
              if (!resultData?.steps?.length) return onShowError("当前没有可编辑步骤");
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
        <p className={`mb-2 text-xs ${isBlockedNoticeResult ? "text-rose-300/90" : "text-amber-300/90"}`}>
          {resultData.analysis_note}
        </p>
      ) : null}
      {isBlockedNoticeResult ? (
        <BlockedNoticeBlock resultData={resultData} />
      ) : !isEditMode ? (
        <div className="single-result-scroll history-scroll flex-1 min-h-0 space-y-2 overflow-auto pr-1">
          {isDegradedResult ? <DegradedSummary resultData={resultData} /> : null}
          <ReadonlyStepsList steps={steps} onSeek={onSeek} />
        </div>
      ) : (
        <div className="steps-edit-scroll history-scroll flex-1 min-h-0 overflow-auto pr-1">
          <div className="steps-edit-actions mb-2 flex gap-2">
            <button type="button" disabled={savingSteps} className="steps-edit-save-btn" onClick={onSave}>
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
                    className="steps-edit-input steps-edit-title-input flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
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
                  className="steps-edit-textarea steps-edit-desc-textarea min-h-16 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm"
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
              setEditedSteps((prev) => [...prev, { step: prev.length + 1, time: "", title: "", description: "" }])
            }
          >
            添加新步骤
          </button>
        </div>
      )}
    </section>
  );
});

const BlockedNoticeBlock = memo(function BlockedNoticeBlock({ resultData }: { resultData: SingleResultData }) {
  const suggestions = resultData?.blocked_notice?.suggestions || [];
  return (
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
      {suggestions.length > 0 ? (
        <ul className="mt-2 list-disc space-y-1 pl-5 text-rose-100/90">
          {suggestions.slice(0, 4).map((tip, idx) => (
            <li key={`bn-tip-${idx}`}>{tip}</li>
          ))}
        </ul>
      ) : null}
      {resultData?.blocked_notice?.retry_guidance ? (
        <p className="mt-2 text-rose-100/90">{resultData.blocked_notice.retry_guidance}</p>
      ) : null}
    </div>
  );
});

const DegradedSummary = memo(function DegradedSummary({ resultData }: { resultData: SingleResultData }) {
  const keyPoints = resultData.key_points || [];
  const timelinePoints = resultData.timeline_points || [];
  return (
    <div className="space-y-2">
      <div className="rounded border border-amber-400/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-200">
        置信度较低（质量分：{Number(resultData?.quality_score || 0).toFixed(2)}）。原因：
        {formatDegradeReason(resultData?.degrade_reason)}
      </div>
      {resultData?.content_title ? (
        <div className="rounded border border-amber-400/30 bg-amber-500/6 p-2 text-xs text-amber-100/95">
          <p className="font-semibold">标题：{resultData.content_title}</p>
          {keyPoints.length > 0 ? (
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {keyPoints.slice(0, 5).map((item, idx) => (
                <li key={`kp-${idx}`}>{item}</li>
              ))}
            </ul>
          ) : null}
          {timelinePoints.length > 0 ? (
            <p className="mt-1">
              时间点：
              {timelinePoints.slice(0, 5).map((item) => String(item?.time || "00:00")).join(" / ")}
            </p>
          ) : null}
          {resultData?.confidence_note ? <p className="mt-1">{resultData.confidence_note}</p> : null}
        </div>
      ) : null}
    </div>
  );
});
