#!/usr/bin/env python3
"""
校验 Agent 输出 Envelope 是否合法
stdin JSON:
  {
    "envelope": { ...agent 返回的原始 JSON },
    "expected_task_id": "wt_...",
    "expected_step_name": "normalize"
  }
stdout JSON:
  {"success": true, "data": {"valid": true, "errors": []}}
  {"success": true, "data": {"valid": false, "errors": ["..."]}}
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from lib.common import read_stdin, ok, fail

VALID_STATUSES = {"success", "retryable_error", "fatal_error"}

def main():
    inp = read_stdin()
    envelope = inp.get("envelope")
    expected_task_id   = inp.get("expected_task_id", "")
    expected_step_name = inp.get("expected_step_name", "")

    if envelope is None:
        fail("invalid_param", "envelope is required")

    errors = []

    # 必要字段检查
    if not isinstance(envelope, dict):
        ok({"valid": False, "errors": ["envelope must be a JSON object"]})

    if not envelope.get("task_id"):
        errors.append("task_id is missing")
    elif expected_task_id and envelope["task_id"] != expected_task_id:
        errors.append(f"task_id mismatch: expected '{expected_task_id}', got '{envelope['task_id']}'")

    if not envelope.get("step_name"):
        errors.append("step_name is missing")
    elif expected_step_name and envelope["step_name"] != expected_step_name:
        errors.append(f"step_name mismatch: expected '{expected_step_name}', got '{envelope['step_name']}'")

    status = envelope.get("status")
    if not status:
        errors.append("status is missing")
    elif status not in VALID_STATUSES:
        errors.append(f"status '{status}' is not valid, must be one of {VALID_STATUSES}")

    if "artifacts" not in envelope:
        errors.append("artifacts field is missing")
    elif envelope["artifacts"] is None:
        errors.append("artifacts must not be null")

    if not isinstance(envelope.get("warnings", []), list):
        errors.append("warnings must be an array")

    if not isinstance(envelope.get("errors", []), list):
        errors.append("errors must be an array")

    # 若 status=fatal_error，errors 不能为空
    if status == "fatal_error" and not envelope.get("errors"):
        errors.append("errors array must not be empty when status is fatal_error")

    ok({"valid": len(errors) == 0, "errors": errors})

if __name__ == "__main__":
    main()
