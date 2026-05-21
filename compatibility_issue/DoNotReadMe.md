# Environment Setup and Compatibility

<br>

The original Intel Mac setup used venv with pip. After that environment broke, recovery required switching to Miniforge with conda-forge. An Apple Silicon Mac, originally a portable testing copy, served as the reference stack during the Intel Mac rebuild.

Both environments now run the same source code with matched package versions. They differ in installation path, not in pipeline behavior.

---

## 📌 Platform Comparison

| Aspect | 🖥️ Intel Mac (main) | 🍎 Apple Silicon (reference) |
|---|---|---|
| Role | Main development environment | Portable testing copy |
| Original install path | venv + pip | venv + pip |
| Final install path | Miniforge + conda-forge + pip | venv + pip |
| Python version | 3.12 | 3.14.3 |
| PyTorch source | conda-forge | pip |
| Status | Recovered after breakage | Verified working |

---

## 🖥️ Intel Mac (Main Development Environment)

This was the primary platform for thesis development. The original venv and pip stack broke during model loading. Recovery required switching to Miniforge with conda-forge.

### Broken stack (pre-recovery, venv + pip)

The broken stack contained the following package versions.

- `torch==2.2.2`
- `torchaudio==2.2.2`
- `torchvision==0.17.2`
- `transformers==4.43.0`
- `tokenizers==0.19.1`
- `huggingface_hub==0.36.2`
- `accelerate==0.33.0`
- `safetensors==0.4.3`

### Failure modes

Two independent failures appeared during model loading.

1. The fast tokenizer failed to load at `AutoTokenizer.from_pretrained(..., use_fast=True)` with the error `data did not match any variant of untagged enum ModelWrapper`.
2. The transformers library could not recognize the EXAONE 4 architecture. It reported that the checkpoint had model type `exaone4`, but the installed Transformers build did not recognize it.

### Version dilemma

The core difficulty was a contradiction between required and installable versions.

- Lower transformers was too old to read `exaone4`
- Higher transformers required higher torch
- Intel Mac pip path stopped at `torch==2.2.2` and could not install `torch==2.4.0` or `torch==2.10.0`

This locked the Intel Mac environment between two incompatible constraints. Neither side of the constraint could be satisfied within the original venv and pip path.

### Recovery procedure

Recovery required leaving the old venv and pip path. A dry-run on conda-forge confirmed that Intel Mac could install `pytorch==2.10.0`, `libtorch==2.10.0`, `torchvision==0.25.0`, and `torchaudio==2.10.0` through that channel.

The recovery steps were as follows.

1. Install Miniforge on Intel Mac
2. Create a new conda environment
3. Install the PyTorch stack from conda-forge
4. Install remaining packages with pip

### Recovered Intel Mac environment

- `python=3.12`
- `pytorch==2.10.0` (conda-forge)
- `torchvision==0.25.0` (conda-forge)
- `torchaudio==2.10.0` (conda-forge)
- `transformers==5.2.0`
- `tokenizers==0.22.2`
- `huggingface_hub==1.4.1`
- `accelerate==1.12.0`
- `safetensors==0.7.0`
- `sentencepiece`
- `selenium`
- `pyautogui`
- `pyperclip`

---

## 🍎 Apple Silicon (Reference Environment)

This was a portable copy used for mobile testing. It was not the main development environment. It became the reference point when the Intel Mac rebuild began.

### Project path

`/Users/air/Desktop/ThesisProject`

### Python

- `Python 3.14.3`
- Interpreter at `/Users/air/Desktop/ThesisProject/.venv/bin/python`

### Core ML and Hugging Face stack

- `torch==2.10.0`
- `torchaudio==2.10.0`
- `torchvision==0.25.0`
- `transformers==5.2.0`
- `tokenizers==0.22.2`
- `huggingface_hub==1.4.1`
- `accelerate==1.12.0`
- `safetensors==0.7.0`

### Additional runtime packages

- `numpy==2.4.2`
- `selenium==4.41.0`
- `sentencepiece==0.2.1`
- `PyAutoGUI==0.9.54`
- `pyperclip==1.11.0`

### Model configuration

- Classification model `monologg/koelectra-base-v3-discriminator`
- EXAONE model `LGAI-EXAONE/EXAONE-4.0-1.2B`

### EXAONE loading code

```python
self.tokenizer = AutoTokenizer.from_pretrained(cfg.model_name_or_path, use_fast=True)
self.model = AutoModelForCausalLM.from_pretrained(
    cfg.model_name_or_path,
    torch_dtype=getattr(torch, "float16", None),
)
```

### Notes

- The environment above was verified as working on Apple Silicon
- The EXAONE configuration in `backends.py` points to `LGAI-EXAONE/EXAONE-4.0-1.2B`
- The Python interpreter used was the project-local virtual environment under `.venv`

---

## 🔑 Key Lesson

The failure was not in the source code itself. The failure came from dependency compatibility across package channels and binary availability on Intel Mac. A simple reinstall inside the old venv and pip path could not recover the project. Recovery required changing the deployment path itself.
