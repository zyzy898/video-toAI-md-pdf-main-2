import { memo } from "react";
import type { StepItem } from "../types/api";
import { parseTimeToSeconds } from "../lib/utils-app";
import { PlayIcon } from "./icons";

export const ReadonlyStepsList = memo(function ReadonlyStepsList({
  steps,
  onSeek,
}: {
  steps: StepItem[];
  onSeek?: (seconds: number) => void;
}) {
  return (
    <div className="space-y-2">
      {steps.map((step, i) => {
        const timeLabel = step.time || "00:00";
        const seconds = parseTimeToSeconds(step.time);
        const canSeek = Boolean(onSeek) && seconds !== null;
        return (
          <div key={`s-${i}`} className="readonly-step-card rounded border border-neutral-800 bg-neutral-950/60 p-2">
            <p className="readonly-step-meta flex items-center gap-1.5 text-xs text-neutral-500">
              <span>#{step.step || i + 1}</span>
              {canSeek ? (
                <button
                  type="button"
                  className="step-time-jump"
                  title={`跳转到 ${timeLabel}`}
                  aria-label={`跳转到视频 ${timeLabel}`}
                  onClick={() => onSeek?.(seconds as number)}
                >
                  <PlayIcon className="h-3 w-3" />
                  {timeLabel}
                </button>
              ) : (
                <span>· {timeLabel}</span>
              )}
            </p>
            <p className="readonly-step-title text-sm font-medium">{step.title || "未命名步骤"}</p>
            <p className="readonly-step-desc text-sm text-neutral-300">{step.description || ""}</p>
          </div>
        );
      })}
    </div>
  );
});
