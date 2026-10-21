"""Bounded DistilBERT continuation pilot; never replaces a product checkpoint."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import time

from .experiment import file_sha, freeze, load_frozen, sha, write_json
from .metrics import FrozenThresholds, evaluate, select_thresholds

VALIDATION_SEED = "turingtint-distilbert-pilot-v1-validation"


def freeze_pilot(source: Path, output: Path) -> dict:
    """Keep existing test/calibration assignments; reserve train families for validation."""
    freeze(source, output)
    rows, manifest = load_frozen(output)
    for row in rows:
        draw = int(sha((VALIDATION_SEED + row["split_unit"]).encode())[:16], 16) / 2**64
        if row["split"] == "train" and draw < 1 / 6:
            row["split"] = "validation"
    for split in ("train", "validation", "calibration", "test"):
        if {r["label"] for r in rows if r["split"] == split} != {0, 1}:
            raise ValueError(f"Both classes are required in {split}; use more source families.")
    records = output / "records.jsonl"
    records.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")
    manifest.update(
        records_sha256=file_sha(records), validation_seed=VALIDATION_SEED,
        split_policy="Existing 60/20/20 families; independently reserve 1/6 of train for validation (about 50/10/20/20).",
        validation_purpose="checkpoint selection only; calibration and test excluded from optimization",
        pilot_code_sha256=file_sha(Path(__file__)),
    )
    manifest["stats"]["counts"] = dict(Counter(f"{r['split']}:{r['label']}" for r in rows))
    write_json(output / "manifest.json", manifest)
    load_frozen(output)  # Check all family, prompt, document and excerpt boundaries again.
    return manifest


def fit_temperature(logits, labels) -> float:
    """Fit one positive scalar by calibration NLL, with a bounded deterministic grid."""
    import numpy as np
    logits, labels = np.asarray(logits, dtype=float), np.asarray(labels, dtype=int)
    if logits.shape != (len(labels), 2) or not len(labels) or not np.isfinite(logits).all():
        raise ValueError("Expected finite binary calibration logits.")
    if set(labels.tolist()) != {0, 1}:
        raise ValueError("Temperature calibration needs both classes.")
    best = (float("inf"), 1.0)
    for temperature in sorted({1.0, *np.geomspace(.25, 8.0, 81).tolist()}):
        scaled = logits / temperature
        shifted = scaled - scaled.max(axis=1, keepdims=True)
        loss = float((np.log(np.exp(shifted).sum(axis=1)) - shifted[np.arange(len(labels)), labels]).mean())
        best = min(best, (loss, temperature))
    return float(best[1])


def score_rows(rows, logits, temperature):
    import numpy as np
    logits = np.asarray(logits, dtype=float)
    if logits.shape != (len(rows), 2) or not np.isfinite(logits).all() or not math.isfinite(temperature) or temperature <= 0:
        raise ValueError("Invalid prediction shape, logits or temperature.")
    scaled = logits / temperature
    shifted = scaled - scaled.max(axis=1, keepdims=True)
    probabilities = np.exp(shifted)
    probabilities /= probabilities.sum(axis=1, keepdims=True)
    # Use the entire connected component as the source family in metrics.
    return [{**r, "source_group": r["split_unit"], "score": float(p)} for r, p in zip(rows, probabilities[:, 1])]


def compare_scores(calibration, test, calibration_logits, test_logits, *, temperature=None):
    if temperature is None:
        temperature = fit_temperature(calibration_logits, [r["label"] for r in calibration])
    calibration_scores = score_rows(calibration, calibration_logits, temperature)
    test_scores = score_rows(test, test_logits, temperature)
    thresholds = select_thresholds(calibration_scores)
    calibrated = evaluate(test_scores, thresholds, require_prompt_disjoint=True)
    binary = evaluate(test_scores, FrozenThresholds(human_max=math.nextafter(.5, 0), ai_min=.5))["metrics"]
    counts = binary["confusion"]
    denominator = 2 * counts["tp"] + counts["fp"] + counts["fn"]
    binary.update(accuracy=(counts["tp"] + counts["tn"]) / len(test),
                  ai_f1=2 * counts["tp"] / denominator if denominator else 0.0)
    return {"temperature": temperature, "binary_at_0_5": binary,
            "calibrated_thresholds": calibrated}, calibration_scores + test_scores


def train(frozen: Path, output: Path, *, epochs=2, max_seconds=900, device="cuda") -> dict:
    if output.exists() and any(output.iterdir()):
        raise ValueError("Use a new output directory; previous runs are immutable.")
    if not 1 <= epochs <= 3 or not 60 <= max_seconds <= 3600:
        raise ValueError("Pilot limits: 1-3 epochs and 60-3600 seconds.")
    import importlib.metadata
    import numpy as np
    import torch
    from transformers import (AutoModelForSequenceClassification, DataCollatorWithPadding,
                              Trainer, TrainerCallback, TrainingArguments, set_seed)
    from detector_models.pretrained import PretrainedDetector, SPECS

    if device == "cuda" and not torch.cuda.is_available():
        raise ValueError("A GPU was requested but CUDA is unavailable; enable a notebook GPU.")
    if device not in {"cpu", "cuda"}:
        raise ValueError("Unsupported training device.")
    torch.set_num_threads(2)
    set_seed(42)
    rows, manifest = load_frozen(frozen)
    if manifest.get("validation_seed") != VALIDATION_SEED:
        raise ValueError("Freeze the pilot with a separate validation split first.")
    subsets = {s: [r for r in rows if r["split"] == s] for s in ("train", "validation", "calibration", "test")}
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "data-manifest.json", manifest)
    detector = PretrainedDetector("distilbert", device=device)
    tokenizer, model = detector.tokenizer, detector.model
    published_temperature = detector.temperature
    del detector

    datasets, token_owners, truncation = {}, {}, Counter()
    for split, subset in subsets.items():
        encoded = tokenizer([r["text"] for r in subset], truncation=False, return_token_type_ids=False)
        for ids in encoded["input_ids"]:
            truncation[split] += len(ids) > 512
        encoded = tokenizer([r["text"] for r in subset], truncation=True, max_length=512, return_token_type_ids=False)
        datasets[split] = []
        for index, row in enumerate(subset):
            marker = tuple(encoded["input_ids"][index])
            if marker in token_owners and token_owners[marker] != split:
                raise ValueError("Identical truncated token sequences cross split boundaries.")
            token_owners[marker] = split
            datasets[split].append({**{key: value[index] for key, value in encoded.items()}, "labels": row["label"]})

    started = time.monotonic()

    class Deadline(TrainerCallback):
        def on_step_begin(self, args, state, control, **kwargs):
            if time.monotonic() - started > max_seconds:
                raise TimeoutError("Pilot training time budget exceeded; no complete result claimed.")

    use_bf16 = device == "cuda" and torch.cuda.is_bf16_supported()
    args = TrainingArguments(
        output_dir=str(output / "checkpoints"), num_train_epochs=epochs,
        per_device_train_batch_size=8, gradient_accumulation_steps=4,
        per_device_eval_batch_size=16, learning_rate=2e-5, weight_decay=.01,
        warmup_ratio=.06, max_grad_norm=1.0, optim="adamw_torch",
        eval_strategy="epoch", save_strategy="epoch", save_total_limit=1, save_only_model=True,
        load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
        bf16=use_bf16, fp16=device == "cuda" and not use_bf16,
        use_cpu=device == "cpu", dataloader_num_workers=0,
        report_to="none", logging_steps=10, seed=42, data_seed=42,
    )
    trainer = Trainer(model=model, args=args, train_dataset=datasets["train"],
                      eval_dataset=datasets["validation"], processing_class=tokenizer,
                      data_collator=DataCollatorWithPadding(tokenizer, pad_to_multiple_of=8),
                      callbacks=[Deadline()])
    # Save predictions internally; compare only after checkpoint selection is complete.
    original_logits = {s: trainer.predict(datasets[s]).predictions for s in ("calibration", "test")}
    result = trainer.train()
    checkpoint = output / "model"
    trainer.save_model(str(checkpoint))
    tokenizer.save_pretrained(checkpoint)
    trainer.save_state()
    tuned_logits = {s: trainer.predict(datasets[s]).predictions for s in ("calibration", "test")}
    comparisons, predictions = {}, []
    for name, logits, temperature in (
        ("original", original_logits, published_temperature),
        ("original_recalibrated", original_logits, None),
        ("finetuned", tuned_logits, None),
    ):
        comparisons[name], scored = compare_scores(subsets["calibration"], subsets["test"],
                                                   logits["calibration"], logits["test"], temperature=temperature)
        predictions.extend({"variant": name, **{k: r[k] for k in ("id", "split", "label", "source_group", "text_sha256", "score")}} for r in scored)
    # Reload the exported artifact before calling the run complete.
    exported = AutoModelForSequenceClassification.from_pretrained(checkpoint, local_files_only=True, use_safetensors=True).to(device).eval()
    sample = tokenizer(subsets["test"][0]["text"], truncation=True, max_length=512,
                       return_token_type_ids=False, return_tensors="pt")
    with torch.inference_mode():
        saved_logits = exported(**{k: v.to(device) for k, v in sample.items()}).logits.float().cpu().numpy()[0]
    # Trainer may use mixed precision; tolerate those numerical differences.
    export_difference = float(np.max(np.abs(saved_logits - tuned_logits["test"][0])))
    if export_difference > .15:
        raise ValueError("Exported checkpoint predictions differ unexpectedly.")
    temperature = comparisons["finetuned"]["temperature"]
    write_json(checkpoint / "detector-config.json", {"label_mapping": {"human": 0, "ai": 1}, "temperature": temperature,
               "calibration_dataset_sha256": manifest["records_sha256"], "experimental": True})
    (output / "predictions.jsonl").write_text("".join(json.dumps(p) + "\n" for p in predictions), encoding="utf-8")
    report = {"status": "completed", "scope": "HC3 wiki_csai continuation pilot; not independent modern-generator validation",
              "base_model": SPECS["distilbert"]["model_id"], "base_revision": SPECS["distilbert"]["revision"],
              "parameters": {"epochs": epochs, "learning_rate": 2e-5, "batch_size": 8, "gradient_accumulation": 4,
                             "max_tokens": 512, "warmup_ratio": .06, "weight_decay": .01, "seed": 42,
                             "precision": "bf16" if use_bf16 else "fp16" if device == "cuda" else "fp32"},
              "training": result.metrics, "best_validation_loss": trainer.state.best_metric,
              "elapsed_seconds": time.monotonic() - started, "truncated_rows": dict(truncation),
              "device": torch.cuda.get_device_name(0) if device == "cuda" else "cpu",
              "packages": {p: importlib.metadata.version(p) for p in ("torch", "transformers", "accelerate", "huggingface-hub")},
              "data_manifest_sha256": file_sha(output / "data-manifest.json"),
              "model_sha256": file_sha(checkpoint / "model.safetensors"),
              "predictions_sha256": file_sha(output / "predictions.jsonl"),
              "code_sha256": file_sha(Path(__file__)), "export_reload_max_logit_difference": export_difference,
              "comparisons": comparisons, "product_model_changed": False,
              "limitations": manifest["source_limitations"]}
    write_json(output / "report.json", report)
    (checkpoint / "README.md").write_text(
        "# TuringTint DistilBERT HC3 pilot\n\nExperimental continuation of rasbt/ai-text-detector-distilbert.\n\n"
        "Training source: " + manifest["attribution"] + "\n\n"
        "Dataset: https://huggingface.co/datasets/Hello-SimpleAI/HC3 (wiki_csai only, CC-BY-SA-4.0).\n"
        "Source model license: Apache-2.0; see LICENSE. Preserve dataset attribution and applicable share-alike terms.\n\n"
        "Labels: 0=HUMAN, 1=AI. Use detector-config.json temperature before softmax.\n"
        "See ../report.json for comparison, false positives and limitations.\n"
        "No verified authorship, sentence-level, or modern-generator accuracy claim.\n", encoding="utf-8")
    from detector_models.pretrained import model_directory
    (checkpoint / "LICENSE").write_bytes((model_directory("distilbert") / "LICENSE").read_bytes())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("freeze")
    prep.add_argument("--source", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    run = sub.add_parser("train")
    run.add_argument("--frozen", type=Path, required=True)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--epochs", type=int, default=2)
    run.add_argument("--max-seconds", type=int, default=900)
    run.add_argument("--device", choices=("cpu", "cuda"), default="cuda")
    args = parser.parse_args()
    if args.command == "freeze":
        print(json.dumps(freeze_pilot(args.source, args.output)["stats"]))
    else:
        report = train(args.frozen, args.output, epochs=args.epochs, max_seconds=args.max_seconds, device=args.device)
        print(json.dumps({k: v["binary_at_0_5"] for k, v in report["comparisons"].items()}, indent=2))


if __name__ == "__main__":
    main()
