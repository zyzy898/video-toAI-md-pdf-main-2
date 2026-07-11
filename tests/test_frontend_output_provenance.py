"""Frontend contracts for output templates and result provenance."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WEB_SRC = REPO_ROOT / "web-react" / "src"


def test_api_types_expose_template_and_evidence_contracts():
    source = (WEB_SRC / "types" / "api.ts").read_text(encoding="utf-8")

    assert 'export type OutputTemplate = "operation_guide" | "content_summary"' in source
    assert "output_template?: OutputTemplate" in source
    assert "step_id?: string" in source
    assert "time_seconds?: number" in source
    assert "evidence?: StepEvidence" in source
    assert "external_references?: ExternalReference[]" in source


def test_app_submits_selected_template_and_regenerates_from_result_template():
    source = (WEB_SRC / "App.tsx").read_text(encoding="utf-8")

    assert 'useState<OutputTemplate>("operation_guide")' in source
    assert "操作教程" in source
    assert "内容摘要" in source
    assert "output_template: outputTemplate" in source
    assert 'output_template: resultData.output_template || "operation_guide"' in source
    assert "summaryOnly={summaryOnly}" not in source


def test_step_evidence_and_external_references_are_rendered_from_result_data():
    evidence = (WEB_SRC / "components" / "StepEvidence.tsx").read_text(
        encoding="utf-8"
    )
    readonly_steps = (WEB_SRC / "components" / "ReadonlyStepsList.tsx").read_text(
        encoding="utf-8"
    )
    steps_panel = (WEB_SRC / "components" / "StepsPanel.tsx").read_text(
        encoding="utf-8"
    )

    assert "原字幕" in evidence
    assert "分析字幕" in evidence
    assert "截图依据" in evidence
    assert "外部补充" in evidence
    assert "<StepEvidence" in readonly_steps
    assert "<ExternalReferences" in steps_panel

