"""Run 20 battles, print HP/MP/duration stats. Use to tune pacing."""
import statistics

from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.character import Character
from pixel_battle.engine.rng import BattleRNG


def run_one(seed: int) -> dict:
    b = Battle(
        left=Character.load("brick_phone"),
        right=Character.load("glass_slab"),
        rng=BattleRNG(seed),
    )
    while b.state is not BattleState.KO and b.elapsed_ms < 90_000:
        b.tick_ms(16)
    ult_count = sum(1 for e in b.events if e.type is EventType.ULTIMATE_START)
    hits = sum(1 for e in b.events if e.type is EventType.HIT)
    misses = sum(1 for e in b.events if e.type is EventType.MISS)
    winner = "brick" if b.right.is_ko() else ("glass" if b.left.is_ko() else "timeout")
    return {
        "seed": seed,
        "duration_s": b.elapsed_ms / 1000,
        "ults": ult_count,
        "hits": hits,
        "misses": misses,
        "winner": winner,
    }


def main():
    results = [run_one(s) for s in range(20)]
    durations = [r["duration_s"] for r in results]
    print(f"{'seed':>4} {'dur':>6} {'ults':>4} {'hits':>4} {'miss':>4} winner")
    for r in results:
        print(f"{r['seed']:>4} {r['duration_s']:>6.1f} {r['ults']:>4} {r['hits']:>4} {r['misses']:>4} {r['winner']}")
    print(f"\nDuration: mean={statistics.mean(durations):.1f}s, "
          f"median={statistics.median(durations):.1f}s, "
          f"min={min(durations):.1f}s, max={max(durations):.1f}s")
    brick_wins = sum(1 for r in results if r["winner"] == "brick")
    print(f"Brick wins: {brick_wins}/20")


if __name__ == "__main__":
    main()
