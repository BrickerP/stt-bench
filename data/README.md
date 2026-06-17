# STT Bench Dataset

Benchmark corpus for local speech-to-text evaluation.

## Contents

| Split | Path | Count | Condition |
|-------|------|-------|-----------|
| LibriSpeech test-clean subset | `librispeech/` | 30 | clean |
| Synthetic noisy overlay | `noisy/` | 1 | noisy |

All samples are registered in [`manifest.json`](./manifest.json).

## License

LibriSpeech is distributed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).  
Source: [OpenSLR 12](https://www.openslr.org/12/).

The noisy clip is a derivative work (same license applies to the underlying speech).

## Ground Truth Mapping

Each LibriSpeech utterance has a matching line in the chapter `.trans.txt` file from the official archive:

```
<utterance-id> <transcript text>
```

Example: `1089-134686-0000` → `"he hoped there would be stew for dinner turnips and carrots and bruised potatoes and fat mutton pieces to be ladled out in thick peppered flour fattened sauce"`

The manifest stores the normalized reference text per sample. Audio files are 16 kHz FLAC mono.

## Reproducing the Subset

### 1. Download LibriSpeech test-clean

```bash
curl -L -o /tmp/test-clean.tar.gz https://openslr.trmal.net/resources/12/test-clean.tar.gz
```

Archive size: ~346 MB compressed.

### 2. Extract selected utterances

The subset uses 30 utterances from four speakers in test-clean:

- `1089/134686` — 8 clips (0000–0007)
- `1188/133604` — 8 clips (0000–0007)
- `121/123852` — 5 clips (0000–0004)
- `1221/135766` — 9 clips (0000–0008)

Extract with tar using paths like:

```bash
tar -xzf /tmp/test-clean.tar.gz \
  LibriSpeech/test-clean/1089/134686/1089-134686-0000.flac \
  LibriSpeech/test-clean/1089/134686/1089-134686.trans.txt
# ... repeat for all target IDs
```

Or run the preparation script from repo root (after implementation lands in `scripts/prepare_dataset.py`).

### 3. Create the synthetic noisy clip

Source: `librispeech/1089-134686-0000.flac`  
Output: `noisy/1089-134686-0000_noisy.flac`

Pink noise mixed at approximately 10 dB SNR:

```bash
ffmpeg -y -i librispeech/1089-134686-0000.flac \
  -f lavfi -i "anoisesrc=color=pink:duration=30:sample_rate=16000:amplitude=0.03" \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0" \
  -ar 16000 -ac 1 noisy/1089-134686-0000_noisy.flac
```

Parameters:
- **Noise type:** pink (`anoisesrc`)
- **Amplitude:** 0.03 (tuned for ~10 dB SNR against speech RMS)
- **Method:** equal-weight mix via `amix`, duration matched to speech

The noisy clip retains the same ground-truth reference text as the source utterance.

### 4. Regenerate manifest

After extraction, build `manifest.json` with entries:

```json
{
  "id": "<utterance-id>",
  "audio_path": "librispeech/<utterance-id>.flac",
  "reference_text": "<transcript from .trans.txt>",
  "condition": "clean",
  "source": "librispeech"
}
```

Validate with:

```bash
stt-bench dataset validate   # after CLI is implemented
python -m json.tool data/manifest.json
```

## Storage Notes

The committed subset (~30 FLAC files + 1 noisy) totals under 5 MB and is safe to commit without Git LFS. The full test-clean archive should **not** be committed — add `*.tar.gz` to gitignore (already configured).
