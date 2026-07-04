"""Regression tests for frontend batch-upload de-duplication."""

import json
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DEDUPE_MODULE = (REPO_ROOT / "web-react" / "src" / "lib" / "upload-dedupe.ts").as_uri()


def _run_node_assertion(script_body: str) -> None:
    script = f"""
import assert from "node:assert/strict";
import {{
  buildUploadSourceKey,
  dedupeBatchUploadFiles,
}} from {json.dumps(UPLOAD_DEDUPE_MODULE)};

const makeFile = (name, size, lastModified) => ({{ name, size, lastModified }});

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


def test_dedupe_batch_upload_files_keeps_first_copy_selected_together():
    _run_node_assertion(
        """
const first = makeFile("demo.mp4", 1024, 123456);
const duplicate = makeFile("demo.mp4", 1024, 123456);
const other = makeFile("other.mp4", 1024, 123456);

const result = dedupeBatchUploadFiles([first, duplicate, other]);

assert.deepEqual(result.files, [first, other]);
assert.equal(result.duplicateCount, 1);
assert.deepEqual(result.duplicateNames, ["demo.mp4"]);
"""
    )


def test_dedupe_batch_upload_files_skips_existing_upload_source():
    _run_node_assertion(
        """
const existing = makeFile("demo.mp4", 1024, 123456);
const incoming = makeFile("demo.mp4", 1024, 123456);

const result = dedupeBatchUploadFiles([incoming], new Set([buildUploadSourceKey(existing)]));

assert.deepEqual(result.files, []);
assert.equal(result.duplicateCount, 1);
assert.deepEqual(result.duplicateNames, ["demo.mp4"]);
"""
    )
