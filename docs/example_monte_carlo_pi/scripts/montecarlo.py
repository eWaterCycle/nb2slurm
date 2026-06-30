"""Monte Carlo estimation of pi (stdlib only).

Kept in scripts/ so the notebooks stay clean and import it (Change 7 in the
nb2slurm setup guide).
"""
import random


def estimate_pi(n_samples: int, seed: int):
    """Throw n_samples random darts at the unit square; the fraction landing
    inside the quarter circle approximates pi/4. Returns (pi, inside, points)."""
    rng = random.Random(seed)
    inside = 0
    points = []
    for _ in range(n_samples):
        x, y = rng.random(), rng.random()
        is_in = (x * x + y * y) <= 1.0
        inside += is_in
        points.append((x, y, is_in))
    pi = 4 * inside / n_samples
    return pi, inside, points
