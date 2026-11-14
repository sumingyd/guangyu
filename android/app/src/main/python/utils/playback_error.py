"""播放错误归类：把底层报错翻译成用户能照做的下一步动作。

底层错误文本（mpv 错误码、HTTP 状态、解码器名称）对用户没有意义，
这里按类别归一到固定提示，原始文本仍由调用方写入日志。
"""
import re

# 顺序即优先级：越靠前的规则越具体
_ERROR_RULES = (
    (re.compile(r'\b401\b|\b403\b|unauthorized|forbidden|鉴权|未授权|禁止访问|无权限', re.IGNORECASE),
     'error_play_auth', '登录或权限失效，请刷新线路后重试'),
    (re.compile(r'\b404\b|\b410\b|not found|链接已失效|地址失效|频道不存在', re.IGNORECASE),
     'error_play_expired', '链接已失效，请刷新线路后重试'),
    (re.compile(r'timed? ?out|timeout|超时|无法连接|connection refused|connection reset|'
                r'network|网络|name resolution|dns|errno 1[01][01]|1006[01]|getaddrinfo',
                re.IGNORECASE),
     'error_play_network', '网络连接失败，请检查网络或稍后重试'),
    (re.compile(r'drm|encrypted|加密|license|授权不可用', re.IGNORECASE),
     'error_play_drm', '该频道需要授权，当前无法播放'),
    (re.compile(r'audio|音频|mp2|ac3|eac3|dts|声道', re.IGNORECASE),
     'error_play_audio', '音频解码失败，请切换播放内核或换台'),
    (re.compile(r'decode|解码失败|hardware|hwdec|gpu|mediacodec', re.IGNORECASE),
     'error_play_decode', '设备解码不支持，请切换软解或降低清晰度'),
    (re.compile(r'unsupported|not supported|无法解析|格式|codec|invalid data|moov atom|moof|'
                r'container|容器', re.IGNORECASE),
     'error_play_format', '媒体格式无法识别，请刷新线路或切换播放内核'),
)

_GENERIC_KEY = 'error_play_generic'
_GENERIC_DEFAULT = '播放失败，请检查网络或切换频道后重试'


def classify_playback_error(message) -> tuple:
    """返回 (i18n 键, 默认中文文案)。原始错误由调用方自行记日志。"""
    text = str(message or '')
    for pattern, key, default in _ERROR_RULES:
        if pattern.search(text):
            return key, default
    return _GENERIC_KEY, _GENERIC_DEFAULT
