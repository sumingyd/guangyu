from services.logo_cache_service import LogoCacheService


def test_scaled_size_does_not_upscale(monkeypatch):
    monkeypatch.setattr(LogoCacheService, '_device_pixel_ratio', staticmethod(lambda: 1.0))
    assert LogoCacheService._scaled_size(1920, 1080, 160, 90, 800_000) == (160, 90)


def test_scaled_size_keeps_aspect_ratio(monkeypatch):
    monkeypatch.setattr(LogoCacheService, '_device_pixel_ratio', staticmethod(lambda: 1.0))
    w, h = LogoCacheService._scaled_size(1000, 1000, 100, 200, 800_000)
    assert (w, h) == (100, 100)


def test_scaled_size_caps_total_pixels(monkeypatch):
    monkeypatch.setattr(LogoCacheService, '_device_pixel_ratio', staticmethod(lambda: 1.0))
    w, h = LogoCacheService._scaled_size(4096, 4096, 4096, 4096, 240_000)
    assert w * h <= 240_000
