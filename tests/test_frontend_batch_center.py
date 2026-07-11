"""Source-level contracts for the batch task center wiring.

The React package intentionally has no component-test runner. Pure task behavior is
covered through Node in ``test_frontend_task_lifecycle.py``; these assertions keep
the user-facing wiring from silently disappearing.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "web-react" / "src"


def test_batch_task_center_is_full_history_with_explicit_notification_opt_in():
    component = (WEB_SRC / "components" / "BatchTaskCenter.tsx").read_text(
        encoding="utf-8"
    )
    app_source = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")

    assert "批量任务中心" in component
    assert "selectBatchTaskCenterItems" in component
    assert 'type="checkbox"' in component
    assert "completed" in component
    assert "<BatchTaskCenter" in app_source
    assert "tasks={taskQueue}" in app_source
    assert "Notification.requestPermission()" in app_source
    assert "document.visibilityState" in app_source
    assert "newlyCompletedTasks" in app_source


def test_batch_result_rows_offer_retry_only_for_retryable_failed_items():
    component = (WEB_SRC / "components" / "BatchResultPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "onRetryItem" in component
    assert "canRetry" in component
    assert 'status === "failed"' in component
    assert "重试此项" in component


def test_batch_result_retry_controls_expose_a_shared_busy_state():
    component = (WEB_SRC / "components" / "BatchResultPanel.tsx").read_text(
        encoding="utf-8"
    )
    app_source = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")

    assert "retrying?: boolean" in component
    assert "disabled={retrying}" in component
    assert "retrying={submittingTask}" in app_source


def test_batch_result_rows_use_a_light_theme_surface():
    component = (WEB_SRC / "components" / "BatchResultPanel.tsx").read_text(
        encoding="utf-8"
    )
    theme = (WEB_SRC / "theme.css").read_text(encoding="utf-8")

    assert "batch-result-row" in component
    selector = ':root[data-theme="light"] .batch-result-row {'
    assert selector in theme
    light_rule = theme.split(selector, 1)[1].split("}", 1)[0]
    assert "background:" in light_rule
    assert "255, 255, 255" in light_rule
    assert "border-top-color: var(--vi-border)" in light_rule
    assert "border-right-color: var(--vi-border)" in light_rule
    assert "border-bottom-color: var(--vi-border)" in light_rule


def test_batch_open_buttons_have_readable_light_theme_colors():
    component = (WEB_SRC / "components" / "BatchResultPanel.tsx").read_text(
        encoding="utf-8"
    )
    styles = (WEB_SRC / "index.css").read_text(encoding="utf-8")

    assert "batch-open-btn" in component
    assert "查看详情" in component
    selector = ':root[data-theme="light"] .batch-open-btn {'
    assert selector in styles
    light_rule = styles.split(selector, 1)[1].split("}", 1)[0]
    assert "color: #0e7490" in light_rule
    assert "border-color: rgba(8, 145, 178" in light_rule
    assert "background: rgba(8, 145, 178" in light_rule

    hover_selector = ':root[data-theme="light"] .batch-open-btn:hover {'
    assert hover_selector in styles


def test_batch_task_center_rehydrates_from_durable_task_list():
    app_source = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")

    assert 'fetchJson<AnalysisTaskListResponse>("/analysis_tasks")' in app_source
    assert "mergeServerTaskQueue" in app_source
    assert "tasks: taskQueue.filter(shouldPollTask)" in app_source
