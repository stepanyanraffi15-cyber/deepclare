"""One real, billed proof that M15 wraps M14 correctly over HTTP.

Not a repeat of Entry 9's proof that the chain itself works — this checks the parts only
the service edge adds: base64 in and out, JSON-serializing a `RunResult` (which nests the
whole `ReviewReport`), the dev bearer token, and the submit -> poll -> result state
machine against a real job. Run once, by hand:

    .venv/bin/python tests/make_synthetic_invoice.py
    .venv/bin/python tests/check_service_edge.py
"""

from __future__ import annotations

import base64
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from deepclare.config import load_settings
from deepclare.contracts import JobStatus
from deepclare.service import create_app

INVOICE = Path("/tmp/invoice_synthetic.pdf")
CMR = Path("/tmp/cmr_synthetic.pdf")


def _encoded(path: Path, role: str) -> dict:
    return {
        "file_name": path.name,
        "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        "declared_role": role,
    }


def main() -> int:
    if not INVOICE.is_file() or not CMR.is_file():
        print("run tests/make_synthetic_invoice.py first", file=sys.stderr)
        return 2

    settings = load_settings()
    app = create_app(settings)
    headers = {"Authorization": f"Bearer {settings.service_dev_token}"}

    with TestClient(app) as client:
        unauthenticated = client.get("/runs/nonexistent")
        assert unauthenticated.status_code == 401, unauthenticated.text
        print("unauthenticated request correctly refused (401)")

        missing = client.get("/runs/nonexistent", headers=headers)
        assert missing.status_code == 404, missing.text
        print("unknown job id correctly reports 404 not_found")

        payload = {
            "files": [
                _encoded(INVOICE, "invoice"),
                _encoded(CMR, "consignment_note"),
            ]
        }
        submitted = client.post("/runs", json=payload, headers=headers)
        assert submitted.status_code == 200, submitted.text
        job_id = submitted.json()["job_id"]
        print(f"submitted: job {job_id}")

        premature = client.get(f"/runs/{job_id}/result", headers=headers)
        assert premature.status_code == 409, premature.text
        print("result requested before completion correctly reports 409")

        deadline = time.monotonic() + 300
        status = None
        seen_stages: list[str] = []
        while time.monotonic() < deadline:
            response = client.get(f"/runs/{job_id}", headers=headers)
            assert response.status_code == 200, response.text
            body = response.json()
            status = body["status"]
            stage = body["current_stage"]
            if stage and (not seen_stages or seen_stages[-1] != stage):
                seen_stages.append(stage)
                print(f"  stage: {stage}")
            if status in (JobStatus.SUCCEEDED.value, JobStatus.FAILED.value):
                break
            time.sleep(1.0)

        assert status == JobStatus.SUCCEEDED.value, f"job ended as {status}: {body}"

        result = client.get(f"/runs/{job_id}/result", headers=headers)
        assert result.status_code == 200, result.text
        run_result = result.json()

        summary = run_result["summary"]
        report = run_result["review_report"]
        xml = run_result["declaration_xml"]

        assert "<catESAD_cu:TotalGoodsNumber>" in xml
        assert summary["goods_line_count"] == 3, summary
        assert len(report["groups"]) > 0, "review report carried no groups over the wire"

        print()
        print("=" * 78)
        print("M15 END-TO-END, OVER HTTP")
        print("=" * 78)
        print(f"stages observed  {' -> '.join(seen_stages)}")
        print(f"goods lines      {summary['goods_line_count']}")
        print(f"codes assigned   {summary['codes_assigned']}")
        print(f"codes abstained  {summary['codes_abstained']}")
        print(f"conforms/filable {summary['conforms']} / {summary['filable']}")
        print(f"review groups    {len(report['groups'])}")
        print(f"XML bytes        {len(xml)}")
        print()
        print("PASSED")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
