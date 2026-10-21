"""Create a credential-free Kaggle notebook pinned to a reviewed repository commit."""
import argparse
import json
from pathlib import Path
import re


def build(revision, frozen_records_sha256):
    if not re.fullmatch(r"[a-f0-9]{40}", revision) or not re.fullmatch(r"[a-f0-9]{64}", frozen_records_sha256):
        raise ValueError("Supply a full repository commit and frozen-record SHA-256.")
    source = '''import json, os, shutil, subprocess, sys
from pathlib import Path

# Use one GPU and keep scratch files outside the saved notebook outputs.
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["USE_TF"] = "0"
os.environ["USE_FLAX"] = "0"
os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
os.environ["TOKENIZERS_PARALLELISM"] = "false"
root = Path("/tmp/turingtint-distilbert-pilot")
root.mkdir(exist_ok=False)
def run(command, timeout=120):
    subprocess.run(command, cwd=root, check=True, timeout=timeout)
run([sys.executable, "-c", "import torch; assert torch.cuda.is_available(), 'No CUDA GPU in this session; check Kaggle accelerator/runtime settings'; print(torch.cuda.get_device_name(0)); print(torch.ones(1, device='cuda').item())"])
run(["git", "init", "-q"])
run(["git", "remote", "add", "origin", "https://github.com/Z35Tyyyy/turingtint.git"])
run(["git", "fetch", "--depth", "1", "origin", REVISION])
run(["git", "checkout", "--detach", "FETCH_HEAD"])
assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip() == REVISION
run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--retries", "1", "--timeout", "20", "-r", "requirements-training.txt"], 240)
run([sys.executable, "-m", "authorship_data.hc3", "--output", "data/hc3"], 180)
run([sys.executable, "-m", "detector_eval.finetune", "freeze", "--source", "data/hc3", "--output", "data/frozen"])
manifest = json.loads((root / "data/frozen/manifest.json").read_text())
assert manifest["records_sha256"] == FROZEN_SHA256, "Source/split drift; inspect before training."
run([sys.executable, "-c", "from detector_models.pretrained import download_model; download_model('distilbert')"], 240)
run([sys.executable, "-m", "detector_eval.finetune", "train", "--frozen", "data/frozen", "--output", "outputs/pilot", "--epochs", "2", "--max-seconds", "900"], 1200)
destination = Path("/kaggle/working/distilbert-hc3-pilot")
destination.mkdir(exist_ok=False)
for name in ("report.json", "data-manifest.json", "predictions.jsonl"):
    shutil.copy2(root / "outputs/pilot" / name, destination / name)
shutil.copytree(root / "outputs/pilot/model", destination / "model")
shutil.copytree(root / "data/hc3", destination / "source")
shutil.copytree(root / "data/frozen", destination / "frozen")
(destination / "repository-commit.txt").write_text(REVISION + "\\n")
report = json.loads((destination / "report.json").read_text())
print(json.dumps({name: entry["binary_at_0_5"] for name, entry in report["comparisons"].items()}, indent=2))
print("Saved checkpoint and comparison to", destination)
'''.replace("REVISION", repr(revision)).replace("FROZEN_SHA256", repr(frozen_records_sha256))
    return {"cells": [
        {"cell_type": "markdown", "metadata": {}, "source":
         "# TuringTint DistilBERT HC3 pilot\n\nPrivate, bounded experiment using Kaggle's free GPU quota. "
         "Enable a T4 GPU and Internet. No Hugging Face token is needed for public downloads. "
         "The notebook runs two epochs, selects by validation loss, calibrates on a separate split, "
         "and compares the original and tuned models on identical held-out questions. "
         "Outputs are experimental; the local app is not changed.\n\n"
         "Data: Guo et al., HC3 wiki_csai (Wikipedia human answers), CC-BY-SA-4.0. "
         "Older ChatGPT outputs; unknown pretrained-model overlap. This is not a modern-generator benchmark."},
        {"cell_type": "code", "metadata": {}, "source": source, "outputs": [], "execution_count": None},
    ], "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
        "nbformat": 4, "nbformat_minor": 4}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--frozen-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.frozen_manifest.read_text(encoding="utf-8"))
    notebook = build(args.revision, manifest["records_sha256"])
    compile(notebook["cells"][1]["source"], "training-notebook", "exec")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")
    print(args.output)
