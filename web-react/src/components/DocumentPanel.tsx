import { memo } from "react";
import { CopyIcon, DocumentIcon, DownloadZipIcon } from "./icons";
import { MarkdownPreview } from "./MarkdownPreview";

type DocumentPanelProps = {
  html: string;
  summaryOnly: boolean;
  onDownloadZip: () => void;
  onCopyMarkdown?: () => void;
  onCopyText?: () => void;
};

export const DocumentPanel = memo(function DocumentPanel({
  html,
  summaryOnly,
  onDownloadZip,
  onCopyMarkdown,
  onCopyText,
}: DocumentPanelProps) {
  return (
    <section className="panel-card motion-enter result-heavy-surface rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <DocumentIcon className="h-4 w-4 text-neutral-300" />
          <h2 className="text-base font-semibold">生成的总结文档</h2>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {onCopyMarkdown ? (
            <button
              type="button"
              className="doc-action-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
              onClick={onCopyMarkdown}
            >
              <CopyIcon className="h-3.5 w-3.5" />
              复制 Markdown
            </button>
          ) : null}
          {onCopyText ? (
            <button
              type="button"
              className="doc-action-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
              onClick={onCopyText}
            >
              <CopyIcon className="h-3.5 w-3.5" />
              复制纯文本
            </button>
          ) : null}
          <button
            className="zip-download-btn flex items-center gap-1 rounded border border-neutral-700 px-2 py-1 text-xs"
            onClick={onDownloadZip}
          >
            <DownloadZipIcon className="h-3.5 w-3.5" />
            下载 ZIP
          </button>
        </div>
      </div>
      <MarkdownPreview
        html={html}
        className={summaryOnly ? "summary-only-scroll-rail" : undefined}
        contentClassName={summaryOnly ? "summary-only-markdown-content" : "standard-markdown-content"}
      />
    </section>
  );
});
