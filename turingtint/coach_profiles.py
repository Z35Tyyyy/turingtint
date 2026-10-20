"""Fixed local writing-model identities; no arbitrary environment model paths."""
COMMON_FILES = ("LICENSE", "README.md", "config.json", "generation_config.json",
                "merges.txt", "tokenizer.json", "tokenizer_config.json", "vocab.json",
                "model.safetensors.index.json")
PROFILES = {
    "compact": {
        "model_id": "Qwen/Qwen3-0.6B",
        "revision": "c1899de289a04d12100db370d81485cdf75e47ca",
        "directory": ".cache/coaching-model-compact",
        "files": tuple(name for name in COMMON_FILES if name != "model.safetensors.index.json") + ("model.safetensors",),
        "quantization": "none_fp16_cuda_fp32_cpu",
        "weights_bytes": 1503300328,
        "weights_sha256": "f47f71177f32bcd101b7573ec9171e6a57f4f4d31148d38e382306f42996874b",
    },
    "small": {
        "model_id": "Qwen/Qwen3-1.7B",
        "revision": "70d244cc86ccca08cf5af4e1e306ecf908b1ad5e",
        "directory": ".cache/coaching-model",
        "files": COMMON_FILES + ("model-00001-of-00002.safetensors", "model-00002-of-00002.safetensors"),
        "quantization": "none_fp16_cuda_fp32_cpu",
    },
    "instruct": {
        "model_id": "Qwen/Qwen3-4B-Instruct-2507",
        "revision": "cdbee75f17c01a7cc42f958dc650907174af0554",
        "directory": ".cache/coaching-model-4b",
        "files": COMMON_FILES + tuple(f"model-{index:05d}-of-00003.safetensors" for index in range(1, 4)),
        "quantization": "nf4_double_fp16",
    },
}
DEFAULT_PROFILE = "instruct"
