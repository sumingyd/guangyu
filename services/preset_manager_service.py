"""预设管理服务 — 第三阶段高级功能

允许用户保存、加载、导出/导入自定义视频增强预设，
并支持按频道/分组绑定不同预设。

预设存储格式（JSON）：
{
    "version": 1,
    "presets": [
        {
            "name": "我的动画预设",
            "description": "适合看番的参数组合",
            "settings": {
                "brightness": 0, "contrast": 5, "saturation": 10,
                "hue": 0, "gamma": 0, "sharpness": 0.2,
                "video_rotate": 0, "video_flip": "",
                "motion_comp": "low", "motion_comp_fps": 60,
                "superres_scale": "ewa_lanczos", "superres_detail": 20,
                "shader_preset": "anime4k"
            },
            "created_at": "2026-08-02T16:00:00"
        }
    ],
    "channel_bindings": {
        "CCTV-1 综合": "我的动画预设",
        "CCTV-5 体育": "体育预设"
    }
}
"""
import json
import os
from datetime import datetime
from typing import Optional

from core.log_manager import global_logger as logger


class PresetManagerService:
    """用户自定义预设管理"""

    PRESET_FILE = 'video_presets.json'
    VERSION = 1

    # 内置预设（不可删除）
    BUILTIN_PRESETS = {
        '智能推荐': {
            'motion_comp': 'auto', 'motion_comp_fps': 60,
            'superres_scale': 'auto', 'superres_detail': 0,
            'shader_preset': 'auto',
        },
        '性能优先': {
            'motion_comp': 'off', 'motion_comp_fps': 60,
            'superres_scale': 'bilinear', 'superres_detail': 0,
            'shader_preset': 'off',
        },
        '画质优先': {
            'motion_comp': 'medium', 'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczossharp', 'superres_detail': 40,
            'shader_preset': 'off',
        },
        '动画优化': {
            'motion_comp': 'low', 'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczos', 'superres_detail': 20,
            'shader_preset': 'anime4k',
        },
        '体育直播': {
            'motion_comp': 'high', 'motion_comp_fps': 60,
            'superres_scale': 'lanczos', 'superres_detail': 30,
            'shader_preset': 'off',
        },
        '电影模式': {
            'motion_comp': 'medium', 'motion_comp_fps': 60,
            'superres_scale': 'ewa_lanczossharp', 'superres_detail': 40,
            'shader_preset': 'off',
            'gamma': -5, 'saturation': 5,
        },
    }

    def __init__(self, config_dir: str = ''):
        if not config_dir:
            # 用户预设属于配置数据，必须写入用户目录而不是进程工作目录
            from utils.app_paths import get_config_dir
            config_dir = get_config_dir()
        self._config_dir = config_dir
        self._preset_path = os.path.join(self._config_dir, self.PRESET_FILE)
        self._data = None
        self._load()

    def _load(self):
        """从文件加载预设数据"""
        default = {
            'version': self.VERSION,
            'presets': [],
            'channel_bindings': {},
        }
        if not os.path.isfile(self._preset_path):
            self._data = default
            return
        try:
            with open(self._preset_path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
            if 'presets' not in self._data:
                self._data['presets'] = []
            if 'channel_bindings' not in self._data:
                self._data['channel_bindings'] = {}
        except Exception as e:
            logger.warning(f"加载预设文件失败: {e}，使用默认值")
            self._data = default

    def _save(self):
        """保存预设数据到文件"""
        try:
            with open(self._preset_path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存预设文件失败: {e}")

    def list_presets(self, include_builtin: bool = True) -> list:
        """列出所有预设

        :param include_builtin: 是否包含内置预设
        :return: [{'name': str, 'description': str, 'settings': dict,
                   'builtin': bool, 'created_at': str}]
        """
        result = []
        if include_builtin:
            for name, settings in self.BUILTIN_PRESETS.items():
                result.append({
                    'name': name,
                    'description': '',
                    'settings': settings,
                    'builtin': True,
                    'created_at': '',
                })
        for preset in self._data.get('presets', []):
            result.append({
                'name': preset.get('name', ''),
                'description': preset.get('description', ''),
                'settings': preset.get('settings', {}),
                'builtin': False,
                'created_at': preset.get('created_at', ''),
            })
        return result

    def get_preset(self, name: str) -> Optional[dict]:
        """按名称获取预设

        :param name: 预设名称
        :return: 预设设置字典，或 None
        """
        # 先查内置
        if name in self.BUILTIN_PRESETS:
            return self.BUILTIN_PRESETS[name].copy()
        # 再查自定义
        for preset in self._data.get('presets', []):
            if preset.get('name') == name:
                return preset.get('settings', {}).copy()
        return None

    def save_preset(self, name: str, settings: dict,
                    description: str = '') -> bool:
        """保存自定义预设

        :param name: 预设名称
        :param settings: 参数字典
        :param description: 描述
        :return: 成功与否
        """
        if not name or not name.strip():
            return False
        name = name.strip()
        if name in self.BUILTIN_PRESETS:
            logger.warning(f"预设名称 '{name}' 与内置预设冲突")
            return False
        presets = self._data.get('presets', [])
        # 更新或新增
        for preset in presets:
            if preset.get('name') == name:
                preset['settings'] = settings
                preset['description'] = description
                preset['updated_at'] = datetime.now().isoformat()
                self._save()
                logger.info(f"预设 '{name}' 已更新")
                return True
        presets.append({
            'name': name,
            'description': description,
            'settings': settings,
            'created_at': datetime.now().isoformat(),
        })
        self._data['presets'] = presets
        self._save()
        logger.info(f"预设 '{name}' 已保存")
        return True

    def delete_preset(self, name: str) -> bool:
        """删除自定义预设

        :param name: 预设名称
        :return: 成功与否
        """
        if name in self.BUILTIN_PRESETS:
            logger.warning(f"内置预设 '{name}' 不可删除")
            return False
        presets = self._data.get('presets', [])
        before = len(presets)
        self._data['presets'] = [
            p for p in presets if p.get('name') != name
        ]
        if len(self._data['presets']) < before:
            # 清理频道绑定
            bindings = self._data.get('channel_bindings', {})
            to_remove = [
                ch for ch, pname in bindings.items() if pname == name
            ]
            for ch in to_remove:
                del bindings[ch]
            self._save()
            logger.info(f"预设 '{name}' 已删除")
            return True
        return False

    def bind_channel_preset(self, channel_name: str, preset_name: str) -> bool:
        """绑定频道到预设

        :param channel_name: 频道名称
        :param preset_name: 预设名称
        :return: 成功与否
        """
        if not channel_name or not preset_name:
            return False
        self._data.setdefault('channel_bindings', {})[channel_name] = preset_name
        self._save()
        logger.info(f"频道 '{channel_name}' 绑定到预设 '{preset_name}'")
        return True

    def unbind_channel_preset(self, channel_name: str) -> bool:
        """解除频道预设绑定

        :param channel_name: 频道名称
        :return: 成功与否
        """
        bindings = self._data.get('channel_bindings', {})
        if channel_name in bindings:
            del bindings[channel_name]
            self._save()
            logger.info(f"频道 '{channel_name}' 预设绑定已解除")
            return True
        return False

    def get_channel_preset(self, channel_name: str) -> Optional[str]:
        """获取频道绑定的预设名称

        :param channel_name: 频道名称
        :return: 预设名称，或 None
        """
        return self._data.get('channel_bindings', {}).get(channel_name)

    def get_all_bindings(self) -> dict:
        """获取所有频道绑定"""
        return self._data.get('channel_bindings', {}).copy()

    def export_presets(self, file_path: str) -> bool:
        """导出预设到文件

        :param file_path: 目标文件路径
        :return: 成功与否
        """
        try:
            export_data = {
                'version': self.VERSION,
                'presets': self._data.get('presets', []),
                'channel_bindings': self._data.get('channel_bindings', {}),
                'exported_at': datetime.now().isoformat(),
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            logger.info(f"预设已导出到: {file_path}")
            return True
        except Exception as e:
            logger.error(f"导出预设失败: {e}")
            return False

    def import_presets(self, file_path: str, overwrite: bool = False) -> int:
        """从文件导入预设

        :param file_path: 源文件路径
        :param overwrite: 是否覆盖同名预设
        :return: 导入的预设数量
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            imported = data.get('presets', [])
            if not imported:
                return 0
            existing = self._data.get('presets', [])
            existing_names = {p.get('name') for p in existing}
            count = 0
            for preset in imported:
                name = preset.get('name', '')
                if not name or name in self.BUILTIN_PRESETS:
                    continue
                if name in existing_names and not overwrite:
                    continue
                if name in existing_names and overwrite:
                    for i, p in enumerate(existing):
                        if p.get('name') == name:
                            existing[i] = preset
                            count += 1
                            break
                else:
                    existing.append(preset)
                    existing_names.add(name)
                    count += 1
            self._data['presets'] = existing
            # 合并频道绑定
            imported_bindings = data.get('channel_bindings', {})
            if imported_bindings:
                self._data.setdefault('channel_bindings', {}).update(
                    imported_bindings
                )
            self._save()
            logger.info(f"成功导入 {count} 个预设")
            return count
        except Exception as e:
            logger.error(f"导入预设失败: {e}")
            return 0


# 单例
_instance = None
_instance_lock = __import__('threading').Lock()


def get_preset_manager(config_dir: str = '') -> PresetManagerService:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = PresetManagerService(config_dir)
    return _instance
