from pixel_battle.engine.character import Character
from pixel_battle.engine.skill import SkillType


def test_brick_has_screw_dart_cd_skill():
    c = Character.load("brick_phone")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "screw_dart"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 5
    assert cd_skills[0].range == "special"


def test_glass_has_shard_scatter_cd_skill():
    c = Character.load("glass_slab")
    cd_skills = c.skills_of_type(SkillType.COOLDOWN)
    assert len(cd_skills) == 1
    assert cd_skills[0].id == "shard_scatter"
    assert cd_skills[0].cooldown_ms == 4000
    assert cd_skills[0].dmg == 4
    assert cd_skills[0].range == "special"
    assert cd_skills[0].stagger_ms == 500


def test_both_characters_still_have_basic_and_specials_and_ult():
    for char_id in ["brick_phone", "glass_slab"]:
        c = Character.load(char_id)
        assert len(c.skills_of_type(SkillType.BASIC)) == 1
        assert len(c.skills_of_type(SkillType.SPECIAL)) == 2
        assert len(c.skills_of_type(SkillType.ULTIMATE)) == 1
