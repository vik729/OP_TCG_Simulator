# TODO: Performance Profiling and Memo Cache

> **Status**: Deferred. Premature without measurement. Build when RL training
> shows the engine is the bottleneck.

## Goal

Make `step()` fast enough for RL training (millions of step calls per training run).

## Target

- `step()` p50 < 100µs
- `step()` p99 < 500µs
- A 50-turn game replays in < 50ms

## Why deferred

We don't yet know what's actually slow. Profile first, optimize second.

## When to pick this up

When either:
- RL training is bottlenecked by environment step throughput
- Property test runs (1000 seeds) take > 60 seconds
- Replay-from-trace (used heavily in MCTS / branching exploration) feels
  noticeably slow at the 50-turn mark

## Approach

1. **Microbenchmark `step()`** with `pytest-benchmark` or a manual timer loop:
   ```python
   import time
   start = time.perf_counter_ns()
   for _ in range(10_000):
       state = step(state, action)
   elapsed_ns = time.perf_counter_ns() - start
   print(f"step() avg: {elapsed_ns / 10_000} ns")
   ```
2. **Profile with cProfile** to find hot spots:
   ```bash
   python -m cProfile -s cumulative -o profile.out -m engine.play --p1 ST-01 --p2 ST-02 --seed 42
   python -c "import pstats; pstats.Stats('profile.out').sort_stats('cumulative').print_stats(30)"
   ```
3. **Common culprits to check**:
   - Tuple rebuilds — when only one element changes, are we rebuilding the
     whole tuple? Use slicing + concatenation, not list-comprehension.
   - `dataclasses.replace` overhead — for frequently-modified fields, consider
     a builder pattern.
   - JSON parsing in hot paths — card definitions should be loaded once and
     held in memory, not re-parsed.
   - `legal_actions()` allocating large tuples — see if we can return a
     view or a generator for the common case.
4. **Turn-boundary memo cache** (escape hatch if replay is the bottleneck):
   - Hold an in-memory cache of `(seed, deck_pair, turn_n) → GameState`
   - Populated on first replay of a trace
   - Subsequent replays-to-turn-N skip ahead from the nearest cached turn
   - Bounded LRU; not persisted to disk

## Acceptance criteria (when picked up)

- [ ] Microbenchmark in `tests/test_perf.py` records step() p50 and p99
- [ ] Profile output documented in this file with date and version
- [ ] Hot spots identified and mitigated to hit the targets above
- [ ] Memo cache implemented IF and ONLY IF replay is shown to be the
      bottleneck for RL
