from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType
from pixel_battle.engine.battle import Battle, BattleState, EventType
from pixel_battle.engine.rng import BattleRNG
from pixel_battle.engine.physics import SPECIAL_RANGE, MELEE_RANGE


def test_brick_has_screw_dart_cd_skill():
    c = Character.load("brick_phone")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "screw_dart"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 5
    assert cd_skills[0].range == 250


def test_glass_has_shard_scatter_cd_skill():
    c = Character.load("glass_slab")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "shard_scatter"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 4
    assert cd_skills[0].range == 240
    assert cd_skills[0].stagger_ms == 500


def test_both_characters_still_have_basic_and_specials_and_ult():
    for char_id in ["brick_phone", "glass_slab"]:
        c = Character.load(char_id)
        assert len(c.skills_of_type(SkillType.BASIC)) == 1
        assert len(c.skills_of_type(SkillType.SPECIAL)) == 2
        assert len(c.skills_of_type(SkillType.ULTIMATE)) == 1


def _setup_close_battle(seed=42):
    a = Character.load("brick_phone")
    b = Character.load("glass_slab")
    bat = Battle(left=a, right=b, rng=BattleRNG(seed))
    # Past intro
    bat.tick_ms(2500)
    return bat, a, b


def test_cd_skill_hit_sets_ready_at():
    """When CD skill lands a hit, attacker.skill_cd_ready_at gets set."""
    bat, a, b = _setup_close_battle(seed=42)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    # Place attacker in range, force attack with the CD skill
    a.pos_x = 200
    b.pos_x = 200 + int(SPECIAL_RANGE * 0.5)
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0  # guarantee hit
    # P5: stun defender so pushback doesn't displace attacker out of range
    b.windup_stun_until_ms = bat.elapsed_ms + 5000
    # Tick through windup -> active (windup is 200ms)
    for _ in range(20):
        bat.tick_ms(16)
    # skill_cd_ready_at should now contain screw_dart
    assert "screw_dart" in a.skill_cd_ready_at
    assert a.skill_cd_ready_at["screw_dart"] >= bat.elapsed_ms


def test_cd_skill_connects_at_numeric_range():
    """CD skill has a numeric range (250), so it lands in the zone past MELEE_RANGE (110)."""
    bat, a, b = _setup_close_battle(seed=99)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    # Place attacker JUST beyond MELEE_RANGE but inside SPECIAL_RANGE
    a.pos_x = 200
    b.pos_x = 200 + int((MELEE_RANGE + SPECIAL_RANGE) / 2)  # mid-zone
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0
    # P5: stun defender so pushback doesn't displace attacker out of range
    b.windup_stun_until_ms = bat.elapsed_ms + 5000
    starting_hp = b.hp
    for _ in range(20):
        bat.tick_ms(16)
        if b.hp < starting_hp:
            break
    assert b.hp < starting_hp, "CD skill should connect at special range"


def test_cd_skill_uses_custom_stagger_ms():
    """shard_scatter has stagger_ms=500, so defender stagger is longer than default 300."""
    a = Character.load("glass_slab")
    b = Character.load("brick_phone")
    bat = Battle(left=a, right=b, rng=BattleRNG(42))
    bat.tick_ms(2500)
    cd_skill = a.skills_of_type(SkillType.COOLDOWN)[0]
    assert cd_skill.stagger_ms == 500
    a.pos_x = 200
    b.pos_x = 200 + int(SPECIAL_RANGE * 0.4)
    a.attack_used_kind = cd_skill
    a.attack_phase = "windup"
    a.attack_phase_t = 0
    a.action_state = "attacking"
    a.accuracy = 1.0
    # P5: stun defender so pushback doesn't displace attacker out of range
    b.windup_stun_until_ms = bat.elapsed_ms + 5000
    for _ in range(20):
        bat.tick_ms(16)
        if b.action_state == "hit_stagger":
            break
    assert b.action_state == "hit_stagger"
    assert getattr(b, "_stagger_remaining_ms", 0) >= 480  # ~500ms minus a tick
