# Examples

## 1. Offline mock regression (CI-safe)

```bash
stt-bench benchmark run --provider mock --force
stt-bench report --format markdown --out reports/examples/mock-report.md
```

## 2. Dictation noisy-clip compare (needs keys)

```bash
stt-bench listen 1089-134686-0000_noisy
# or
stt-bench compare 1089-134686-0000_noisy
```

## 3. Voice-agent STT selection workflow

1. Run mock corpus to validate your harness.
2. Run the same sample set on candidate providers.
3. Export a markdown report into the PR that proposes a provider change.

```bash
stt-bench benchmark run --providers mock --force
stt-bench report --format markdown
```
