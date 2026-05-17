"""Seeded RNG wrapper. All battle randomness flows through this class."""
import random


class BattleRNG:
    def __init__(self, seed: int):
        self.seed = seed
        self._rng = random.Random(seed)

    def uniform(self) -> float:
        """Return float in [0.0, 1.0)."""
        return self._rng.random()

    def randint(self, lo: int, hi: int) -> int:
        """Return integer in [lo, hi] inclusive."""
        return self._rng.randint(lo, hi)

    def roll_check(self, probability: float) -> bool:
        """Return True with given probability (0.0-1.0)."""
        return self._rng.random() < probability
