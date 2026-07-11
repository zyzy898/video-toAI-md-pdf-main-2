"""Regression tests for the frontend analysis-task lifecycle helpers."""

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TASK_LIFECYCLE_MODULE = (
    REPO_ROOT / "web-react" / "src" / "lib" / "task-lifecycle.ts"
).as_uri()


def _run_node_assertion(script_body: str) -> None:
    script = f"""
import assert from "node:assert/strict";
import {{
  TASK_STATUS_LABELS,
  createTaskQueueItem,
  failedBatchFilepaths,
  findReselectableUpload,
  markTaskUnavailable,
  parseLifecycleState,
  runUploadCancellation,
  serializeLifecycleState,
  shouldPollTask,
}} from {json.dumps(TASK_LIFECYCLE_MODULE)};

{script_body}
"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _run_quality_node_assertion(script_body: str) -> None:
    script = f"""
import assert from "node:assert/strict";
import * as lifecycle from {json.dumps(TASK_LIFECYCLE_MODULE)};
const {{
  batchRetryFilepathForItem,
  batchRetryFilepathsForTask,
  canPresentTaskResult,
  classifyResultLoadFailure,
  completionNotificationKey,
  newlyCompletedTasks,
  pendingCompletedTasks,
  resultLoadRetryDelayMs,
  safeStorageGet,
  safeStorageRemove,
  safeStorageSet,
  selectBatchTaskCenterItems,
  shouldSendBrowserCompletionNotification,
  upsertTaskQueueItem,
}} = lifecycle;

{script_body}
"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _run_cached_presentation_assertion(script_body: str) -> None:
    script = f"""
import assert from "node:assert/strict";
import * as lifecycle from {json.dumps(TASK_LIFECYCLE_MODULE)};

const selectCachedResult = lifecycle.cachedTaskResultForPresentation;
assert.equal(
  typeof selectCachedResult,
  "function",
  "completed task results need a cache-aware presentation selector",
);

{script_body}
"""
    result = subprocess.run(
        ["node", "--experimental-strip-types", "--input-type=module", "--eval", script],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_lifecycle_persistence_excludes_secrets_and_marks_upload_for_reselection():
    _run_node_assertion(
        """
const serialized = serializeLifecycleState({
  tasks: [{
    taskId: "task-1",
    kind: "single",
    status: "queued",
    stage: "queued",
    message: "等待处理",
    percent: 0,
    total: 1,
    current: 0,
    currentFile: "clip.mp4",
    retryable: false,
    cancelRequested: false,
    attemptCount: 0,
    recoveryCount: 0,
    payload: {
      filepath: "uploads/clip.mp4",
      output_template: "content_summary",
      apiKey: "must-not-persist",
      api_key: "must-not-persist-either",
    },
    label: "clip.mp4",
    createdAt: "2026-07-10T00:00:00.000Z",
  }, {
    taskId: "task-url",
    kind: "url",
    status: "queued",
    payload: { url: "https://example.test/video" },
    label: "url_video.mp4",
    clientId: "url-1",
    createdAt: "2026-07-10T00:00:01.000Z",
  }],
  uploads: [{
    clientId: "upload-1",
    filename: "clip.mp4",
    filepath: "",
    status: "uploading",
    error: "正在上传",
    sourceKey: "source-key",
    resumeKey: "resume-key",
    size: 2048,
    lastModified: 1234,
    file: { name: "clip.mp4", bytes: "must-not-persist" },
  }, {
    clientId: "url-1",
    filename: "url_video.mp4",
    filepath: "",
    status: "processing",
    error: "正在分析链接",
  }, {
    clientId: "import-only",
    filename: "import_video.mp4",
    filepath: "",
    status: "processing",
    error: "正在导入链接",
  }],
});

assert.equal(serialized.includes("must-not-persist"), false);
const restored = parseLifecycleState(serialized);
assert.deepEqual(restored.tasks[0].payload, {
  filepath: "uploads/clip.mp4",
  output_template: "content_summary",
});
assert.equal(restored.uploads[0].status, "uploading");
assert.equal(restored.uploads[0].needsReselect, true);
assert.match(restored.uploads[0].error, /重新选择同一文件/);
assert.equal("file" in restored.uploads[0], false);
assert.equal(restored.uploads[1].status, "processing");
assert.equal(restored.uploads[1].needsReselect, false);
assert.equal(restored.uploads[2].status, "failed");
assert.match(restored.uploads[2].error, /刷新|重新提交/);
"""
    )


def test_corrupt_lifecycle_state_is_ignored():
    _run_node_assertion(
        """
assert.deepEqual(parseLifecycleState("not-json"), { version: 1, tasks: [], uploads: [] });
assert.deepEqual(parseLifecycleState(null), { version: 1, tasks: [], uploads: [] });
"""
    )


def test_deleted_task_becomes_terminal_recoverable_ui_failure():
    _run_node_assertion(
        """
const queued = {
  taskId: "gone-task",
  kind: "single",
  status: "queued",
  payload: { filepath: "uploads/clip.mp4" },
  label: "clip.mp4",
  createdAt: "2026-07-10T00:00:00.000Z",
};
assert.equal(shouldPollTask(queued), true);

const unavailable = markTaskUnavailable(queued);
assert.equal(unavailable.status, "failed");
assert.equal(unavailable.retryable, false);
assert.match(unavailable.message, /任务不存在|重新提交/);
assert.equal(shouldPollTask(unavailable), false);
assert.equal(TASK_STATUS_LABELS.uploading, "上传中");
assert.equal(TASK_STATUS_LABELS.queued, "排队中");
assert.equal(TASK_STATUS_LABELS.analyzing, "分析中");
assert.equal(TASK_STATUS_LABELS.failed, "失败");
assert.equal(TASK_STATUS_LABELS.cancelled, "已取消");
"""
    )


def test_task_queue_item_normalizes_public_status_and_keeps_safe_metadata():
    _run_node_assertion(
        """
const item = createTaskQueueItem(
  {
    task_id: "task-2",
    kind: "batch",
    status: "analyzing",
    stage: "analysis",
    message: "working",
    percent: 42.5,
    total: 3,
    current: 2,
    current_file: "two.mp4",
    retryable: false,
    cancel_requested: true,
    attempt_count: 2,
    recovery_count: 1,
  },
  {
    payload: { filepaths: ["uploads/one.mp4", "uploads/two.mp4"], apiKey: "secret" },
    label: "2 个视频",
    createdAt: "2026-07-10T01:00:00.000Z",
  },
);

assert.equal(item.taskId, "task-2");
assert.equal(item.currentFile, "two.mp4");
assert.equal(item.cancelRequested, true);
assert.equal(item.attemptCount, 2);
assert.deepEqual(item.payload, { filepaths: ["uploads/one.mp4", "uploads/two.mp4"] });
assert.equal(item.createdAt, "2026-07-10T01:00:00.000Z");
"""
    )


def test_reselection_matches_only_an_incomplete_copy_of_the_same_file():
    _run_node_assertion(
        """
const uploads = [
  { clientId: "done", sourceKey: "same", status: "pending", needsReselect: false },
  { clientId: "resume", sourceKey: "same", status: "uploading", needsReselect: true },
  { clientId: "other", sourceKey: "other", status: "cancelled", needsReselect: true },
];

assert.equal(findReselectableUpload(uploads, "same")?.clientId, "resume");
assert.equal(findReselectableUpload(uploads, "missing"), undefined);
"""
    )


def test_batch_retry_uses_only_failed_filepaths():
    _run_node_assertion(
        """
const filepaths = ["uploads/one.mp4", "uploads/two.mp4", "uploads/three.mp4"];
const results = [
  { index: 2, filename: "two.mp4", success: false, error: "provider busy" },
  { index: 3, filename: "three.mp4", success: false, result_mode: "blocked_notice" },
  { index: 1, filename: "one.mp4", success: true },
];

assert.deepEqual(failedBatchFilepaths(filepaths, results), ["uploads/two.mp4"]);
assert.deepEqual(failedBatchFilepaths(filepaths, []), []);
assert.deepEqual(
  failedBatchFilepaths(filepaths, [{ index: 99, filename: "unknown.mp4", success: false }]),
  [],
);
assert.deepEqual(
  failedBatchFilepaths(filepaths, [{ index: 99, filename: "two.mp4", success: false }]),
  ["uploads/two.mp4"],
);
assert.deepEqual(
  failedBatchFilepaths(
    ["uploads/a/clip.mp4", "uploads/b/clip.mp4"],
    [{ filename: "clip.mp4", success: false }],
  ),
  [],
);
assert.deepEqual(
  failedBatchFilepaths(filepaths, [{ index: 1, filename: "two.mp4", success: false }]),
  ["uploads/one.mp4"],
);
"""
    )


def test_upload_cancel_keeps_resume_state_until_server_confirms():
    _run_node_assertion(
        """
const rejectedCalls = [];
const rejection = new Error("finalizing");
const rejected = await runUploadCancellation({
  uploadId: "upload-1",
  abort: () => rejectedCalls.push("abort"),
  cancel: async () => {
    rejectedCalls.push("cancel");
    throw rejection;
  },
  clearResume: () => rejectedCalls.push("clear"),
});
assert.equal(rejected.confirmed, false);
assert.equal(rejected.error, rejection);
assert.deepEqual(rejectedCalls, ["abort", "cancel"]);

const confirmedCalls = [];
const confirmed = await runUploadCancellation({
  uploadId: "upload-2",
  abort: () => confirmedCalls.push("abort"),
  cancel: async () => confirmedCalls.push("cancel"),
  clearResume: () => confirmedCalls.push("clear"),
});
assert.equal(confirmed.confirmed, true);
assert.deepEqual(confirmedCalls, ["abort", "cancel", "clear"]);

const unknownCalls = [];
const unknown = await runUploadCancellation({
  uploadId: "",
  abort: () => unknownCalls.push("abort"),
  cancel: async () => unknownCalls.push("cancel"),
  clearResume: () => unknownCalls.push("clear"),
});
assert.equal(unknown.confirmed, false);
assert.match(String(unknown.error?.message || unknown.error), /upload_id|初始化/);
assert.deepEqual(unknownCalls, ["abort"]);
"""
    )


def test_only_presented_completed_task_is_selected_for_result_loading():
    _run_quality_node_assertion(
        """
const tasks = [
  { taskId: "old-complete", status: "completed" },
  { taskId: "new-complete", status: "completed" },
  { taskId: "already-loaded", status: "completed" },
  { taskId: "currently-loading", status: "completed" },
  { taskId: "waiting-for-own-retry", status: "completed" },
  { taskId: "still-running", status: "analyzing" },
];

const pending = pendingCompletedTasks(
  tasks,
  new Set(["already-loaded"]),
  new Set(["currently-loading"]),
  new Set(["waiting-for-own-retry"]),
  "new-complete",
);
assert.deepEqual(pending.map((task) => task.taskId), ["new-complete"]);
assert.deepEqual(pendingCompletedTasks(tasks).map((task) => task.taskId), []);
"""
    )


def test_submitting_a_new_task_preserves_completed_result_producers():
    _run_quality_node_assertion(
        """
const completedProducer = { taskId: "batch-source", status: "completed" };
const awaitingResultRetry = { taskId: "awaiting-result", status: "completed" };
const replacement = { taskId: "new-task", status: "queued" };
const queue = upsertTaskQueueItem(
  [completedProducer, awaitingResultRetry, { taskId: "new-task", status: "failed" }],
  replacement,
);

assert.deepEqual(
  queue.map((task) => task.taskId),
  ["batch-source", "awaiting-result", "new-task"],
);
assert.equal(queue[2], replacement);

const filler = Array.from({ length: 19 }, (_, index) => ({
  taskId: `old-${index}`,
  status: "failed",
}));
const fullQueue = upsertTaskQueueItem(
  [completedProducer, ...filler],
  replacement,
);
assert.equal(fullQueue.length, 21);
assert.equal(fullQueue.some((task) => task.taskId === completedProducer.taskId), true);
assert.equal(fullQueue.some((task) => task.taskId === replacement.taskId), true);
assert.equal(fullQueue.some((task) => task.taskId === "old-0"), true);
"""
    )


def test_task_submission_gate_rejects_concurrent_duplicate_requests():
    _run_quality_node_assertion(
        """
assert.equal(typeof lifecycle.runExclusiveTaskSubmission, "function");
const gate = { current: false };
let releaseFirst;
let callCount = 0;
const first = lifecycle.runExclusiveTaskSubmission(gate, async () => {
  callCount += 1;
  await new Promise((resolve) => { releaseFirst = resolve; });
  return "first";
});
const duplicate = await lifecycle.runExclusiveTaskSubmission(gate, async () => {
  callCount += 1;
  return "duplicate";
});
assert.equal(duplicate, undefined);
assert.equal(callCount, 1);
assert.equal(gate.current, true);
releaseFirst();
assert.equal(await first, "first");
assert.equal(gate.current, false);
assert.equal(
  await lifecycle.runExclusiveTaskSubmission(gate, async () => {
    callCount += 1;
    return "next";
  }),
  "next",
);
assert.equal(callCount, 2);
"""
    )


def test_server_task_history_rehydrates_complete_queue_without_losing_local_metadata():
    _run_quality_node_assertion(
        """
assert.equal(typeof lifecycle.mergeServerTaskQueue, "function");
const serverTasks = Array.from({ length: 25 }, (_, index) => ({
  task_id: `task-${index}`,
  kind: "batch",
  status: index === 24 ? "analyzing" : "completed",
  created_at: 1_700_000_000 + index,
  payload: {
    filepaths: [`uploads/video-${index}.mp4`],
    output_template: "operation_guide",
  },
}));
const local = [{
  taskId: "task-24",
  kind: "batch",
  status: "queued",
  stage: "queued",
  message: "",
  percent: 0,
  total: 1,
  current: 0,
  currentFile: "",
  retryable: false,
  cancelRequested: false,
  attemptCount: 0,
  recoveryCount: 0,
  payload: serverTasks[24].payload,
  label: "local label",
  clientId: "client-24",
  createdAt: "2023-11-14T22:13:44.000Z",
}];
const merged = lifecycle.mergeServerTaskQueue(local, serverTasks);
assert.equal(merged.length, 25);
assert.equal(merged.some((task) => task.taskId === "task-0"), true);
assert.equal(merged[24].taskId, "task-24");
assert.equal(merged[24].status, "analyzing");
assert.equal(merged[24].label, "local label");
assert.equal(merged[24].clientId, "client-24");
"""
    )


def test_stale_result_cannot_present_and_batch_retry_uses_exact_producer():
    _run_quality_node_assertion(
        """
const oldRequest = { taskId: "old-task", revision: 1 };
const newerPresentation = { taskId: "new-task", revision: 2 };
const userPresentation = { taskId: "", revision: 3 };

assert.equal(canPresentTaskResult(oldRequest, newerPresentation), false);
assert.equal(canPresentTaskResult(oldRequest, userPresentation), false);
assert.equal(canPresentTaskResult(newerPresentation, newerPresentation), true);

const tasks = [
  {
    taskId: "batch-old",
    kind: "batch",
    status: "completed",
    payload: { filepaths: ["uploads/old-one.mp4", "uploads/old-two.mp4"] },
  },
  {
    taskId: "batch-new",
    kind: "batch",
    status: "completed",
    payload: { filepaths: ["uploads/new-one.mp4", "uploads/new-two.mp4"] },
  },
];
const results = [{ index: 2, filename: "old-two.mp4", success: false }];
assert.deepEqual(
  batchRetryFilepathsForTask(tasks, "batch-old", results),
  ["uploads/old-two.mp4"],
);
assert.deepEqual(batchRetryFilepathsForTask(tasks, "missing", results), []);
"""
    )


def test_result_failure_classification_and_backoff_are_recoverable():
    _run_quality_node_assertion(
        """
assert.equal(classifyResultLoadFailure(404), "unavailable");
assert.equal(classifyResultLoadFailure(500), "retry");
assert.equal(classifyResultLoadFailure(undefined), "retry");
assert.equal(resultLoadRetryDelayMs(0), 1000);
assert.equal(resultLoadRetryDelayMs(1), 2000);
assert.equal(resultLoadRetryDelayMs(20), 30000);
"""
    )


def test_safe_storage_helpers_swallow_restriction_errors():
    _run_quality_node_assertion(
        """
const throwingStorage = {
  getItem() { throw new Error("blocked get"); },
  setItem() { throw new Error("blocked set"); },
  removeItem() { throw new Error("blocked remove"); },
};
assert.equal(safeStorageGet(throwingStorage, "resume", "fallback"), "fallback");
assert.equal(safeStorageSet(throwingStorage, "resume", "upload-1"), false);
assert.equal(safeStorageRemove(throwingStorage, "resume"), false);

const throwingStorageSource = () => { throw new Error("blocked storage getter"); };
assert.equal(safeStorageGet(throwingStorageSource, "resume", "factory-fallback"), "factory-fallback");
assert.equal(safeStorageSet(throwingStorageSource, "resume", "upload-1"), false);
assert.equal(safeStorageRemove(throwingStorageSource, "resume"), false);

const values = new Map();
const memoryStorage = {
  getItem(key) { return values.get(key) ?? null; },
  setItem(key, value) { values.set(key, value); },
  removeItem(key) { values.delete(key); },
};
assert.equal(safeStorageSet(memoryStorage, "resume", "upload-2"), true);
assert.equal(safeStorageGet(memoryStorage, "resume", ""), "upload-2");
assert.equal(safeStorageRemove(memoryStorage, "resume"), true);
assert.equal(safeStorageGet(memoryStorage, "resume", "missing"), "missing");
assert.equal(safeStorageSet(() => memoryStorage, "resume", "upload-3"), true);
assert.equal(safeStorageGet(() => memoryStorage, "resume", ""), "upload-3");
assert.equal(safeStorageRemove(() => memoryStorage, "resume"), true);
"""
    )


def test_background_loaded_result_can_present_when_auto_target_returns():
    _run_cached_presentation_assertion(
        """
const cache = new Map();
const batchData = { results: [{ index: 1, filename: "older.mp4", success: true }] };

// The older completed task reconciles in the background without a presentation token.
cache.set("older-task", { taskId: "older-task", kind: "batch", data: batchData });
assert.equal(
  selectCachedResult(cache, undefined, { taskId: "newer-task", revision: 2 }),
  undefined,
);

// Once the newer target is gone, a fresh token must make the cached result displayable.
const returnedTarget = { taskId: "older-task", revision: 3 };
const selected = selectCachedResult(cache, returnedTarget, returnedTarget);
assert.equal(selected.taskId, "older-task");
assert.equal(selected.kind, "batch");
assert.equal(selected.data, batchData);
"""
    )


def test_inflight_result_can_present_with_fresh_token_after_target_returns():
    _run_cached_presentation_assertion(
        """
const cache = new Map();
const requestToken = { taskId: "url-task", revision: 1 };
const changedTarget = { taskId: "newer-task", revision: 2 };
const urlData = { steps: [], markdown: "done", output_dir: "url-output" };

// The request started for url-task, then completed after its original token became stale.
cache.set("url-task", { taskId: "url-task", kind: "url", data: urlData });
assert.equal(selectCachedResult(cache, requestToken, changedTarget), undefined);

// Returning to url-task upgrades presentation through a fresh token, without another fetch.
const returnedTarget = { taskId: "url-task", revision: 3 };
const selected = selectCachedResult(cache, returnedTarget, returnedTarget);
assert.equal(selected.taskId, "url-task");
assert.equal(selected.kind, "url");
assert.equal(selected.data, urlData);
"""
    )


def test_task_status_card_uses_a_light_theme_surface():
    app_source = (REPO_ROOT / "web-react" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )
    theme_source = (REPO_ROOT / "web-react" / "src" / "theme.css").read_text(
        encoding="utf-8"
    )

    assert (
        'className="vi-task-row rounded border border-neutral-800 '
        'bg-neutral-950/55 px-3 py-2.5"'
    ) in app_source
    light_rule = theme_source.split(
        ':root[data-theme="light"] .vi-task-row {', 1
    )[1].split("}", 1)[0]
    assert "border-color: var(--vi-border)" in light_rule
    assert "background:" in light_rule
    assert "255, 255, 255" in light_rule


def test_single_failed_batch_item_retry_maps_by_index_and_fails_closed():
    _run_quality_node_assertion(
        """
const tasks = [{
  taskId: "batch-source",
  kind: "batch",
  status: "completed",
  payload: {
    filepaths: [
      "uploads/a/clip.mp4",
      "uploads/b/clip.mp4",
      "uploads/three.mp4",
    ],
  },
}];

assert.equal(
  batchRetryFilepathForItem(
    tasks,
    "batch-source",
    { index: 2, filename: "clip.mp4", success: false, error: "provider busy" },
  ),
  "uploads/b/clip.mp4",
);
assert.equal(
  batchRetryFilepathForItem(
    tasks,
    "batch-source",
    { filename: "clip.mp4", success: false, error: "provider busy" },
  ),
  "",
);
assert.equal(
  batchRetryFilepathForItem(
    tasks,
    "batch-source",
    { index: 3, filename: "three.mp4", success: false, result_mode: "blocked_notice" },
  ),
  "",
);
assert.equal(
  batchRetryFilepathForItem(
    tasks,
    "missing-task",
    { index: 3, filename: "three.mp4", success: false },
  ),
  "",
);
"""
    )


def test_batch_task_center_keeps_completed_batches_and_filters_without_mutating():
    _run_quality_node_assertion(
        """
const tasks = [
  { taskId: "old-complete", kind: "batch", status: "completed", createdAt: "2026-07-10T01:00:00Z" },
  { taskId: "single", kind: "single", status: "analyzing", createdAt: "2026-07-10T04:00:00Z" },
  { taskId: "new-failed", kind: "batch", status: "failed", createdAt: "2026-07-10T03:00:00Z" },
  { taskId: "middle-running", kind: "batch", status: "analyzing", createdAt: "2026-07-10T02:00:00Z" },
];

assert.deepEqual(
  selectBatchTaskCenterItems(tasks).map((task) => task.taskId),
  ["new-failed", "middle-running", "old-complete"],
);
assert.deepEqual(
  selectBatchTaskCenterItems(tasks, "completed").map((task) => task.taskId),
  ["old-complete"],
);
assert.deepEqual(tasks.map((task) => task.taskId), [
  "old-complete",
  "single",
  "new-failed",
  "middle-running",
]);
"""
    )


def test_completion_notifications_fire_once_per_completed_attempt_and_only_in_hidden_tabs():
    _run_quality_node_assertion(
        """
const previous = [
  { taskId: "batch-a", status: "analyzing", attemptCount: 0 },
  { taskId: "batch-b", status: "completed", attemptCount: 0 },
  { taskId: "batch-retry", status: "queued", attemptCount: 2 },
];
const current = [
  { taskId: "batch-a", status: "completed", attemptCount: 0 },
  { taskId: "batch-b", status: "completed", attemptCount: 0 },
  { taskId: "batch-retry", status: "completed", attemptCount: 2 },
  { taskId: "hydrated-complete", status: "completed", attemptCount: 0 },
];

assert.equal(completionNotificationKey(current[0]), "batch-a:0");
assert.deepEqual(
  newlyCompletedTasks(previous, current, new Set()).map((task) => task.taskId),
  ["batch-a", "batch-retry"],
);
assert.deepEqual(
  newlyCompletedTasks(previous, current, new Set(["batch-a:0"])).map((task) => task.taskId),
  ["batch-retry"],
);
assert.equal(
  shouldSendBrowserCompletionNotification({
    enabled: true,
    visibilityState: "hidden",
    permission: "granted",
  }),
  true,
);
for (const options of [
  { enabled: false, visibilityState: "hidden", permission: "granted" },
  { enabled: true, visibilityState: "visible", permission: "granted" },
  { enabled: true, visibilityState: "hidden", permission: "default" },
  { enabled: true, visibilityState: "hidden", permission: "denied" },
]) {
  assert.equal(shouldSendBrowserCompletionNotification(options), false);
}
"""
    )


def test_batch_file_rows_follow_cumulative_per_file_progress():
    _run_quality_node_assertion(
        """
const reconcileTaskFiles = lifecycle.reconcileTaskFiles;
assert.equal(
  typeof reconcileTaskFiles,
  "function",
  "batch task updates need a per-file reconciliation helper",
);

const initialFiles = [
  {
    filename: "test1_50ae17733efb4feba009f4dde252ff6a.mp4",
    filepath: "uploads/test1_50ae17733efb4feba009f4dde252ff6a.mp4",
    status: "processing",
    error: "正在分析视频...",
  },
  {
    filename: "test2_5ddc76620c054b81a706c01bd5f07a85.mp4",
    filepath: "uploads/test2_5ddc76620c054b81a706c01bd5f07a85.mp4",
    status: "processing",
    error: "正在分析视频...",
  },
];
const task = {
  taskId: "batch-1",
  kind: "batch",
  status: "analyzing",
  stage: "done",
  message: "已完成 1/2：test1_50ae17733efb4feba009f4dde252ff6a.mp4 分析完成",
  percent: 50,
  total: 2,
  current: 1,
  currentFile: "test1_50ae17733efb4feba009f4dde252ff6a.mp4",
  retryable: false,
  cancelRequested: false,
  attemptCount: 1,
  recoveryCount: 0,
  payload: { filepaths: initialFiles.map((item) => item.filepath) },
  label: "2 个视频",
  createdAt: "2026-07-10T00:00:00Z",
  fileProgress: [
    {
      index: 1,
      filename: initialFiles[0].filename,
      status: "success",
      stage: "done",
      message: "已完成 1/2：test1_50ae17733efb4feba009f4dde252ff6a.mp4 分析完成",
    },
    {
      index: 2,
      filename: initialFiles[1].filename,
      status: "analyzing",
      stage: "analysis",
      message: "正在分析 test2_5ddc76620c054b81a706c01bd5f07a85.mp4",
    },
  ],
};

const partial = reconcileTaskFiles(initialFiles, task);
assert.equal(partial[0].status, "success");
assert.match(partial[0].error, /test1_.*分析完成/u);
assert.equal(partial[1].status, "processing");
assert.equal(partial[1].error, "正在分析 test2_5ddc76620c054b81a706c01bd5f07a85.mp4");
assert.doesNotMatch(partial[1].error, /test1_/u);

const next = reconcileTaskFiles(partial, {
  ...task,
  stage: "subtitle",
  currentFile: initialFiles[1].filename,
  message: "正在识别 test2 字幕",
  fileProgress: [
    task.fileProgress[0],
    { ...task.fileProgress[1], stage: "subtitle", message: "正在识别 test2 字幕" },
  ],
});
assert.equal(next[0].status, "success");
assert.match(next[0].error, /test1_.*分析完成/u);
assert.equal(next[1].status, "processing");
assert.equal(next[1].error, "正在识别 test2 字幕");
"""
    )


def test_app_wires_task_updates_through_per_file_reconciliation():
    app_source = (REPO_ROOT / "web-react" / "src" / "App.tsx").read_text(
        encoding="utf-8"
    )

    assert "reconcileTaskFiles(prev, task)" in app_source


def test_retried_batch_resets_old_terminal_file_rows_while_queued():
    _run_quality_node_assertion(
        """
const files = [
  { filename: "done.mp4", filepath: "uploads/done.mp4", status: "success", error: "分析完成" },
  { filename: "failed.mp4", filepath: "uploads/failed.mp4", status: "failed", error: "分析失败" },
];
const queuedRetry = {
  taskId: "batch-retry",
  kind: "batch",
  status: "queued",
  stage: "queued",
  message: "Task queued for retry",
  percent: 0,
  total: 2,
  current: 0,
  currentFile: "",
  fileProgress: [],
  retryable: false,
  cancelRequested: false,
  attemptCount: 1,
  recoveryCount: 0,
  payload: { filepaths: files.map((item) => item.filepath) },
  label: "2 个视频",
  createdAt: "2026-07-10T00:00:00Z",
};

const reset = lifecycle.reconcileTaskFiles(files, queuedRetry);
assert.deepEqual(reset.map((item) => item.status), ["processing", "processing"]);
assert.deepEqual(reset.map((item) => item.error), [
  "Task queued for retry",
  "Task queued for retry",
]);
"""
    )


def test_legacy_batch_progress_updates_only_the_unique_current_file():
    _run_quality_node_assertion(
        """
const files = [
  { filename: "test1.mp4", filepath: "uploads/test1.mp4", status: "processing", error: "正在分析视频..." },
  { filename: "test2.mp4", filepath: "uploads/test2.mp4", status: "processing", error: "正在分析视频..." },
];
const legacyTask = {
  taskId: "legacy-batch",
  kind: "batch",
  status: "analyzing",
  stage: "done",
  message: "已完成 1/2：test1.mp4 分析完成",
  percent: 50,
  total: 2,
  current: 1,
  currentFile: "test1.mp4",
  fileProgress: [],
  retryable: false,
  cancelRequested: false,
  attemptCount: 1,
  recoveryCount: 0,
  payload: { filepaths: files.map((item) => item.filepath) },
  label: "2 个视频",
  createdAt: "2026-07-10T00:00:00Z",
};

const partial = lifecycle.reconcileTaskFiles(files, legacyTask);
assert.equal(partial[0].status, "success");
assert.equal(partial[0].error, legacyTask.message);
assert.equal(partial[1].status, "processing");
assert.equal(partial[1].error, "正在分析视频...");
assert.doesNotMatch(partial[1].error, /test1/u);
"""
    )


def test_legacy_batch_progress_fails_closed_for_duplicate_basenames():
    _run_quality_node_assertion(
        """
const files = [
  { filename: "clip.mp4", filepath: "uploads/a/clip.mp4", status: "processing", error: "正在分析视频..." },
  { filename: "clip.mp4", filepath: "uploads/b/clip.mp4", status: "processing", error: "正在分析视频..." },
];
const ambiguousTask = {
  taskId: "legacy-duplicates",
  kind: "batch",
  status: "analyzing",
  stage: "done",
  message: "已完成 1/2：clip.mp4 分析完成",
  percent: 50,
  total: 2,
  current: 1,
  currentFile: "clip.mp4",
  fileProgress: [],
  retryable: false,
  cancelRequested: false,
  attemptCount: 1,
  recoveryCount: 0,
  payload: { filepaths: files.map((item) => item.filepath) },
  label: "2 个视频",
  createdAt: "2026-07-10T00:00:00Z",
};

const unchanged = lifecycle.reconcileTaskFiles(files, ambiguousTask);
assert.deepEqual(unchanged.map((item) => item.status), ["processing", "processing"]);
assert.deepEqual(unchanged.map((item) => item.error), [
  "正在分析视频...",
  "正在分析视频...",
]);
"""
    )
