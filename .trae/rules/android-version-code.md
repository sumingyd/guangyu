# Android versionCode 统一规则

## 唯一真源

- 版本号只写在 `core/version.py` 的 `CURRENT_VERSION`，格式固定四段 `major.minor.patch.build`，每段 0-99。
- `android/app/build.gradle` 在配置阶段读取该文件生成 `versionName` 与 `versionCode`，不在 gradle 里另写版本号。
- `android/app/src/main/python/core/version.py` 是独立跟踪的副本（APK 内 Python 运行时用），必须与根目录文件保持一致；`validate-version` 作业会解析两边版本并强制相等。
- 发版时同步修改两处，只改一处会让 APK 内报告的版本与实际包版本脱节。

## versionCode 公式

```
versionCode = major * 10000000 + minor * 100000 + patch * 100 + build
```

- 例：`50.0.7.9` → `500000709`。
- 单调性：`build +1` 加 1，`patch +1` 加 100（大于 build 段最大增量 99），`minor +1` 加 100000，`major +1` 加 10000000，因此版本号按段递进时 versionCode 严格递增。
- 上限：脚本限制 `major <= 209`，保证结果小于 Android 上限 2100000000。
- ABI 区分：arm64 使用公式值，arm32 在公式值上加 1；`-PversionCodeOffset` 只用于本地测试包需要覆盖同版本旧安装的场景，正式发布不传。

## 禁止做法

- 不得添加或使用绝对覆盖 versionCode 的参数。历史上为车机调试手改成 `500002700`，导致后续按公式算出的版本低于它、无法覆盖安装；该覆盖入口已移除。
- 不得在 `build.gradle`、CI 脚本、清单文件或代码里硬编码 `versionCode` / `versionName`。
- 不得手改 `versionCode` 来绕过降级安装限制；需要覆盖测试安装时用 `-PversionCodeOffset`。

## 发版检查

- tag 去掉 `v` 前缀后必须与 `CURRENT_VERSION` 完全一致。
- `release-notes/<版本号>.md` 必须存在且内容有效。
- 两侧 `version.py` 版本一致、工作区无版本号相关的临时改动。
