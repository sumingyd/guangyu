"""图标/SVG 生成方法。"""
import os
from typing import Optional
from ui.styles_base import StylesBase, _SVG_TMPDIR, color_to_hex


class StylesIcons(StylesBase):
    """图标/SVG 生成方法。"""

    @classmethod
    def _get_svg_image(cls, cache: dict, filename_prefix: str, svg_content: str) -> str:
        """通用 SVG 图标缓存辅助：将 SVG 写入临时文件（每种变体只写一次），
        返回文件路径供 Qt QSS image: url(...) 使用。
        Qt 的 QSS 不支持 data URI，必须使用文件路径。"""
        with cls._cache_lock:
            if filename_prefix in cache:
                return cache[filename_prefix]
            path = os.path.join(_SVG_TMPDIR, f'{filename_prefix}.svg')
            try:
                if os.path.exists(path):
                    with open(path, 'r', encoding='utf-8') as f:
                        if f.read() == svg_content:
                            path = path.replace('\\', '/')
                            cache[filename_prefix] = path
                            return path
            except Exception:
                pass
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(svg_content)
            except Exception:
                pass
            # Qt QSS 在 Windows 下需要正斜杠路径
            path = path.replace('\\', '/')
            cache[filename_prefix] = path
            return path

    @classmethod
    def _get_arrow_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">'
            f'<path d="M0 0 L5 6 L10 0 Z" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._arrow_cache, f'arrow_down_{color.lstrip("#")}', svg)

    @classmethod
    def _get_sort_up_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
            f'<path d="M5 0 L10 8 L0 8 Z" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._sort_up_cache, f'sort_up_{color.lstrip("#")}', svg)

    @classmethod
    def _get_sort_down_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="8" viewBox="0 0 10 8">'
            f'<path d="M0 0 L10 0 L5 8 Z" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._sort_down_cache, f'sort_down_{color.lstrip("#")}', svg)

    @classmethod
    def _get_check_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
            f'<path d="M3 8 L6.5 11.5 L13 4.5" stroke="{color}" stroke-width="2.5" '
            f'fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._check_cache, f'check_{color.lstrip("#")}', svg)

    @classmethod
    def _get_radio_dot_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">'
            f'<circle cx="8" cy="8" r="4" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._radio_cache, f'radio_dot_{color.lstrip("#")}', svg)

    @classmethod
    def _get_spin_up_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">'
            f'<path d="M0 6 L5 0 L10 6 Z" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._spinup_cache, f'spin_up_{color.lstrip("#")}', svg)

    @classmethod
    def _get_spin_down_image(cls, color: str) -> str:
        color = color_to_hex(color)
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="6" viewBox="0 0 10 6">'
            f'<path d="M0 0 L5 6 L10 0 Z" fill="{color}"/>'
            f'</svg>'
        )
        return cls._get_svg_image(cls._spindown_cache, f'spin_down_{color.lstrip("#")}', svg)

    @classmethod
    def play_icon_name(cls, is_playing, is_paused) -> str:
        """播放/暂停按钮图标的唯一取值口径。

        图标表示"点击后执行的动作"：只有真正在播放（且未暂停）时显示暂停图标，
        空闲 / 停止 / 暂停 / 未知状态一律显示播放图标。初始创建、播放状态同步、
        主题重刷都从这里取值，避免各路径各写一份反向判断。
        """
        return 'pause' if (bool(is_playing) and not bool(is_paused)) else 'play'

    @classmethod
    def get_icon(cls, name: str, color: Optional[str] = None, size: int = 16) -> str:
        if color is None:
            color = cls._get_colors().get('window_text', cls._safe_fallback('window_text'))
        color = color_to_hex(color)
        key = f'{name}_{size}_{color.lstrip("#")}'
        if key in cls._icon_cache:
            return cls._icon_cache[key]
        svg = cls._build_icon_svg(name, color, size)
        if svg is None:
            return ''
        return cls._get_svg_image(cls._icon_cache, key, svg)

    @classmethod
    def _build_icon_svg(cls, name: str, color: str, size: int) -> Optional[str]:
        s = size
        h = round(s / 2)
        p = round(s * 0.15)
        def ri(v):
            return round(v)
        icons = {
            'play': (
                f'<polygon points="{ri(s*0.3)},{p} {ri(s*0.8)},{h} {ri(s*0.3)},{s-p}" fill="{color}"/>'
            ),
            'pause': (
                f'<rect x="{p}" y="{p}" width="{ri(s*0.3)}" height="{s-p*2}" rx="1" fill="{color}"/>'
                f'<rect x="{ri(s*0.55)}" y="{p}" width="{ri(s*0.3)}" height="{s-p*2}" rx="1" fill="{color}"/>'
            ),
            'stop': (
                f'<rect x="{p}" y="{p}" width="{s-p*2}" height="{s-p*2}" rx="2" fill="{color}"/>'
            ),
            'prev': (
                f'<polygon points="{h},{p} {p},{h} {h},{s-p}" fill="{color}"/>'
                f'<rect x="{ri(s*0.6)}" y="{p}" width="{ri(s*0.12)}" height="{s-p*2}" rx="1" fill="{color}"/>'
            ),
            'next': (
                f'<polygon points="{h},{p} {s-p},{h} {h},{s-p}" fill="{color}"/>'
                f'<rect x="{ri(s*0.28)}" y="{p}" width="{ri(s*0.12)}" height="{s-p*2}" rx="1" fill="{color}"/>'
            ),
            'backward': (
                f'<polygon points="{ri(s*0.55)},{p} {p},{h} {ri(s*0.55)},{s-p}" fill="{color}"/>'
                f'<polygon points="{s-p},{p} {ri(s*0.55)},{h} {s-p},{s-p}" fill="{color}"/>'
            ),
            'volume': (
                f'<path d="M{ri(p+s*0.05)},{h} L{ri(p+s*0.05)},{ri(h-s*0.15)} L{ri(p+s*0.3)},{ri(h-s*0.3)} L{ri(p+s*0.3)},{ri(h+s*0.3)} L{ri(p+s*0.05)},{ri(h+s*0.15)} Z" fill="{color}"/>'
                f'<path d="M{ri(p+s*0.38)},{ri(h-s*0.17)} A{ri(s*0.17)},{ri(s*0.17)} 0 0,1 {ri(p+s*0.38)},{ri(h+s*0.17)}" stroke="{color}" stroke-width="{ri(s*0.07)}" fill="none" stroke-linecap="round"/>'
                f'<path d="M{ri(p+s*0.5)},{ri(h-s*0.28)} A{ri(s*0.28)},{ri(s*0.28)} 0 0,1 {ri(p+s*0.5)},{ri(h+s*0.28)}" stroke="{color}" stroke-width="{ri(s*0.07)}" fill="none" stroke-linecap="round"/>'
            ),
            'volume_low': (
                f'<path d="M{ri(p+s*0.05)},{h} L{ri(p+s*0.05)},{ri(h-s*0.15)} L{ri(p+s*0.3)},{ri(h-s*0.3)} L{ri(p+s*0.3)},{ri(h+s*0.3)} L{ri(p+s*0.05)},{ri(h+s*0.15)} Z" fill="{color}"/>'
                f'<path d="M{ri(p+s*0.38)},{ri(h-s*0.17)} A{ri(s*0.17)},{ri(s*0.17)} 0 0,1 {ri(p+s*0.38)},{ri(h+s*0.17)}" stroke="{color}" stroke-width="{ri(s*0.07)}" fill="none" stroke-linecap="round"/>'
            ),
            'volume_mute': (
                f'<path d="M{ri(p+s*0.05)},{h} L{ri(p+s*0.05)},{ri(h-s*0.15)} L{ri(p+s*0.3)},{ri(h-s*0.3)} L{ri(p+s*0.3)},{ri(h+s*0.3)} L{ri(p+s*0.05)},{ri(h+s*0.15)} Z" fill="{color}"/>'
                f'<line x1="{ri(p+s*0.4)}" y1="{ri(h-s*0.15)}" x2="{ri(p+s*0.65)}" y2="{ri(h+s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.07)}" stroke-linecap="round"/>'
            ),
            'fullscreen': (
                f'<path d="M{p},{ri(p+s*0.25)} L{p},{p} L{ri(p+s*0.25)},{p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="M{ri(s-p-s*0.25)},{p} L{s-p},{p} L{s-p},{ri(p+s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="M{s-p},{ri(s-p-s*0.25)} L{s-p},{s-p} L{ri(s-p-s*0.25)},{s-p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="M{ri(p+s*0.25)},{s-p} L{p},{s-p} L{p},{ri(s-p-s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'restore': (
                f'<path d="M{ri(p+s*0.15)},{ri(p+s*0.35)} L{ri(p+s*0.15)},{ri(p+s*0.15)} L{ri(p+s*0.35)},{ri(p+s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<path d="M{ri(s-p-s*0.15)},{ri(s-p-s*0.35)} L{ri(s-p-s*0.15)},{ri(s-p-s*0.15)} L{ri(s-p-s*0.35)},{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
                f'<rect x="{p}" y="{ri(p+s*0.25)}" width="{ri(s-p*2-s*0.05)}" height="{ri(s-p*2-s*0.05)}" rx="1" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
            ),
            'minimize': (
                f'<line x1="{p}" y1="{h}" x2="{s-p}" y2="{h}" stroke="{color}" stroke-width="{ri(s*0.1)}" stroke-linecap="round"/>'
            ),
            'close': (
                f'<line x1="{p}" y1="{p}" x2="{s-p}" y2="{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" stroke-linecap="round"/>'
                f'<line x1="{s-p}" y1="{p}" x2="{p}" y2="{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" stroke-linecap="round"/>'
            ),
            'list_view': (
                f'<rect x="{p}" y="{p}" width="{s-p*2}" height="{ri(s*0.08)}" rx="1" fill="{color}"/>'
                f'<rect x="{p}" y="{ri(h-s*0.04)}" width="{s-p*2}" height="{ri(s*0.08)}" rx="1" fill="{color}"/>'
                f'<rect x="{p}" y="{ri(s-p-s*0.08)}" width="{s-p*2}" height="{ri(s*0.08)}" rx="1" fill="{color}"/>'
            ),
            'grid_view': (
                f'<rect x="{p}" y="{p}" width="{ri(h-p-s*0.04)}" height="{ri(h-p-s*0.04)}" rx="1" fill="{color}"/>'
                f'<rect x="{ri(h+s*0.04)}" y="{p}" width="{ri(h-p-s*0.04)}" height="{ri(h-p-s*0.04)}" rx="1" fill="{color}"/>'
                f'<rect x="{p}" y="{ri(h+s*0.04)}" width="{ri(h-p-s*0.04)}" height="{ri(h-p-s*0.04)}" rx="1" fill="{color}"/>'
                f'<rect x="{ri(h+s*0.04)}" y="{ri(h+s*0.04)}" width="{ri(h-p-s*0.04)}" height="{ri(h-p-s*0.04)}" rx="1" fill="{color}"/>'
            ),
            'pip': (
                f'<rect x="{p}" y="{p}" width="{s-p*2}" height="{s-p*2}" rx="2" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<rect x="{ri(h+s*0.05)}" y="{ri(h+s*0.05)}" width="{ri(h-p-s*0.05)}" height="{ri(h-p-s*0.05)}" rx="1" fill="{color}"/>'
            ),
            'more': (
                f'<circle cx="{ri(p+s*0.2)}" cy="{h}" r="{ri(s*0.08)}" fill="{color}"/>'
                f'<circle cx="{h}" cy="{h}" r="{ri(s*0.08)}" fill="{color}"/>'
                f'<circle cx="{ri(s-p-s*0.2)}" cy="{h}" r="{ri(s*0.08)}" fill="{color}"/>'
            ),
            'speed': (
                f'<circle cx="{h}" cy="{h}" r="{h-p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{h}" y1="{h}" x2="{h}" y2="{ri(p+s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
                f'<line x1="{h}" y1="{h}" x2="{ri(h+s*0.2)}" y2="{h}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'aspect': (
                f'<rect x="{p}" y="{p}" width="{s-p*2}" height="{s-p*2}" rx="2" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{ri(p+s*0.15)}" y1="{s-p}" x2="{ri(p+s*0.15)}" y2="{ri(s-p-s*0.2)}" stroke="{color}" stroke-width="{ri(s*0.06)}" stroke-linecap="round"/>'
                f'<line x1="{p}" y1="{ri(s-p-s*0.15)}" x2="{ri(p+s*0.2)}" y2="{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.06)}" stroke-linecap="round"/>'
            ),
            'audio_track': (
                f'<path d="M{h},{ri(p+s*0.1)} L{h},{ri(s-p-s*0.15)} Q{h},{s-p} {ri(h-s*0.15)},{s-p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round"/>'
                f'<circle cx="{ri(h-s*0.15)}" cy="{ri(s-p-s*0.1)}" r="{ri(s*0.1)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{h}" y1="{ri(p+s*0.1)}" x2="{s-p}" y2="{ri(p+s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'subtitle': (
                f'<rect x="{p}" y="{ri(h-s*0.15)}" width="{s-p*2}" height="{ri(s*0.3)}" rx="2" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{ri(p+s*0.15)}" y1="{h}" x2="{ri(p+s*0.4)}" y2="{h}" stroke="{color}" stroke-width="{ri(s*0.06)}" stroke-linecap="round"/>'
            ),
            'pin': (
                f'<path d="M{h},{ri(p+s*0.2)} L{h},{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round"/>'
                f'<circle cx="{h}" cy="{ri(p+s*0.2)}" r="{ri(s*0.12)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{ri(p+s*0.2)}" y1="{ri(s-p-s*0.15)}" x2="{ri(s-p-s*0.2)}" y2="{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'favorite': (
                f'<path d="M{h},{s-p} L{ri(p+s*0.12)},{ri(h+s*0.08)} L{ri(p+s*0.05)},{ri(p+s*0.2)} L{ri(h-s*0.12)},{ri(p+s*0.12)} L{h},{ri(p+s*0.05)} L{ri(h+s*0.12)},{ri(p+s*0.12)} L{ri(s-p-s*0.05)},{ri(p+s*0.2)} L{ri(s-p-s*0.12)},{ri(h+s*0.08)} Z" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linejoin="round"/>'
            ),
            'favorite_filled': (
                f'<path d="M{h},{s-p} L{ri(p+s*0.12)},{ri(h+s*0.08)} L{ri(p+s*0.05)},{ri(p+s*0.2)} L{ri(h-s*0.12)},{ri(p+s*0.12)} L{h},{ri(p+s*0.05)} L{ri(h+s*0.12)},{ri(p+s*0.12)} L{ri(s-p-s*0.05)},{ri(p+s*0.2)} L{ri(s-p-s*0.12)},{ri(h+s*0.08)} Z" fill="{color}" stroke="{color}" stroke-width="{ri(s*0.04)}" stroke-linejoin="round"/>'
            ),
            'history': (
                f'<circle cx="{h}" cy="{h}" r="{h-p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<polyline points="{h},{ri(p+s*0.15)} {h},{h} {ri(s-p-s*0.15)},{h}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'pin_active': (
                f'<path d="M{h},{ri(p+s*0.2)} L{h},{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
                f'<circle cx="{h}" cy="{ri(p+s*0.2)}" r="{ri(s*0.12)}" fill="{color}"/>'
                f'<line x1="{ri(p+s*0.2)}" y1="{ri(s-p-s*0.15)}" x2="{ri(s-p-s*0.2)}" y2="{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'tv': (
                f'<rect x="{ri(p+s*0.05)}" y="{ri(h-s*0.25)}" width="{ri(s-p*2-s*0.1)}" height="{ri(h-p-s*0.05)}" rx="1" stroke="{color}" stroke-width="{ri(s*0.09)}" fill="none"/>'
                f'<line x1="{ri(h-s*0.12)}" y1="{ri(p+s*0.05)}" x2="{ri(h-s*0.12)}" y2="{ri(h-s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.09)}" stroke-linecap="round"/>'
                f'<line x1="{ri(h+s*0.12)}" y1="{ri(p+s*0.05)}" x2="{ri(h+s*0.12)}" y2="{ri(h-s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.09)}" stroke-linecap="round"/>'
            ),
            'speaker': (
                f'<path d="M{ri(p+s*0.05)},{h} L{ri(p+s*0.05)},{ri(h-s*0.15)} L{ri(p+s*0.3)},{ri(h-s*0.3)} L{ri(p+s*0.3)},{ri(h+s*0.3)} L{ri(p+s*0.05)},{ri(h+s*0.15)} Z" fill="{color}"/>'
                f'<path d="M{ri(p+s*0.45)},{ri(h-s*0.22)} A{ri(s*0.22)},{ri(s*0.22)} 0 0,1 {ri(p+s*0.45)},{ri(h+s*0.22)}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round"/>'
            ),
            'signal': (
                f'<circle cx="{ri(p+s*0.2)}" cy="{ri(s-p-s*0.1)}" r="{ri(s*0.08)}" fill="{color}"/>'
                f'<path d="M{ri(p+s*0.38)},{ri(s-p-s*0.1)} A{ri(s*0.25)},{ri(s*0.25)} 0 0,1 {ri(p+s*0.2)},{ri(s-p-s*0.35)}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round"/>'
                f'<path d="M{ri(p+s*0.58)},{ri(s-p-s*0.1)} A{ri(s*0.45)},{ri(s*0.45)} 0 0,1 {ri(p+s*0.2)},{ri(s-p-s*0.55)}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round"/>'
            ),
            'calendar': (
                f'<rect x="{p}" y="{ri(p+s*0.25)}" width="{s-p*2}" height="{ri(s-p-s*0.25)}" rx="2" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<line x1="{p}" y1="{ri(p+s*0.45)}" x2="{s-p}" y2="{ri(p+s*0.45)}" stroke="{color}" stroke-width="{ri(s*0.06)}"/>'
                f'<line x1="{ri(h-s*0.15)}" y1="{p}" x2="{ri(h-s*0.15)}" y2="{ri(p+s*0.35)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
                f'<line x1="{ri(h+s*0.15)}" y1="{p}" x2="{ri(h+s*0.15)}" y2="{ri(p+s*0.35)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'folder': (
                f'<path d="M{p},{ri(p+s*0.25)} L{p},{s-p} Q{p},{s-p} {ri(p+s*0.05)},{s-p} L{ri(s-p-s*0.05)},{s-p} Q{s-p},{s-p} {s-p},{s-p} L{s-p},{ri(p+s*0.25)} Z" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linejoin="round"/>'
                f'<path d="M{p},{ri(p+s*0.25)} L{p},{ri(p+s*0.15)} Q{p},{ri(p+s*0.1)} {ri(p+s*0.05)},{ri(p+s*0.1)} L{ri(p+s*0.3)},{ri(p+s*0.1)} L{ri(p+s*0.4)},{ri(p+s*0.25)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linejoin="round"/>'
            ),
            'settings': (
                f'<circle cx="{h}" cy="{h}" r="{ri(s*0.2)}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<path d="M{h},{p} L{h},{ri(p+s*0.2)} M{h},{ri(s-p-s*0.2)} L{h},{s-p} M{p},{h} L{ri(p+s*0.2)},{h} M{ri(s-p-s*0.2)},{h} L{s-p},{h}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
                f'<path d="M{ri(p+s*0.15)},{ri(p+s*0.15)} L{ri(p+s*0.25)},{ri(p+s*0.25)} M{ri(s-p-s*0.25)},{ri(s-p-s*0.25)} L{ri(s-p-s*0.15)},{ri(s-p-s*0.15)} M{ri(s-p-s*0.15)},{ri(p+s*0.15)} L{ri(s-p-s*0.25)},{ri(p+s*0.25)} M{ri(p+s*0.25)},{ri(s-p-s*0.25)} L{ri(p+s*0.15)},{ri(s-p-s*0.15)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'edit': (
                f'<path d="M{ri(s-p-s*0.3)},{ri(p+s*0.2)} L{ri(p+s*0.3)},{ri(s-p-s*0.2)} L{ri(p+s*0.15)},{s-p} L{p},{ri(s-p-s*0.15)} L{ri(s-p-s*0.3)},{ri(p+s*0.2)} Z" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linejoin="round"/>'
                f'<line x1="{ri(s-p-s*0.45)}" y1="{ri(p+s*0.35)}" x2="{ri(s-p-s*0.15)}" y2="{ri(p+s*0.05)}" stroke="{color}" stroke-width="{ri(s*0.08)}" stroke-linecap="round"/>'
            ),
            'save': (
                f'<rect x="{p}" y="{p}" width="{s-p*2}" height="{s-p*2}" rx="2" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none"/>'
                f'<rect x="{ri(p+s*0.2)}" y="{p}" width="{ri(s-p*2-s*0.4)}" height="{ri(s*0.3)}" fill="{color}"/>'
                f'<rect x="{ri(p+s*0.25)}" y="{h}" width="{ri(s-p*2-s*0.5)}" height="{ri(s*0.25)}" rx="1" stroke="{color}" stroke-width="{ri(s*0.06)}" fill="none"/>'
            ),
            'refresh': (
                f'<path d="M{s-p},{h} A{h-p},{h-p} 0 1,1 {h},{p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round"/>'
                f'<polygon points="{h},{p} {ri(h+s*0.15)},{ri(p+s*0.2)} {ri(h-s*0.15)},{ri(p+s*0.2)}" fill="{color}"/>'
            ),
            'check': (
                f'<path d="M{ri(p+s*0.2)},{h} L{ri(h-s*0.1)},{ri(s-p-s*0.15)} L{s-p},{ri(p+s*0.2)}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'hourglass': (
                f'<path d="M{ri(p+s*0.2)},{p} L{ri(s-p-s*0.2)},{p} L{h},{h} L{ri(s-p-s*0.2)},{s-p} L{ri(p+s*0.2)},{s-p} L{h},{h} Z" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linejoin="round"/>'
            ),
            'chevron_left': (
                f'<polyline points="{s-p},{p} {p},{h} {s-p},{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'chevron_right': (
                f'<polyline points="{p},{p} {s-p},{h} {p},{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'chevron_down': (
                f'<polyline points="{p},{p} {h},{s-p} {s-p},{p}" stroke="{color}" stroke-width="{ri(s*0.1)}" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
            ),
            'exit_catchup': (
                f'<path d="M{s-p},{h} L{ri(h-s*0.2)},{h} A{h-p},{h-p} 0 1,1 {h},{p}" stroke="{color}" stroke-width="{ri(s*0.08)}" fill="none" stroke-linecap="round"/>'
                f'<polygon points="{ri(h-s*0.2)},{h} {ri(h-s*0.05)},{ri(h-s*0.12)} {ri(h-s*0.35)},{ri(h-s*0.12)}" fill="{color}"/>'
                f'<line x1="{ri(h+s*0.1)}" y1="{ri(h+s*0.1)}" x2="{s-p}" y2="{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" stroke-linecap="round"/>'
                f'<line x1="{s-p}" y1="{ri(h+s*0.1)}" x2="{ri(h+s*0.1)}" y2="{s-p}" stroke="{color}" stroke-width="{ri(s*0.1)}" stroke-linecap="round"/>'
            ),
        }
        body = icons.get(name)
        if body is None:
            return None
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'{body}'
            f'</svg>'
        )

    COLOR_PALETTES = {
        'dark': {
            'window': '#000000',
            'window_text': '#ffffff',
            'base': '#1a1a1a',
            'alternate_base': '#2a2a2a',
            'button': '#3a3a3a',
            'light': '#444444',
            'mid': '#555555',
            'dark': '#666666',
            'highlight': '#2a3a5a',
            'highlighted_text': '#6a9eff',
            'bright_text': '#ffffff',
            'link': '#6a9eff',
            'link_visited': '#8a7eff',
            'tooltip_base': '#2a2a2a',
            'tooltip_text': '#f0f0f0',
            'placeholder': '#aaaaaa',
            'accent': '#4a7eff',
            'accent_hover': '#3a6eff',
            'accent_pressed': '#2a5eff',
            'success': '#4CAF50',
            'warning': '#FF9800',
            'error': '#f44336',
            'error_background': '#3a1a1a',
            'info': '#2196F3',
            'table_header': '#3a3a3a',
            'table_header_gradient_start': '#444444',
            'table_header_gradient_middle': '#3a3a3a',
            'table_header_gradient_end': '#2a2a2a',
            'table_header_text': '#ffffff',
            'table_header_hover': '#4a7eff',
            'table_border': '#555555',
            'table_grid': '#444444',
            'table_alternate': '#1a1a1a',
            'table_hover': '#2a3a5a',
            'table_selection': '#4a7eff',
            'table_selection_text': '#ffffff',
            'player_background': '#1a1a1a',
            'player_panel': '#2a2a2a',
            'player_panel_text': '#ffffff',
            'player_panel_secondary': '#aaaaaa',
            'player_panel_disabled': '#8a8a8a',
            'player_panel_hint': '#9a9a9a',
            'player_button': 'rgba(60, 60, 60, 0.9)',
            'player_combo': 'rgba(45, 45, 45, 0.8)',
            'player_line': '#555555',
            'player_accent': '#6a9eff',
            'player_success': '#4CAF50',
            'player_warning': '#ff6464',
            'player_slider_track': '#555555',
            'player_slider_fill': '#6a9eff',
            'player_slider_handle': '#ffffff',
            'player_cache_bar': 'rgba(106, 158, 255, 0.4)',
            'player_volume_track': '#444444',
            'player_video_placeholder': '#1a1a1a',
            'window_opacity': 140,
            'osd_text': '#ffffff',
            'osd_border': '#000000',
            'osd_shadow': '#000000',
            'shadow_light': 'rgba(255,255,255,0.05)',
            'shadow_dark': 'rgba(0,0,0,0.4)',
            'neumorphic_light': '#323232',
            'neumorphic_dark': '#0a0a0a',
        },
        'light': {
            'window': '#f0f0f0',
            'window_text': '#333333',
            'base': '#ffffff',
            'alternate_base': '#e8e8e8',
            'button': '#d0d0d0',
            'light': '#e0e0e0',
            'mid': '#c0c0c0',
            'dark': '#a0a0a0',
            'highlight': '#cce0ff',
            'highlighted_text': '#2a6eff',
            'bright_text': '#000000',
            'link': '#2a6eff',
            'link_visited': '#6a5eff',
            'tooltip_base': '#ffffff',
            'tooltip_text': '#333333',
            'placeholder': '#767676',
            'accent': '#2a6eff',
            'accent_hover': '#1a5eff',
            'accent_pressed': '#0a4eff',
            'success': '#4CAF50',
            'warning': '#FF9800',
            'error': '#f44336',
            'error_background': '#ffdddd',
            'info': '#2196F3',
            'table_header': '#d8d8d8',
            'table_header_gradient_start': '#e8e8e8',
            'table_header_gradient_middle': '#d8d8d8',
            'table_header_gradient_end': '#c8c8c8',
            'table_header_text': '#333333',
            'table_header_hover': '#2a6eff',
            'table_border': '#c0c0c0',
            'table_grid': '#d0d0d0',
            'table_alternate': '#f5f5f5',
            'table_hover': '#cce0ff',
            'table_selection': '#2a6eff',
            'table_selection_text': '#ffffff',
            'player_background': '#e0e0e0',
            'player_panel': '#fafafa',
            'player_panel_text': '#333333',
            'player_panel_secondary': '#555555',
            'player_panel_disabled': '#767676',
            'player_panel_hint': '#666666',
            'player_button': 'rgba(200, 200, 200, 0.9)',
            'player_combo': 'rgba(220, 220, 220, 0.8)',
            'player_line': '#c0c0c0',
            'player_accent': '#2a6eff',
            'player_success': '#4CAF50',
            'player_warning': '#ff6464',
            'player_slider_track': '#c0c0c0',
            'player_slider_fill': '#2a6eff',
            'player_slider_handle': '#333333',
            'player_cache_bar': 'rgba(42, 110, 255, 0.35)',
            'player_volume_track': '#d0d0d0',
            'player_video_placeholder': '#e0e0e0',
            'window_opacity': 160,
            'osd_text': '#1a1a1a',
            'osd_border': '#ffffff',
            'osd_shadow': '#808080',
            'shadow_light': 'rgba(255,255,255,0.8)',
            'shadow_dark': 'rgba(0,0,0,0.12)',
            'neumorphic_light': '#ffffff',
            'neumorphic_dark': '#d0d0d0',
        },
    }


