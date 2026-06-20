import { memo } from "react";
import type { StepItem } from "../types/api";

export const ReadonlyStepsList = memo(function ReadonlyStepsList({
  steps,
}: {
  steps: StepItem[];
}) {
  return (
    <div className="space-y-2">
      {steps.map((step, i) => (
        <div key={`s-${i}`} className="readonly-step-card rounded border border-neutral-800 bg-neutral-950/60 p-2">
          <p className="readonly-step-meta text-xs text-neutral-500">
            #{step.step || i + 1} · {step.time || "00:00"}
          </p>
          <p className="readonly-step-title text-sm font-medium">{step.title || "未命名步骤"}</p>
          <p className="readonly-step-desc text-sm text-neutral-300">{step.description || ""}</p>
        </div>
      ))}
    </div>
  );
});
