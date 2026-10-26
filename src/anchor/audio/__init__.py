"""Audio building blocks: decoding, sentence splitting, trimming, loudness, beds, pacing.

Everything is mixed as mono float32 at one internal sample rate (design D2).
"""

SAMPLE_RATE = 48_000
