import { memo, useMemo } from "react";
import type { ExternalReference, StepItem, SubtitleEvidence } from "../types/api";
import { basename } from "../lib/utils-app";

const formatSeconds = (value: unknown) => {
  const seconds = Math.max(0, Number(value) || 0);
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
};

const screenshotUrl = (outputDir: string, path: unknown) => {
  const outputName = basename(outputDir);
  const relativePath = typeof path === "string" ? path.trim() : "";
  const match = /^images\/([A-Za-z0-9_.-]+)$/u.exec(relativePath);
  if (!outputName || !match) return "";
  return `/output/${encodeURIComponent(outputName)}/images/${encodeURIComponent(match[1])}`;
};

const subtitleKey = (subtitle: SubtitleEvidence, index: number) =>
  `${String(subtitle.index ?? index)}-${String(subtitle.start_seconds ?? subtitle.start_time ?? index)}`;

export const StepEvidence = memo(function StepEvidence({
  step,
  outputDir,
}: {
  step: StepItem;
  outputDir: string;
}) {
  const subtitles = Array.isArray(step.evidence?.subtitles)
    ? step.evidence.subtitles
    : [];
  const screenshot = step.evidence?.screenshot;
  const imageUrl = screenshotUrl(outputDir, screenshot?.path);
  if (!imageUrl && subtitles.length === 0) return null;

  return (
    <div className="mt-2 border-t border-neutral-800/80 pt-2">
      {imageUrl ? (
        <figure className="mb-2">
          <div className="step-evidence-image aspect-video w-full max-w-72 overflow-hidden rounded border border-neutral-800 bg-neutral-900">
            <img
              src={imageUrl}
              alt={`步骤 ${step.step || ""} 截图依据`}
              className="h-full w-full object-cover"
              loading="lazy"
              decoding="async"
            />
          </div>
          <figcaption className="mt-1 text-xs text-neutral-500">
            截图依据 · {formatSeconds(screenshot?.captured_at_seconds ?? step.time_seconds)}
          </figcaption>
        </figure>
      ) : null}

      {subtitles.length > 0 ? (
        <details className="group text-xs">
          <summary className="cursor-pointer select-none text-neutral-400 hover:text-neutral-200">
            字幕依据 {subtitles.length} 条
          </summary>
          <div className="mt-2 space-y-2">
            {subtitles.map((subtitle, index) => (
              <div key={subtitleKey(subtitle, index)} className="border-l-2 border-cyan-500/35 pl-2">
                <p className="text-neutral-500">
                  {subtitle.start_time || formatSeconds(subtitle.start_seconds)}
                </p>
                <p className="mt-0.5 text-neutral-300">
                  <span className="text-neutral-500">原字幕：</span>
                  {subtitle.raw_text || "未保留"}
                </p>
                <p className="mt-0.5 text-neutral-300">
                  <span className="text-neutral-500">分析字幕：</span>
                  {subtitle.analyzed_text || "未校正"}
                </p>
              </div>
            ))}
          </div>
        </details>
      ) : null}
    </div>
  );
});

const safeExternalReferences = (references: ExternalReference[]) => {
  const seen = new Set<string>();
  return references.filter((reference) => {
    const rawUrl = String(reference.url || "").trim();
    try {
      const parsed = new URL(rawUrl);
      if (!['http:', 'https:'].includes(parsed.protocol) || seen.has(parsed.href)) return false;
      seen.add(parsed.href);
      return true;
    } catch {
      return false;
    }
  });
};

export const ExternalReferences = memo(function ExternalReferences({
  references,
}: {
  references: ExternalReference[];
}) {
  const visibleReferences = useMemo(
    () => safeExternalReferences(Array.isArray(references) ? references : []),
    [references],
  );
  if (visibleReferences.length === 0) return null;

  return (
    <section className="mt-3 border-t border-neutral-800 pt-3" aria-label="外部补充">
      <h3 className="text-sm font-semibold text-neutral-200">外部补充</h3>
      <ul className="mt-1.5 space-y-1.5 text-xs">
        {visibleReferences.map((reference) => (
          <li key={reference.id || reference.url} className="min-w-0">
            <a
              href={reference.url}
              target="_blank"
              rel="noreferrer noopener"
              className="break-words text-cyan-300 underline decoration-cyan-500/40 underline-offset-2 hover:text-cyan-200"
            >
              {reference.title || reference.url}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
});
