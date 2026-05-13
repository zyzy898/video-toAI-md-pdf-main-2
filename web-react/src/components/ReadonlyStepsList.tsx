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
        <div
          key={`s-${i}`}
          className="rounded border border-neutral-800 bg-neutral-950/60 p-2"
        >
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
