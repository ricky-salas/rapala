from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import scheduler_engine as se


def main(argv):
    if len(argv)!=3:
        print("usage: solver_runner.py INPUT_JSON OUTPUT_JSON",file=sys.stderr)
        return 2
    input_path=Path(argv[1])
    output_path=Path(argv[2])
    try:
        payload=json.loads(input_path.read_text(encoding="utf-8"))
        expected=str(payload.get("expected_engine_api") or "")
        if expected and expected!=str(se.ENGINE_API_VERSION):
            raise RuntimeError(f"engine API mismatch: expected {expected}, loaded {se.ENGINE_API_VERSION}")
        se.set_runtime_rules(payload.get("rules") or {})
        people=se.people_from_request_snapshot(payload.get("people_snapshot") or {})
        if not people:
            raise RuntimeError("empty/invalid frozen people snapshot")
        result=se.solve_schedule(
            int(payload["year"]),
            int(payload["month"]),
            people,
            time_limit=float(payload.get("time_limit") or 90.0),
        )
        out={"engine_api":str(se.ENGINE_API_VERSION),"result":se.serialize_result(result)}
        output_path.write_text(json.dumps(out,ensure_ascii=False),encoding="utf-8")
        return 0
    except Exception as exc:
        print(f"solver worker failed: {exc}",file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 3


if __name__=="__main__":
    raise SystemExit(main(sys.argv))
