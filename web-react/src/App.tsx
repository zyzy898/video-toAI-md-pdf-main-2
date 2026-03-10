
import DOMPurify from "dompurify";
import { marked } from "marked";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BackgroundBeams } from "@/components/ui/background-beams";

const VALID_VIDEO_EXTENSIONS = new Set([
  "mp4",
  "avi",
  "mov",
  "mkv",
  "wmv",
  "flv",
  "webm",
  "m4v",
  "mpg",
  "mpeg",
  "3gp",
  "ts",
  "m2ts",
]);

const WEB_SEARCH_ERROR_HINTS = ["toolnotopen", "web search", "联网搜索"];
const DEFAULT_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024;
const UPLOAD_RESUME_KEY_PREFIX = "video-upload-resume-v1";

const STAGE_LABELS: Record<string, string> = {
  prepare: "准备中",
  upload: "上传中",
  subtitle: "字幕识别",
  analysis: "内容分析",
  screenshots: "截图生成",
  vision: "视觉增强",
  document: "文档生成",
  pdf: "PDF 生成",
  done: "已完成",
  failed: "失败",
};

const STAGE_PERCENT: Record<string, number> = {
  prepare: 8,
  upload: 35,
  subtitle: 28,
  analysis: 55,
  screenshots: 75,
  vision: 84,
  document: 90,
  pdf: 96,
  done: 100,
  failed: 100,
};

type Mode = "" | "upload" | "single" | "batch";
type FileStatus = "pending" | "processing" | "success" | "failed";

type StepItem = {
  step?: number;
  time?: string;
  title?: string;
  description?: string;
  confidence?: number;
};

type BatchFileItem = {
  filename: string;
  filepath: string;
  status: FileStatus;
  error: string;
};

type SingleResultData = {
  steps: StepItem[];
  markdown: string;
  output_dir: string;
  pdf_path?: string;
};

type BatchResultItem = {
  index?: number;
  filename: string;
  success: boolean;
  steps_count?: number;
  output_dir?: string;
  error?: string;
};

type BatchResultData = {
  results: BatchResultItem[];
  summary?: {
    total?: number;
    success?: number;
    failed?: number;
  };
};

type HistoryItem = {
  id: string;
  video_name: string;
  mode?: string;
  steps_count?: number;
  timestamp?: string;
};

type ProgressBoard = {
  mode: Mode;
  percent: number;
  stage: string;
  total: number;
  current: number;
  success: number;
  failed: number;
  currentFile: string;
};

const DEFAULT_PROGRESS_BOARD: ProgressBoard = {
  mode: "",
  percent: 0,
  stage: "",
  total: 0,
  current: 0,
  success: 0,
  failed: 0,
  currentFile: "",
};

const isValidVideo = (filename: string) => {
  const ext = String(filename || "").split(".").pop()?.toLowerCase() || "";
  return VALID_VIDEO_EXTENSIONS.has(ext);
};

const basename = (value: string | undefined | null) =>
  String(value || "")
    .split(/[\\/]/)
    .filter(Boolean)
    .pop() || "";

const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value)) as T;

export default function App() {
  const [apiKey, setApiKey] = useState("");
  const [whisperModel, setWhisperModel] = useState("base");
  const [maxVision, setMaxVision] = useState(10);
  const [useVideo, setUseVideo] = useState(false);
  const [webSearch, setWebSearch] = useState(false);
  const [fps, setFps] = useState(1);

  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [savingSteps, setSavingSteps] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [batchFiles, setBatchFiles] = useState<BatchFileItem[]>([]);
  const [resultData, setResultData] = useState<SingleResultData | null>(null);
  const [batchResultData, setBatchResultData] = useState<BatchResultData | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const [isEditMode, setIsEditMode] = useState(false);
  const [editedSteps, setEditedSteps] = useState<StepItem[]>([]);
  const [dragIndex, setDragIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  const [batchDragOver, setBatchDragOver] = useState(false);
  const [progressVisible, setProgressVisible] = useState(false);
  const [progressTitle, setProgressTitle] = useState("处理中...");
  const [progressText, setProgressText] = useState("请稍候...");
  const [progressBoard, setProgressBoard] = useState<ProgressBoard>(DEFAULT_PROGRESS_BOARD);
  const [errorMessage, setErrorMessage] = useState("");
  const [showErrorToast, setShowErrorToast] = useState(false);

  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const errorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const batchTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const singleTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const progressVisibleRef = useRef(false);
  const batchFilesRef = useRef<BatchFileItem[]>([]);

  useEffect(() => {
    progressVisibleRef.current = progressVisible;
  }, [progressVisible]);

  useEffect(() => {
    batchFilesRef.current = batchFiles;
  }, [batchFiles]);

  useEffect(() => {
    return () => {
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
      if (batchTimerRef.current) clearInterval(batchTimerRef.current);
      if (singleTimerRef.current) clearInterval(singleTimerRef.current);
    };
  }, []);

  const fetchJson = useCallback(async <T,>(url: string, options: RequestInit = {}) => {
    const response = await fetch(url, options);
    const data = (await response.json().catch(() => ({}))) as { error?: string } & T;
    if (!response.ok || data.error) {
      throw new Error(data.error || `请求失败 (${response.status})`);
    }
    return data;
  }, []);

  const fetchBlob = useCallback(async (url: string, options: RequestInit = {}) => {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`下载失败 (${response.status})`);
    }
    return response.blob();
  }, []);

  const showError = useCallback((message: string) => {
    setErrorMessage(message || "操作失败");
    setShowErrorToast(true);
    if (errorTimerRef.current) clearTimeout(errorTimerRef.current);
    errorTimerRef.current = setTimeout(() => setShowErrorToast(false), 5000);
  }, []);

  const showProgress = useCallback((title: string, text: string) => {
    setProgressTitle(title);
    setProgressText(text);
    setProgressBoard(DEFAULT_PROGRESS_BOARD);
    setProgressVisible(true);
  }, []);

  const hideProgress = useCallback(() => {
    setProgressVisible(false);
    setProgressBoard(DEFAULT_PROGRESS_BOARD);
  }, []);

  const updateProgressBoard = useCallback((patch: Partial<ProgressBoard>) => {
    setProgressBoard((prev) => {
      const next = { ...prev, ...patch };
      next.percent = Math.max(0, Math.min(100, Number(next.percent) || 0));
      next.total = Math.max(0, Number(next.total) || 0);
      next.current = Math.max(0, Number(next.current) || 0);
      next.success = Math.max(0, Number(next.success) || 0);
      next.failed = Math.max(0, Number(next.failed) || 0);
      return next;
    });
  }, []);

  const getStageProgress = useCallback((stage: string) => STAGE_PERCENT[String(stage || "").toLowerCase()] || 0, []);

  const countBatchStatus = useCallback(() => {
    let success = 0;
    let failed = 0;
    batchFilesRef.current.forEach((item) => {
      if (item.status === "success") success += 1;
      if (item.status === "failed") failed += 1;
    });
    return { success, failed };
  }, []);
  const loadHistory = useCallback(async () => {
    setLoadingHistory(true);
    try {
      const data = await fetchJson<{ history?: HistoryItem[] }>("/history");
      setHistory(Array.isArray(data.history) ? data.history : []);
    } catch (error) {
      showError(`加载历史失败: ${String((error as Error).message || error)}`);
    } finally {
      setLoadingHistory(false);
    }
  }, [fetchJson, showError]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const stopBatchPolling = useCallback(() => {
    if (!batchTimerRef.current) return;
    clearInterval(batchTimerRef.current);
    batchTimerRef.current = null;
  }, []);

  const stopSinglePolling = useCallback(() => {
    if (!singleTimerRef.current) return;
    clearInterval(singleTimerRef.current);
    singleTimerRef.current = null;
  }, []);

  const pullSingleProgress = useCallback(async () => {
    try {
      const progress = await fetchJson<{ current_file?: string; status?: string; stage?: string; message?: string }>(
        "/single_progress",
      );
      const stage = String(progress.stage || "").toLowerCase();
      const status = String(progress.status || "").toLowerCase();
      const done = status === "completed" || stage === "done";
      const failed = status === "failed" || stage === "failed";
      if (progressVisibleRef.current) {
        setProgressText(String(progress.message || "正在分析视频..."));
      }
      updateProgressBoard({
        mode: "single",
        stage,
        percent: done || failed ? 100 : getStageProgress(stage),
        total: 1,
        current: done || failed ? 1 : 0,
        success: done ? 1 : 0,
        failed: failed ? 1 : 0,
        currentFile: String(progress.current_file || ""),
      });
    } catch {
      // ignore polling errors
    }
  }, [fetchJson, getStageProgress, updateProgressBoard]);

  const pullBatchProgress = useCallback(async () => {
    try {
      const progress = await fetchJson<{
        current_file?: string;
        status?: string;
        stage?: string;
        total?: number;
        current?: number;
        message?: string;
      }>("/batch_progress");
      const stage = String(progress.stage || "").toLowerCase();
      const status = String(progress.status || "").toLowerCase();
      const currentFile = String(progress.current_file || "");
      const total = Number(progress.total) || batchFilesRef.current.length;
      const current = Number(progress.current) || 0;
      const { success, failed } = countBatchStatus();
      let percent = 0;
      if (total > 0) {
        const doneFiles = Math.max(0, current - 1);
        percent = ((doneFiles + getStageProgress(stage) / 100) / total) * 100;
      }
      if (status === "completed" || stage === "done") {
        percent = 100;
      } else {
        percent = Math.min(99, percent);
      }
      if (progressVisibleRef.current) setProgressText(String(progress.message || "正在批量分析..."));
      updateProgressBoard({
        mode: "batch",
        stage,
        percent,
        total,
        current,
        success,
        failed,
        currentFile,
      });

      if (currentFile) {
        setBatchFiles((prev) =>
          prev.map((item) => {
            if (item.status === "success" || item.status === "failed") {
              return item;
            }
            if (item.filename === currentFile) {
              return { ...item, status: "processing" };
            }
            return item;
          }),
        );
      }
    } catch {
      // ignore polling errors
    }
  }, [countBatchStatus, fetchJson, getStageProgress, updateProgressBoard]);

  const startSinglePolling = useCallback(() => {
    stopSinglePolling();
    void pullSingleProgress();
    singleTimerRef.current = setInterval(() => void pullSingleProgress(), 1200);
  }, [pullSingleProgress, stopSinglePolling]);

  const startBatchPolling = useCallback(() => {
    stopBatchPolling();
    void pullBatchProgress();
    batchTimerRef.current = setInterval(() => void pullBatchProgress(), 1200);
  }, [pullBatchProgress, stopBatchPolling]);

  const uploadSingleFileWithResume = useCallback(
    async (file: File, fileIndex: number, totalFiles: number) => {
      const resumeKey = `${UPLOAD_RESUME_KEY_PREFIX}:${file.name}:${file.size}:${file.lastModified}`;
      const storedUploadId = window.localStorage.getItem(resumeKey) || "";
      const initData = await fetchJson<{
        upload_id: string;
        chunk_size?: number;
        total_chunks?: number;
        received_chunks?: number[];
      }>("/upload_chunk_init", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file.name,
          total_size: file.size,
          chunk_size: DEFAULT_UPLOAD_CHUNK_SIZE,
          upload_id: storedUploadId,
          file_key: resumeKey,
        }),
      });
      const uploadId = String(initData.upload_id || "");
      if (!uploadId) throw new Error("初始化上传失败");
      window.localStorage.setItem(resumeKey, uploadId);

      const chunkSize = Number(initData.chunk_size) || DEFAULT_UPLOAD_CHUNK_SIZE;
      const totalChunks = Number(initData.total_chunks) || 1;
      const receivedSet = new Set((initData.received_chunks || []).map((item) => Number(item)));

      for (let chunkIndex = 0; chunkIndex < totalChunks; chunkIndex += 1) {
        if (receivedSet.has(chunkIndex)) continue;
        const start = chunkIndex * chunkSize;
        const end = Math.min(file.size, start + chunkSize);
        const formData = new FormData();
        formData.append("upload_id", uploadId);
        formData.append("chunk_index", String(chunkIndex));
        formData.append("chunk", file.slice(start, end));
        setProgressText(`正在上传 ${file.name}（${fileIndex}/${totalFiles}，分片 ${chunkIndex + 1}/${totalChunks}）`);
        await fetchJson("/upload_chunk", { method: "POST", body: formData });
      }

      const finalized = await fetchJson<{ filename: string; filepath: string }>("/upload_chunk_finalize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId }),
      });
      window.localStorage.removeItem(resumeKey);
      return finalized;
    },
    [fetchJson],
  );

  const uploadBatchFiles = useCallback(
    async (fileList: FileList | File[]) => {
      const files = Array.from(fileList || []).filter((file) => isValidVideo(file.name));
      if (files.length === 0) {
        showError("没有可用的视频文件");
        return;
      }
      showProgress("上传中", "正在上传视频...");
      updateProgressBoard({ mode: "upload", stage: "prepare", total: files.length, percent: 0 });
      try {
        const uploaded: BatchFileItem[] = [];
        for (let i = 0; i < files.length; i += 1) {
          const item = await uploadSingleFileWithResume(files[i], i + 1, files.length);
          uploaded.push({ filename: item.filename, filepath: item.filepath, status: "pending", error: "" });
          updateProgressBoard({
            mode: "upload",
            stage: i + 1 >= files.length ? "done" : "upload",
            total: files.length,
            current: i + 1,
            success: i + 1,
            percent: Math.round(((i + 1) / files.length) * 100),
          });
        }
        setBatchFiles((prev) => [...prev, ...uploaded]);
      } catch (error) {
        showError(`上传失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [hideProgress, showError, showProgress, updateProgressBoard, uploadSingleFileWithResume],
  );
  const analyzeSingle = useCallback(async () => {
    if (batchFilesRef.current.length !== 1) return;
    const file = batchFilesRef.current[0];
    setBatchFiles((prev) => prev.map((item) => ({ ...item, status: "pending", error: "" })));
    stopBatchPolling();
    setIsAnalyzing(true);
    showProgress("单文件处理中", "正在分析视频，请稍候...");
    updateProgressBoard({ mode: "single", stage: "prepare", total: 1, percent: 5, currentFile: file.filename });
    startSinglePolling();
    let reveal = false;
    try {
      const data = await fetchJson<SingleResultData>("/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          filepath: file.filepath,
          whisper_model: whisperModel,
          use_video: useVideo,
          web_search: webSearch,
          max_vision: maxVision,
          fps,
        }),
      });
      setResultData(data);
      setBatchResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
      setBatchFiles((prev) => prev.map((item) => ({ ...item, status: "success", error: "" })));
      updateProgressBoard({
        mode: "single",
        stage: "done",
        total: 1,
        current: 1,
        success: 1,
        failed: 0,
        currentFile: file.filename,
        percent: 100,
      });
      reveal = true;
      await loadHistory();
    } catch (error) {
      const message = String((error as Error).message || error);
      if (WEB_SEARCH_ERROR_HINTS.some((hint) => message.toLowerCase().includes(hint))) setWebSearch(false);
      setBatchFiles((prev) => prev.map((item) => ({ ...item, status: "failed", error: message })));
      updateProgressBoard({
        mode: "single",
        stage: "failed",
        total: 1,
        current: 1,
        success: 0,
        failed: 1,
        currentFile: file.filename,
        percent: 100,
      });
      showError(`单文件分析失败: ${message}`);
    } finally {
      stopSinglePolling();
      setIsAnalyzing(false);
      hideProgress();
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [
    apiKey,
    fetchJson,
    fps,
    hideProgress,
    loadHistory,
    maxVision,
    showError,
    showProgress,
    startSinglePolling,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    useVideo,
    webSearch,
    whisperModel,
  ]);

  const analyzeBatch = useCallback(async () => {
    if (batchFilesRef.current.length <= 1) return;
    setBatchFiles((prev) => prev.map((item) => ({ ...item, status: "pending", error: "" })));
    stopSinglePolling();
    setIsAnalyzing(true);
    showProgress("批量处理中", "正在逐个分析视频...");
    updateProgressBoard({ mode: "batch", stage: "prepare", total: batchFilesRef.current.length, percent: 0 });
    startBatchPolling();
    let reveal = false;
    try {
      const data = await fetchJson<BatchResultData>("/analyze_batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          filepaths: batchFilesRef.current.map((item) => item.filepath),
          whisper_model: whisperModel,
          use_video: useVideo,
          web_search: webSearch,
          max_vision: maxVision,
          fps,
        }),
      });
      setBatchResultData(data);
      setResultData(null);
      setIsEditMode(false);
      setEditedSteps([]);
      const nextFiles: BatchFileItem[] = batchFilesRef.current.map((item, index) => ({
        ...item,
        status: data.results?.[index]?.success ? "success" : "failed",
        error: data.results?.[index]?.error || "",
      }));
      setBatchFiles(nextFiles);
      const success = nextFiles.filter((item) => item.status === "success").length;
      const failed = nextFiles.filter((item) => item.status === "failed").length;
      updateProgressBoard({
        mode: "batch",
        stage: "done",
        total: Number(data?.summary?.total) || nextFiles.length,
        current: Number(data?.summary?.total) || nextFiles.length,
        success: Number(data?.summary?.success) || success,
        failed: Number(data?.summary?.failed) || failed,
        currentFile: "",
        percent: 100,
      });
      reveal = true;
      await loadHistory();
    } catch (error) {
      const { success, failed } = countBatchStatus();
      updateProgressBoard({
        mode: "batch",
        stage: "failed",
        total: batchFilesRef.current.length,
        current: success + failed,
        success,
        failed,
        percent: 100,
      });
      showError(`批量分析失败: ${String((error as Error).message || error)}`);
    } finally {
      stopBatchPolling();
      setIsAnalyzing(false);
      hideProgress();
      if (reveal && resultsRef.current) resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [
    apiKey,
    fetchJson,
    fps,
    hideProgress,
    loadHistory,
    maxVision,
    countBatchStatus,
    showError,
    showProgress,
    startBatchPolling,
    stopBatchPolling,
    stopSinglePolling,
    updateProgressBoard,
    useVideo,
    webSearch,
    whisperModel,
  ]);

  const startAnalyze = useCallback(async () => {
    if (!apiKey) {
      showError("请输入 ARK API Key");
      return;
    }
    if (batchFilesRef.current.length === 1) return analyzeSingle();
    if (batchFilesRef.current.length > 1) return analyzeBatch();
    showError("请先上传视频文件");
  }, [analyzeBatch, analyzeSingle, apiKey, showError]);

  const openHistoryRecord = useCallback(
    async (recordId: string) => {
      showProgress("加载中", "正在读取历史记录...");
      try {
        const data = await fetchJson<{ record?: Partial<SingleResultData> & { steps?: StepItem[] } }>(
          `/history/${recordId}`,
        );
        const record = data.record || {};
        setResultData({
          steps: Array.isArray(record.steps) ? record.steps : [],
          markdown: record.markdown || "",
          output_dir: record.output_dir || "",
          pdf_path: record.pdf_path || "",
        });
        setBatchResultData(null);
        if (resultsRef.current) {
          resultsRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      } catch (error) {
        showError(`加载历史失败: ${String((error as Error).message || error)}`);
      } finally {
        hideProgress();
      }
    },
    [fetchJson, hideProgress, showError, showProgress],
  );

  const removeHistoryRecord = useCallback(
    async (recordId: string) => {
      if (!window.confirm("确定要删除这条历史记录吗？")) return;
      try {
        await fetchJson(`/history/${recordId}`, { method: "DELETE" });
        await loadHistory();
      } catch (error) {
        showError(`删除失败: ${String((error as Error).message || error)}`);
      }
    },
    [fetchJson, loadHistory, showError],
  );

  const saveEditedSteps = useCallback(async () => {
    if (!apiKey) return showError("请输入 ARK API Key");
    if (!resultData?.output_dir) return showError("缺少输出目录信息");
    setSavingSteps(true);
    showProgress("重新生成中", "根据编辑步骤生成新文档...");
    try {
      const data = await fetchJson<SingleResultData>("/regenerate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          api_key: apiKey,
          steps: editedSteps,
          output_dir: resultData.output_dir,
          web_search: webSearch,
        }),
      });
      setResultData(data);
      setIsEditMode(false);
      setEditedSteps([]);
    } catch (error) {
      showError(`重新生成失败: ${String((error as Error).message || error)}`);
    } finally {
      setSavingSteps(false);
      hideProgress();
    }
  }, [apiKey, editedSteps, fetchJson, hideProgress, resultData?.output_dir, showError, showProgress, webSearch]);

  const triggerDownload = useCallback((blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(url);
  }, []);

  const downloadSingleZip = useCallback(async () => {
    const outputDirName = basename(resultData?.output_dir);
    if (!outputDirName) return showError("没有可下载结果");
    try {
      const blob = await fetchBlob(`/download_zip/${encodeURIComponent(outputDirName)}`);
      triggerDownload(blob, `${outputDirName}.zip`);
    } catch (error) {
      showError(`下载失败: ${String((error as Error).message || error)}`);
    }
  }, [fetchBlob, resultData?.output_dir, showError, triggerDownload]);

  const downloadSingleFromBatch = useCallback(
    async (outputDir: string | undefined, filename: string | undefined) => {
      const outputDirName = basename(outputDir);
      if (!outputDirName) return showError("下载路径无效");
      try {
        const blob = await fetchBlob(`/download_zip/${encodeURIComponent(outputDirName)}`);
        const baseName = basename(filename).replace(/\.[^/.]+$/, "") || outputDirName;
        triggerDownload(blob, `${baseName}.zip`);
      } catch (error) {
        showError(`下载失败: ${String((error as Error).message || error)}`);
      }
    },
    [fetchBlob, showError, triggerDownload],
  );

  const downloadBatchZip = useCallback(async () => {
    const outputDirs = (batchResultData?.results || [])
      .filter((item) => item.success && item.output_dir)
      .map((item) => String(item.output_dir));
    if (outputDirs.length === 0) return showError("没有可下载批量结果");
    try {
      const blob = await fetchBlob("/download_batch_zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_dirs: outputDirs }),
      });
      triggerDownload(blob, "batch_results.zip");
    } catch (error) {
      showError(`下载失败: ${String((error as Error).message || error)}`);
    }
  }, [batchResultData?.results, fetchBlob, showError, triggerDownload]);

  const renderedMarkdown = useMemo(() => {
    if (!resultData?.markdown) return "";
    const outputDirName = basename(resultData.output_dir);
    const baseUrl = outputDirName ? `/output/${encodeURIComponent(outputDirName)}/` : "";
    const markdownText = String(resultData.markdown).replace(
      /!\[(.*?)\]\((images\/.*?)\)/g,
      (_m, alt, imgPath) => `![${alt}](${baseUrl}${imgPath})`,
    );
    return DOMPurify.sanitize(marked.parse(markdownText, { gfm: true, breaks: true }) as string);
  }, [resultData?.markdown, resultData?.output_dir]);

  const progressPercent = Math.max(0, Math.min(100, Math.round(progressBoard.percent || 0)));
  const progressModeText =
    progressBoard.mode === "upload"
      ? "上传进度"
      : progressBoard.mode === "single"
        ? "单文件分析"
        : progressBoard.mode === "batch"
          ? "批量分析"
          : "任务进度";
  const batchStatusText = (status: FileStatus) =>
    status === "success"
      ? "已完成"
      : status === "failed"
        ? "失败"
        : status === "processing"
          ? "处理中"
          : "待处理";
  const modeLabel = (mode?: string) => (mode === "video" ? "视频模式" : "字幕模式");

  const canAnalyze = !isAnalyzing && batchFiles.length > 0;
  const analyzeButtonText = isAnalyzing
    ? batchFiles.length === 1
      ? "单文件处理中..."
      : "批量处理中..."
    : batchFiles.length === 1
      ? "开始单文件分析"
      : "开始批量分析";
  const hasSingleResult = Boolean(resultData);
  const hasBatchResult = Boolean(batchResultData);
  const hasAnyResult = hasSingleResult || hasBatchResult;
  return (
    <div className="relative min-h-screen bg-neutral-950 text-neutral-100">
      <div className="pointer-events-none absolute inset-0">
        <BackgroundBeams className="opacity-70" />
      </div>
      <main className="relative z-10 mx-auto max-w-[1300px] p-4 md:p-8">
        <header className="mb-6 rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
          <h1 className="text-2xl font-bold">视频总结工作台（React）</h1>
          <p className="mt-1 text-sm text-neutral-300">流程与原项目一致：上传、分析、历史、编辑、下载。</p>
        </header>

        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          <aside className="space-y-4">
            <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
              <h2 className="mb-2 text-sm font-semibold">配置选项</h2>
              <input className="mb-2 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm" type="password" placeholder="ARK API Key" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              <select className="mb-2 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm" value={whisperModel} onChange={(e) => setWhisperModel(e.target.value)}>
                <option value="tiny">tiny</option><option value="base">base</option><option value="small">small</option><option value="medium">medium</option><option value="large">large</option>
              </select>
              <input className="mb-2 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm" type="number" min={0} max={10} value={maxVision} onChange={(e) => setMaxVision(Number(e.target.value) || 0)} />
              <label className="mb-2 flex items-center gap-2 text-sm"><input type="checkbox" checked={useVideo} onChange={(e) => setUseVideo(e.target.checked)} />视频上传模式</label>
              {useVideo ? <input className="mb-2 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm" type="number" min={0.1} max={10} step={0.1} value={fps} onChange={(e) => setFps(Number(e.target.value) || 1)} /> : null}
              <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={webSearch} onChange={(e) => setWebSearch(e.target.checked)} />联网搜索增强</label>
            </section>

            <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
              <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">历史记录</h2><button className="rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => void loadHistory()}>{loadingHistory ? "刷新中..." : "刷新"}</button></div>
              <div className="max-h-72 space-y-2 overflow-auto">
                {history.length === 0 ? <p className="text-sm text-neutral-500">暂无历史记录</p> : null}
                {history.map((record) => (
                  <div key={record.id} className="rounded border border-neutral-800 bg-neutral-950/60 p-2">
                    <button className="w-full text-left" onClick={() => void openHistoryRecord(record.id)}>
                      <p className="truncate text-sm font-medium">{record.video_name}</p>
                      <p className="text-xs text-neutral-500">{modeLabel(record.mode)} · {record.steps_count || 0} 步 · {record.timestamp || ""}</p>
                    </button>
                    <button className="mt-1 rounded border border-rose-500/40 px-2 py-0.5 text-xs text-rose-300" onClick={() => void removeHistoryRecord(record.id)}>删除</button>
                  </div>
                ))}
              </div>
            </section>
          </aside>

          <section className="space-y-4">
            <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
              <h2 className="mb-2 text-sm font-semibold">上传视频</h2>
              <input ref={fileInputRef} type="file" accept="video/*" multiple className="hidden" onChange={(e) => { const files = e.target.files; if (files) void uploadBatchFiles(files); e.target.value = ""; }} />
              <div className={`rounded border-2 border-dashed p-5 text-center ${batchDragOver ? "border-teal-400 bg-teal-500/10" : "border-neutral-700 bg-neutral-950/50"}`} onClick={() => fileInputRef.current?.click()} onDragOver={(e) => { e.preventDefault(); setBatchDragOver(true); }} onDragLeave={() => setBatchDragOver(false)} onDrop={(e) => { e.preventDefault(); setBatchDragOver(false); if (e.dataTransfer.files) void uploadBatchFiles(e.dataTransfer.files); }}>
                点击或拖拽上传单个/多个视频
              </div>
              <div className="mt-2 space-y-2">
                {batchFiles.map((item, index) => (
                  <div key={`${item.filepath}-${index}`} className="flex items-center justify-between rounded border border-neutral-800 bg-neutral-950/60 p-2">
                    <div className="min-w-0"><p className="truncate text-sm">{item.filename}</p><p className="text-xs text-neutral-500">{batchStatusText(item.status)}{item.error ? ` · ${item.error}` : ""}</p></div>
                    {batchFiles.length > 1 ? <button className="rounded border border-neutral-700 px-2 py-1 text-xs" disabled={isAnalyzing} onClick={() => setBatchFiles((prev) => prev.filter((_, i) => i !== index))}>删除</button> : null}
                  </div>
                ))}
              </div>
              {batchFiles.length > 0 ? <button className="mt-2 w-full rounded border border-neutral-700 px-3 py-1.5 text-sm" onClick={() => setBatchFiles([])}>清空列表</button> : null}
              <button className="mt-3 w-full rounded bg-teal-600 px-4 py-2 text-sm font-medium disabled:bg-neutral-700" disabled={!canAnalyze} onClick={() => void startAnalyze()}>{analyzeButtonText}</button>
            </section>

            {hasAnyResult ? (
              <div ref={resultsRef} className="grid gap-4 xl:grid-cols-2">
                {hasBatchResult ? (
                  <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4 xl:col-span-2">
                    <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">批量处理结果</h2><button className="rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => void downloadBatchZip()}>下载批量 ZIP</button></div>
                    <div className="space-y-2">{(batchResultData?.results || []).map((r, i) => <div key={`${r.filename}-${i}`} className="rounded border border-neutral-800 bg-neutral-950/60 p-2"><div className="flex items-center justify-between"><p className="truncate text-sm font-medium">{r.filename}</p><span className={`text-xs ${r.success ? "text-emerald-300" : "text-rose-300"}`}>{r.success ? "成功" : "失败"}</span></div>{r.success ? <button className="mt-1 rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => void downloadSingleFromBatch(r.output_dir, r.filename)}>下载</button> : <p className="mt-1 text-xs text-rose-300">{r.error || "处理失败"}</p>}</div>)}</div>
                  </section>
                ) : null}

                {hasSingleResult ? (
                  <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
                    <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">识别到的步骤</h2>{!isEditMode ? <button className="rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => { if (!resultData?.steps?.length) return showError("当前没有可编辑步骤"); setEditedSteps(clone(resultData.steps).map((s, i) => ({ ...s, step: i + 1, time: s.time || "00:00", title: s.title || "", description: s.description || "" }))); setIsEditMode(true); }}>编辑</button> : null}</div>
                    {!isEditMode ? <div className="max-h-96 space-y-2 overflow-auto">{(resultData?.steps || []).map((step, i) => <div key={`s-${i}`} className="rounded border border-neutral-800 bg-neutral-950/60 p-2"><p className="text-xs text-neutral-500">#{step.step || i + 1} · {step.time || "00:00"}</p><p className="text-sm font-medium">{step.title || "未命名步骤"}</p><p className="text-sm text-neutral-300">{step.description || ""}</p></div>)}</div> : <div className="max-h-96 overflow-auto"><div className="mb-2 flex gap-2"><button disabled={savingSteps} className="rounded bg-teal-600 px-2 py-1 text-xs" onClick={() => void saveEditedSteps()}>保存并重生成</button><button disabled={savingSteps} className="rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => { setIsEditMode(false); setEditedSteps([]); }}>取消</button></div><div className="space-y-2">{editedSteps.map((step, index) => <div key={`e-${index}`} draggable onDragStart={() => setDragIndex(index)} onDragOver={(e) => { e.preventDefault(); setDragOverIndex(index); }} onDrop={(e) => { e.preventDefault(); if (dragIndex === null || dragIndex === index) return; setEditedSteps((prev) => { const next = [...prev]; const [moved] = next.splice(dragIndex, 1); if (!moved) return prev; next.splice(index, 0, moved); return next.map((s, i) => ({ ...s, step: i + 1 })); }); setDragIndex(null); setDragOverIndex(null); }} onDragEnd={() => { setDragIndex(null); setDragOverIndex(null); }} className={`rounded border p-2 ${dragIndex === index ? "border-teal-500/50 opacity-60" : dragOverIndex === index ? "border-teal-400" : "border-neutral-800"}`}><div className="mb-1 flex gap-2"><input className="flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" value={step.title || ""} onChange={(e) => setEditedSteps((prev) => prev.map((item, idx) => (idx === index ? { ...item, title: e.target.value } : item)))} /><input className="w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" value={step.time || ""} onChange={(e) => setEditedSteps((prev) => prev.map((item, idx) => (idx === index ? { ...item, time: e.target.value } : item)))} /></div><textarea className="min-h-16 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-sm" value={step.description || ""} onChange={(e) => setEditedSteps((prev) => prev.map((item, idx) => (idx === index ? { ...item, description: e.target.value } : item)))} /><button className="mt-1 rounded border border-rose-500/40 px-2 py-1 text-xs text-rose-300" onClick={() => setEditedSteps((prev) => prev.filter((_, idx) => idx !== index).map((s, i) => ({ ...s, step: i + 1 })))}>删除</button></div>)}</div><button className="mt-2 w-full rounded border border-dashed border-neutral-700 px-3 py-1.5 text-sm" onClick={() => setEditedSteps((prev) => [...prev, { step: prev.length + 1, time: "00:00", title: "新步骤", description: "请输入步骤描述" }])}>添加新步骤</button></div>}
                  </section>
                ) : null}

                {hasSingleResult ? (
                  <section className="rounded-xl border border-neutral-800 bg-neutral-900/70 p-4">
                    <div className="mb-2 flex items-center justify-between"><h2 className="text-sm font-semibold">生成的总结文档</h2><button className="rounded border border-neutral-700 px-2 py-1 text-xs" onClick={() => void downloadSingleZip()}>下载 ZIP</button></div>
                    <div className="prose prose-invert max-w-none text-sm" dangerouslySetInnerHTML={{ __html: renderedMarkdown }} />
                  </section>
                ) : null}
              </div>
            ) : null}
          </section>
        </div>
      </main>

      {progressVisible ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-md rounded-xl border border-neutral-700 bg-neutral-900 p-4">
            <h3 className="text-base font-semibold">{progressTitle}</h3>
            <p className="mt-1 text-sm text-neutral-300">{progressText}</p>
            <div className="mt-3 rounded border border-neutral-800 bg-neutral-950/70 p-3">
              <div className="mb-1 flex items-center justify-between text-xs text-neutral-400"><span>{progressModeText}</span><span>{progressPercent}%</span></div>
              <div className="h-2 overflow-hidden rounded bg-neutral-800"><div className="h-full bg-teal-500" style={{ width: `${progressPercent}%` }} /></div>
              {progressBoard.total > 0 ? <p className="mt-1 text-xs text-neutral-400">进度 {progressBoard.current}/{progressBoard.total}</p> : null}
              {progressBoard.success > 0 || progressBoard.failed > 0 ? <p className="text-xs text-neutral-400">成功 {progressBoard.success} · 失败 {progressBoard.failed}</p> : null}
              {progressBoard.stage ? <p className="text-xs text-neutral-400">阶段: {STAGE_LABELS[progressBoard.stage] || progressBoard.stage}</p> : null}
              {progressBoard.currentFile ? <p className="truncate text-xs text-teal-300">当前文件: {progressBoard.currentFile}</p> : null}
            </div>
          </div>
        </div>
      ) : null}

      {showErrorToast ? <div className="fixed bottom-5 left-1/2 z-50 w-[min(92vw,560px)] -translate-x-1/2 rounded border border-red-400/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">{errorMessage}</div> : null}
    </div>
  );
}
