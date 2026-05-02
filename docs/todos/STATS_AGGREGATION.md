# TODO: Stats Aggregation

> **Status**: Deferred. Belongs to RL phase (Phase 2 of the project roadmap).
> Vanilla MVP saves single-game traces but does not aggregate across games.

## Goal

Crunch large batches of game traces (1000s) into matchup tables, win-rate
distributions, game-length histograms, life-remaining distributions, and the
"first-vs-second" variance metric the user has called out as a key insight.

## Why deferred

Until the RL training loop exists, there's no batched simulation to aggregate
over. We don't know yet which stats matter — different RL algorithms care about
different things. Building this now would mean designing a schema we'll
immediately want to change.

## Approach (when picked up)

1. **Define the run record format** — what does ONE game produce in terms of
   stats? At minimum: winner, win_reason, turns, p1_life_remaining,
   p2_life_remaining, p1_deck_remaining, p2_deck_remaining, who_went_first.
2. **Choose a storage layer**:
   - SQLite (simple, queryable, no service to run) — recommended for batches up to ~1M
   - DuckDB (columnar, faster aggregations) — if batch sizes grow
   - Parquet files (pure data, no DB) — if you want to stream into pandas
3. **Build the aggregator**: takes a directory of trace JSONLs, extracts run
   records, writes to the storage layer.
4. **Build the analyzer**: produces the actual statistical reports — matchup
   tables, win rate by deck pairing, win rate by who-went-first, etc.
5. **Hook into RL pipeline**: every self-play game writes its trace to a
   common pool; aggregator runs nightly or per-batch.

## Initial reports (sketch)

- **Matchup table**: rows = P1 deck, cols = P2 deck, cell = P1 win rate over N games
- **First-vs-second variance**: across all matchups, P(win | went first) vs
  P(win | went second) — the user's hypothesis is that this is a stronger
  predictor than deck choice
- **Game length distribution**: histogram of turn counts by matchup
- **Win-reason breakdown**: % LIFE_AND_LEADER_HIT vs DECK_OUT by matchup
  (high DECK_OUT % → bots are passive)

## Acceptance criteria (when picked up)

- [ ] 1000-game batch produces a queryable stats table
- [ ] Matchup table renders for any pair of decks
- [ ] First-vs-second variance reported per matchup AND aggregated
- [ ] Aggregator handles 100k+ games without OOM
