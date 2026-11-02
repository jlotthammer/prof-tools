"""Deterministic synthetic residue sequences and sparse validity masks."""
from __future__ import annotations

import hashlib
import json
import random

PUBLIC_CASES = {
    "boundary": {"seed": 3, "lengths": [1, 3, 17, 257], "radii": [0, 1, 12, 400]},
    "short": {"seed": 41, "lengths": [128, 256, 512], "radii": [3, 15, 48]},
    "medium": {"seed": 73, "lengths": [512, 1024, 1536], "radii": [24, 80, 128]},
    "wide": {"seed": 91, "lengths": [512, 1024, 2048], "radii": [96, 256, 512]},
}


def build(config):
    lengths, radii = config["lengths"], config["radii"]
    if len(lengths) != len(radii) or not lengths or any(n < 1 for n in lengths) or any(r < 0 for r in radii):
        raise ValueError("each sequence needs positive length and nonnegative radius")
    random_state = random.Random(config["seed"])
    sequences = []
    for n, radius in zip(lengths, radii):
        # IDs 0..19; a realistic sparse observation mask and charged residue categories.
        ids = [random_state.randrange(20) for _ in range(n)]
        valid = [int(random_state.randrange(7) not in (0, 1)) for _ in range(n)]
        sequences.append((ids, valid, radius))
    return sequences


def identity(case, config):
    return {"suite": "ragged-masked-neighborhood-v1", "case": case,
            "seed": config["seed"], "lengths": config["lengths"], "radii": config["radii"]}


def digest_input(sequences):
    payload = json.dumps(sequences, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
