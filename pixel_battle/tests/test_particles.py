import pygame
from pixel_battle.engine.particles import ParticleSystem


def test_emit_hit_burst_creates_particles():
    ps = ParticleSystem()
    ps.emit_hit_burst(100, 200, count=8)
    assert len(ps.particles) == 8


def test_update_ages_particles():
    ps = ParticleSystem()
    ps.emit_hit_burst(0, 0, count=4)
    initial_count = len(ps.particles)
    for _ in range(50):
        ps.update()
    # All particles should expire within max lifetime (32)
    assert len(ps.particles) < initial_count


def test_render_doesnt_crash():
    pygame.init()
    surf = pygame.Surface((100, 100), pygame.SRCALPHA)
    ps = ParticleSystem()
    ps.emit_hit_burst(50, 50, count=5)
    ps.render(surf)  # should not raise
