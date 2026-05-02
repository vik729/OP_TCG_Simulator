"""Tests for engine/rng.py - splittable seed RNG helper."""
import random
from engine.rng import split_rng


class TestSplitRng:
    def test_returns_random_and_int(self):
        rng, next_state = split_rng(42)
        assert isinstance(rng, random.Random)
        assert isinstance(next_state, int)

    def test_deterministic_for_same_seed(self):
        rng_a, next_a = split_rng(42)
        rng_b, next_b = split_rng(42)
        assert next_a == next_b
        assert rng_a.random() == rng_b.random()

    def test_consecutive_calls_produce_different_states(self):
        _, state_1 = split_rng(42)
        _, state_2 = split_rng(state_1)
        _, state_3 = split_rng(state_2)
        assert len({42, state_1, state_2, state_3}) == 4

    def test_different_seeds_produce_different_results(self):
        rng_a, _ = split_rng(42)
        rng_b, _ = split_rng(43)
        assert rng_a.random() != rng_b.random()

    def test_next_state_is_within_int64_range(self):
        for seed in (0, 1, 1234567890, 2**32, 2**62):
            _, next_state = split_rng(seed)
            assert 0 <= next_state < 2**63
