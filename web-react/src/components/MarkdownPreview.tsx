import { memo } from "react";
import { cn } from "@/lib/utils";

export const MarkdownPreview = memo(function MarkdownPreview({
  html,
  className,
  contentClassName,
}: {
  html: string;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <div
      className={cn(
        "history-scroll max-h-[min(62vh,40rem)] overflow-auto pr-1 xl:h-[min(62vh,40rem)]",
        className,
      )}
    >
      <div
        className={cn("prose prose-invert max-w-none text-sm", contentClassName)}
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </div>
  );
});
