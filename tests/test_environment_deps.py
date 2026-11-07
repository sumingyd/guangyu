"""测试环境隔离校验：不得加载 android 等 vendored 目录中的第三方依赖。"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _requirements_version(package: str):
    path = os.path.join(REPO_ROOT, 'requirements.txt')
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.split('#', 1)[0].strip()
            if line.lower().startswith(package.lower() + '=='):
                return line.split('==', 1)[1].strip()
    return None


def test_sys_path_does_not_contain_vendored_android_dir():
    normalized = [p.replace('\\', '/') for p in sys.path if p]
    assert not any('/android/' in p for p in normalized), \
        f"android 目录被加入 sys.path，测试可能加载 vendored 依赖: {normalized}"


def test_aiohttp_is_loaded_from_environment_not_vendored_copy():
    import aiohttp

    module_path = os.path.abspath(aiohttp.__file__).replace('\\', '/')
    assert '/android/' not in module_path, f"aiohttp 来自 android 目录: {module_path}"

    expected = _requirements_version('aiohttp')
    assert expected is not None
    assert aiohttp.__version__ == expected, \
        f"aiohttp 版本 {aiohttp.__version__} 与 requirements 锁定版本 {expected} 不一致"
