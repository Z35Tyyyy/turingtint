"""Pinned pretrained detectors. Downloads are explicit; prediction is offline."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .mage import ROOT, _download, sha256_file, validate_records

SPECS = json.loads(Path(__file__).with_name('pretrained-pins.json').read_text(encoding='utf-8'))


def model_directory(name):
    if name not in SPECS:
        raise ValueError('Unknown pretrained model.')
    return ROOT / '.cache' / 'detector-models' / name


def verify_files(name, directory):
    for filename, entry in SPECS[name]['files'].items():
        path = directory / filename
        if path.is_symlink() or not path.is_file() or path.stat().st_size != entry['size']:
            raise ValueError('Missing or incorrect pinned artifact: ' + filename)
        if entry['kind'] == 'sha256':
            digest = sha256_file(path)
        else:
            data = path.read_bytes()
            digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if digest != entry['hash']:
            raise ValueError('Artifact checksum mismatch: ' + filename)


def download_model(name):
    directory = model_directory(name)
    spec = SPECS[name]
    if sum(f['size'] for f in spec['files'].values()) > 2_000_000_000:
        raise ValueError('Model exceeds 2 GB acquisition budget.')
    directory.mkdir(parents=True, exist_ok=True)
    for filename, entry in spec['files'].items():
        if (directory / filename).is_symlink():
            raise ValueError('Model files cannot be symlinks.')
        _download(f"https://huggingface.co/{spec['model_id']}/resolve/{spec['revision']}/{filename}",
                  directory / filename, expected_size=entry['size'],
                  expected_sha256=entry['hash'] if entry['kind'] == 'sha256' else None,
                  expected_git_blob=entry['hash'] if entry['kind'] == 'git_blob' else None)
    verify_files(name, directory)


def desklib_class(torch, transformers):
    """Local implementation of upstream's masked mean pooling and sigmoid head."""
    class DesklibModel(transformers.PreTrainedModel):
        config_class = transformers.AutoConfig

        def __init__(self, config):
            super().__init__(config)
            self.model = transformers.AutoModel.from_config(config, trust_remote_code=False)
            self.classifier = torch.nn.Linear(config.hidden_size, 1)
            self.post_init()

        def forward(self, input_ids, attention_mask, **kwargs):
            hidden = self.model(input_ids=input_ids, attention_mask=attention_mask)[0]
            mask = attention_mask.unsqueeze(-1).expand(hidden.size()).float()
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1e-9)
            return {'logits': self.classifier(pooled)}
    return DesklibModel


class PretrainedDetector:
    def __init__(self, name, *, device='cpu'):
        self.directory = model_directory(name)
        self.name, self.spec = name, SPECS[name]
        if device not in {'cpu', 'cuda', 'auto'}:
            raise ValueError('Unsupported device.')
        verify_files(name, self.directory)
        import torch
        import transformers
        self.torch = torch
        self.device = ('cuda' if torch.cuda.is_available() else 'cpu') if device == 'auto' else device
        if self.device == 'cuda' and not torch.cuda.is_available():
            raise ValueError('CUDA is unavailable.')
        config = transformers.AutoConfig.from_pretrained(self.directory, local_files_only=True, trust_remote_code=False)
        expected_type = {'distilbert': 'distilbert', 'modernbert': 'modernbert', 'desklib': 'deberta-v2'}[name]
        if config.model_type != expected_type or getattr(config, 'auto_map', None):
            raise ValueError('Unexpected architecture.')
        self.temperature = 1.0
        if name != 'desklib':
            metadata = json.loads((self.directory / 'detector-config.json').read_text(encoding='utf-8'))
            self.temperature = float(metadata['temperature'])
            if (not math.isfinite(self.temperature) or self.temperature <= 0
                    or metadata['label_mapping'] != {'human': 0, 'ai': 1}
                    or config.num_labels != 2 or config.id2label != {0: 'HUMAN', 1: 'AI'}):
                raise ValueError('Invalid labels or calibration metadata.')
        if name == 'modernbert':
            # Transformers 5 calls this generic JSON backend TokenizersBackend.
            # Load its exact serialized tokenizer with the v4 generic fast class;
            # do not alter verified artifacts or reconstruct its tokenization.
            settings = json.loads((self.directory / 'tokenizer_config.json').read_text(encoding='utf-8'))
            self.tokenizer = transformers.PreTrainedTokenizerFast(
                tokenizer_file=str(self.directory / 'tokenizer.json'),
                **{k: settings[k] for k in ('cls_token', 'sep_token', 'pad_token', 'unk_token',
                                           'mask_token', 'model_max_length', 'model_input_names',
                                           'clean_up_tokenization_spaces')})
            for key in ('cls_token_id', 'sep_token_id', 'pad_token_id'):
                if getattr(self.tokenizer, key) != getattr(config, key):
                    raise ValueError('Tokenizer special IDs do not match the checkpoint.')
            # Newer configs serialize the same rotary bases under rope_parameters.
            rotary = getattr(config, 'rope_parameters', {})
            for attention, key in [('full_attention', 'global_rope_theta'), ('sliding_attention', 'local_rope_theta')]:
                if attention in rotary:
                    if rotary[attention]['rope_type'] != 'default':
                        raise ValueError('Unsupported rotary configuration.')
                    setattr(config, key, rotary[attention]['rope_theta'])
            config.reference_compile = False
        else:
            self.tokenizer = transformers.AutoTokenizer.from_pretrained(self.directory, local_files_only=True, trust_remote_code=False)
        cls = desklib_class(torch, transformers) if name == 'desklib' else transformers.AutoModelForSequenceClassification
        options = {'attn_implementation': 'eager'} if name == 'modernbert' else {}
        model, loading = cls.from_pretrained(self.directory, config=config, local_files_only=True,
            trust_remote_code=False, use_safetensors=True, dtype=torch.float32,
            output_loading_info=True, **options)
        if any(loading.get(k) for k in ('missing_keys', 'unexpected_keys', 'mismatched_keys', 'error_msgs')):
            raise ValueError('Checkpoint architecture mismatch.')
        self.model = model.to(self.device).eval()

    def predict(self, records, *, batch_size=1):
        validate_records(records)
        if type(batch_size) is not int or not 1 <= batch_size <= 4:
            raise ValueError('Batch size must be 1 to 4.')
        results = []
        limit = self.spec['max_tokens']
        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            texts = [r['text'] for r in batch]
            counts = [len(self.tokenizer(t, truncation=False)['input_ids']) for t in texts]
            # The published DistilBERT tokenizer identifies as BERT and otherwise
            # emits token_type_ids, which DistilBERT's forward does not accept.
            encoded = self.tokenizer(texts, padding=True, truncation=True, max_length=limit,
                                     return_token_type_ids=False, return_tensors='pt')
            actual = encoded['attention_mask'].sum(1).tolist()
            encoded = {k: v.to(self.device) for k, v in encoded.items()}
            with self.torch.inference_mode():
                output = self.model(**encoded)
                logits = output['logits'].float()
                if tuple(logits.shape) != (len(batch), 1 if self.name == 'desklib' else 2) or not self.torch.isfinite(logits).all():
                    raise ValueError('Invalid model logits.')
                scores = (self.torch.sigmoid(logits[:, 0]) if self.name == 'desklib' else
                          (logits / self.temperature).softmax(-1)[:, 1]).cpu().tolist()
            for i, record in enumerate(batch):
                results.append(dict(id=record['id'], model_id=self.spec['model_id'], model_revision=self.spec['revision'],
                    score_ai=scores[i], score_kind='sigmoid' if self.name == 'desklib' else 'upstream_temperature_softmax',
                    temperature=self.temperature, original_tokens=counts[i], input_tokens=int(actual[i]), max_tokens=limit,
                    truncated=counts[i] > actual[i], device=self.device, product_approved=False, calibrated=False))
        return results
