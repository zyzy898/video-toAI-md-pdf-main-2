"use client";
import { cn } from "@/lib/utils";
import { CanvasText } from "@/components/ui/canvas-text";

export default function CanvasTextDemo() {
  return (
    <div className="flex min-h-80 flex-col items-center justify-center gap-3 p-8">
      <h2
        className={cn(
          "group relative mx-auto mt-4 max-w-2xl text-left text-4xl font-bold tracking-tight text-balance text-neutral-600 sm:text-5xl md:text-6xl xl:text-7xl dark:text-neutral-700",
        )}
      >
        视频转文档，{" "}
        <CanvasText
          text="不止是提取，更是理解"
          backgroundClassName="bg-blue-600 dark:bg-blue-700"
          colors={[
            "rgba(0, 153, 255, 1)",
            "rgba(0, 153, 255, 0.9)",
            "rgba(0, 153, 255, 0.8)",
            "rgba(0, 153, 255, 0.7)",
            "rgba(0, 153, 255, 0.6)",
            "rgba(0, 153, 255, 0.5)",
            "rgba(0, 153, 255, 0.4)",
            "rgba(0, 153, 255, 0.3)",
            "rgba(0, 153, 255, 0.2)",
            "rgba(0, 153, 255, 0.1)",
          ]}
          lineGap={4}
          animationDuration={20}
        />
      </h2>
      <p className="mx-auto max-w-3xl text-balance text-center text-sm font-medium text-neutral-500 sm:text-base dark:text-neutral-400">
        AI 自动分析视频内容，抓取关键截图，拆解核心步骤，输出结构清晰、重点明确的总结文档。
      </p>
      <p className="mx-auto max-w-3xl text-balance text-center text-sm font-medium text-neutral-500 sm:text-base dark:text-neutral-400">
        <CanvasText
          text="让信息沉淀更高效，Turn insights into docs。"
          backgroundClassName="bg-blue-600 dark:bg-blue-700"
          colors={[
            "rgba(0, 153, 255, 0.9)",
            "rgba(0, 153, 255, 0.75)",
            "rgba(56, 189, 248, 0.68)",
            "rgba(96, 165, 250, 0.56)",
            "rgba(147, 197, 253, 0.46)",
          ]}
          lineGap={4}
          animationDuration={20}
        />
      </p>
    </div>
  );
}
