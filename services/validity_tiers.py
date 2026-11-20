"""频道有效性三档定义与兼容工具。

三档：
- ``valid``     ：确证有效（真实拉流解析出流，或内容嗅探命中明确媒体特征）
- ``suspected`` ：疑似（能连上但没解析出流，或只做了弱检查）
- ``invalid``   ：不可用（明确的 4xx / 拒连 / 解析失败）

持久化兼容：老缓存只有 ``valid`` 布尔值。读取时优先用 ``validity``，
缺失时按 ``valid`` 映射（True→valid，False→invalid，None→未检测）。
"""
from typing import Any, Dict

VALID = 'valid'
SUSPECTED = 'suspected'
INVALID = 'invalid'

ALL_TIERS = (VALID, SUSPECTED, INVALID)

# 中文状态文案（桌面端与 Android 端共用同一口径）
STATUS_TEXT = {
    VALID: '有效',
    SUSPECTED: '疑似',
    INVALID: '无效',
}

# 各档对应到旧数据的 valid 字段：疑似不算确证有效，也不算不可用
VALID_BOOL = {
    VALID: True,
    SUSPECTED: None,
    INVALID: False,
}


def channel_tier(channel: Dict[str, Any] | None) -> str | None:
    """读取频道记录的档位；未检测返回 None。"""
    if not channel:
        return None
    tier = str(channel.get('validity', '') or '').strip().lower()
    if tier in ALL_TIERS:
        return tier
    valid = channel.get('valid')
    if valid is True:
        return VALID
    if valid is False:
        return INVALID
    return None


def tier_from_valid(valid: Any) -> str | None:
    """把旧 valid 布尔值映射为档位。"""
    if valid is True:
        return VALID
    if valid is False:
        return INVALID
    return None


def valid_bool_for(tier: str | None) -> bool | None:
    """档位映射回旧 valid 字段（兼容仍在读 valid 的调用方）。"""
    return VALID_BOOL.get(tier)


def status_text_for(tier: str | None) -> str:
    """频道状态列的展示文案。"""
    return STATUS_TEXT.get(tier or '', '待检测')


def apply_tier(channel: Dict[str, Any], tier: str | None, status: str | None = None) -> None:
    """把档位写回频道字典，同时维护旧 valid 字段与状态文案。"""
    if tier:
        channel['validity'] = tier
        channel['valid'] = valid_bool_for(tier)
        channel['status'] = status or STATUS_TEXT[tier]
    else:
        channel.pop('validity', None)
        channel['valid'] = None
        channel['status'] = status or '待检测'
