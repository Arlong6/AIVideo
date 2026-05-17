from pixel_battle.engine.rng import BattleRNG


def test_same_seed_produces_same_sequence():
    a = BattleRNG(seed=42)
    b = BattleRNG(seed=42)
    seq_a = [a.uniform() for _ in range(20)]
    seq_b = [b.uniform() for _ in range(20)]
    assert seq_a == seq_b


def test_different_seeds_produce_different_sequences():
    a = BattleRNG(seed=1)
    b = BattleRNG(seed=2)
    assert a.uniform() != b.uniform()


def test_roll_check_true_when_under_probability():
    rng = BattleRNG(seed=42)
    assert rng.roll_check(1.0) is True


def test_roll_check_false_when_zero_probability():
    rng = BattleRNG(seed=42)
    assert rng.roll_check(0.0) is False


def test_randint_range_inclusive():
    rng = BattleRNG(seed=42)
    for _ in range(50):
        v = rng.randint(5, 8)
        assert 5 <= v <= 8
