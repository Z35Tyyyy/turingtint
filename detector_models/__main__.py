"""CLI acquisition and explicitly selected, offline research predictions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mage import DEFAULT_MODEL_DIR, MageDetector, convert_to_safetensors, download_model, validate_records


def read_records(path: Path, ids_path: Path | None = None, limit: int | None = None) -> list[dict]:
    if limit is not None and limit < 1:
        raise ValueError("limit must be a positive integer.")
    selected = None
    if ids_path is not None:
        content = ids_path.read_text(encoding="utf-8")
        selected = set(json.loads(content)) if content.lstrip().startswith("[") else set(content.splitlines())
        if not selected or not all(isinstance(value, str) and value for value in selected):
            raise ValueError("IDs must be a nonempty JSON string array or one nonempty id per line.")
    records = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            record = json.loads(line)
            if selected is None or record.get("id") in selected:
                records.append(record)
                if limit is not None and len(records) >= limit:
                    break
    validate_records(records)
    if not records:
        raise ValueError("No input records were selected.")
    if selected is not None and limit is None and selected != {record["id"] for record in records}:
        raise ValueError("Some requested IDs were not present in the input records.")
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description="Pinned MAGE research baseline; no validated product scores.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("download", help="Download <2 GB of pinned official artifacts, then safely convert weights.")
    commands.add_parser("convert", help="Convert already downloaded verified weights to safetensors.")
    predict = commands.add_parser("predict", help="Predict locally on explicitly selected JSONL records.")
    predict.add_argument("--input", type=Path, required=True)
    predict.add_argument("--output", type=Path, required=True)
    predict.add_argument("--ids", type=Path)
    predict.add_argument("--limit", type=int)
    predict.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    predict.add_argument("--max-tokens", type=int, default=1024)
    predict.add_argument("--batch-size", type=int, default=1)
    options = parser.parse_args()
    if options.command in {"download", "convert"}:
        if options.command == "download":
            download_model(options.model_dir)
        manifest = convert_to_safetensors(options.model_dir)
        print(json.dumps({"event": "model_ready", "model_revision": manifest["model_revision"],
                          "download_bytes": manifest["download_bytes"], "manifest": str(options.model_dir / "manifest.json")}))
        return
    if options.input.resolve() == options.output.resolve():
        parser.error("Prediction output must not overwrite source records.")
    if not 1 <= options.batch_size <= 4:
        parser.error("batch-size must be between 1 and 4.")
    if options.output.exists():
        parser.error("Prediction output already exists; use a new run path.")
    pending = options.output.with_name(options.output.name + ".partial")
    if pending.exists():
        parser.error("A partial prediction file already exists; use a new run path to preserve its evidence.")
    records = read_records(options.input, options.ids, options.limit)
    detector = MageDetector(options.model_dir, device=options.device, max_tokens=options.max_tokens)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    truncated_count = 0
    completed = 0
    with pending.open("x", encoding="utf-8") as stream:
        for start in range(0, len(records), options.batch_size):
            predictions = detector.predict(records[start:start + options.batch_size], batch_size=options.batch_size)
            for record in predictions:
                stream.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
                truncated_count += int(record["truncated"])
            stream.flush()
            completed += len(predictions)
            if completed % 20 < options.batch_size or completed == len(records):
                print(json.dumps({"event": "prediction_progress", "completed": completed, "total": len(records)}), flush=True)
    pending.replace(options.output)
    print(json.dumps({"event": "prediction_complete", "records": completed, "output": str(options.output),
                      "truncated_records": truncated_count, "product_approved": False}))


if __name__ == "__main__":
    main()
