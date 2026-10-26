# Listening Test (M1 acceptance)

The audio assembly rules (spec §9.1) are judged by ear on the three example Scripts. This test
checks **assembly** (pacing, pauses, joins, levels, start and end), **not voice quality**. Piper
German voices are accepted for M1 even though they sound synthetic; a higher-quality engine
(Qwen3-TTS) arrives in M7.

## How to run

```
export ANCHOR_TTS__API_KEY=…            # see docs/render-pipeline.md §2
docker compose up -d speaches
for n in day sleep short; do uv run anchor render examples/scripts/$n.json -o out/$n.mp3; done
```

Listen on headphones at a comfortable, fixed volume, start to end, without skipping. Record each
item as pass, fail or note.

## Checklist

| # | Item | What to listen for |
| --- | --- | --- |
| 1 | No clipped word endings | Final consonants and soft endings ("-en", "-s", breathy "h") are complete; no word sounds cut off |
| 2 | No dropouts / digital silence | The background never drops to dead silence; no gaps, clicks or pops at joins |
| 3 | Even pause lengths | Gaps between sentences sound uniform, and pauses match their intent; no gap is randomly short or long |
| 4 | No level jumps | No sentence is suddenly louder or quieter than its neighbours; cached and freshly synthesized sentences sound alike |
| 5 | Calm pacing per type | `sleep` is slowest with the longest gaps, `day` is relaxed, `short` is tighter but not rushed |
| 6 | Sleep ends without sound | `sleep` ends with speech, then silence over the background, then a long (30 s) fade; no bell, no Emergence |
| 7 | Bell clean | `bell_soft` has no click at onset, decays smoothly, does not clip, and sits below speech level |
| 8 | Background | The Noise Floor is barely noticeable, does not swell in pauses, and the `brown_noise` switch in `sleep` is smooth |
| 9 | Peaks | No audible squashing or distortion on loud syllables (peak limiter, design D5) |

## Results — 2026-10-26

**Listener:** the project owner. **Renders:** `out/day.mp3`, `out/sleep.mp3`, `out/short.mp3`
(Speaches 0.8.3, `speaches-ai/piper-de_DE-thorsten-medium`, voice `thorsten`, default pacing).

**Verdict:** assembly accepted ("fine"). **Remark:** the voice sounds generic and "technical".
That is a voice-quality issue, outside this test's scope: it is an accepted M1 risk (design,
Risks) and is addressed by the M7 engine.

The listening was done on the first renders, *before* the true-peak limiter was added (design
D5). Those renders ran through loudnorm's dynamic fallback, which lifted the Noise Floor in long
pauses (item 8: −49.9 LUFS instead of about −60). The current renders fix that, but the change
was verified only by measurement (below), not by ear. Items 8 and 9 should be re-checked on the
current renders at the next listen.

### Measured on the current renders (automated proxies)

| Check | `day` | `sleep` | `short` |
| --- | --- | --- | --- |
| Duration / target | 577.3 / 600 s | 900.0 / 900 s | 180.0 / 180 s |
| Integrated loudness, true peak | −18.4 LUFS, −1.8 dBTP | −18.4 LUFS, −1.8 dBTP | −18.4 LUFS, −1.7 dBTP |
| loudnorm mode | linear | linear | linear |
| Peak limiting (max gain reduction) | 2.4 dB | 3.6 dB | 3.4 dB |
| Longest run of zero samples (between fades) | 0 ms | 0 ms | 0.02 ms |
| Loudest 400 ms block inside the final fade | −59.8 LUFS (bed only) | −58.6 LUFS (bed only) | −59.4 LUFS (bed only) |
| Noise Floor in a long pause | – | −59.5 LUFS (840–880 s) | – |
| 3 s loudness of speech passages, p5…p95 | −24.2…−17.2 LUFS | −20.7…−17.3 LUFS | −27.5…−16.7 LUFS |

The 3 s windows include sentence gaps, so their spread reflects pacing, not level jumps. Each
sentence is normalized to −18 LUFS individually (unit-tested to within 2 LU). Gap lengths are
exact by construction: every sentence is trimmed to a 30 ms margin, and gaps come from the
pacing profile (unit-tested with 50 ms vs. 400 ms of engine padding).

### Tuned values

None. Pacing, bed level (−42 LU) and the voice keep their defaults. Two observations for later
tuning:

- **`day` is under-sized.** All of its Elastic Pauses fit at their maximum and it still lands
  3.8 % short (577 s for 600 s). That is within tolerance, but the Script could use more content
  or wider ranges.
- **Voice choice** (design, Open Questions): `thorsten-medium` stays the default. Other German
  Piper models to try (`thorsten-high`, `thorsten_emotional-medium`, `kerstin-low`,
  `ramona-low`) are listed in docs/render-pipeline.md §2.2. Changing `tts.model` or `tts.voice`
  is a config value only, and it creates new cache entries.
