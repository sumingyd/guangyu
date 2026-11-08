package com.iptv.scanner.editor.pro.data

import android.util.Log
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.builtins.serializer
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

/**
 * IPTV 数据仓库：通过 Chaquopy 直调 [android_bridge.py] 中的 Python 入口函数。
 *
 * 设计要点：
 * 1. 单例（与 Python ServerContext 单例对应）
 * 2. 所有方法用 `withContext(Dispatchers.IO)` 包装（Chaquopy callAttr 是阻塞调用）
 * 3. 返回 `Result<T>`：成功返回数据，失败返回 Result.failure
 * 4. 错误处理：解析 `{"error": "..."}` 字段判断成功/失败
 * 5. 通用调用 [callPy] 包装：调用 callAttr → 拿 JSON 字符串 → 解析 error 字段
 *
 * 与 android_bridge.py 入口函数的对应关系：
 * - init_context / get_status_json / get_channels_json / get_channel_json / get_groups_json
 * - add_channel / update_channel / delete_channel / import_channels / get_m3u_text
 * - get_sources_json / add_source / delete_source / update_source / reload_sources / get_source_status_json
 * - get_epg_sources_json / add_epg_source / delete_epg_source / reload_epg / get_epg_status_json
 * - get_epg_json / get_epg_channels_json
 * - start_scan / stop_scan / get_scan_status_json / get_scan_results_json
 * - get_mappings_json / add_mapping / delete_mapping / refresh_mappings
 * - search_subtitles / download_subtitle / clear_cache
 */
class IptvRepository private constructor() {

    private val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    // -----------------------------------------------------------------
    // 通用调用包装
    // -----------------------------------------------------------------

    /**
     * 调用 Python 入口函数（无返回值解析），返回原始字符串。
     * 用于 init_context 这种返回 'OK'/'FAILED: ...' 的函数。
     */
    private suspend fun callPyRaw(funcName: String, vararg args: Any?): String =
        withContext(Dispatchers.IO) {
            try {
                val module = Python.getInstance().getModule("android_bridge")
                val pyArgs = args.map { it ?: "" }.toTypedArray()
                val result: PyObject = if (pyArgs.isEmpty()) {
                    module.callAttr(funcName)
                } else {
                    module.callAttr(funcName, *pyArgs)
                }
                result.toString()
            } catch (e: Throwable) {
                Log.e(TAG, "callPyRaw($funcName) failed", e)
                return@withContext "FAILED: ${e.message ?: "unknown"}"
            }
        }

    /**
     * 调用 Python 入口函数并解析 JSON。如果 JSON 包含 error 字段，返回 Result.failure。
     * 否则返回成功 JSON 字符串（去掉外层包装）。
     *
     * 注意：Python 端 _ok(data) 返回 json.dumps(data)，_err(msg) 返回 json.dumps({"error": msg})。
     * 所以成功响应的顶层可能是 object / array / string / number。
     * 只有 object 类型才检查 error 字段；array 等其他类型直接视为成功。
     */
    private suspend fun callPy(funcName: String, vararg args: Any?): Result<String> =
        withContext(Dispatchers.IO) {
            val raw = try {
                val module = Python.getInstance().getModule("android_bridge")
                val pyArgs = args.map { it ?: "" }.toTypedArray()
                val result: PyObject = if (pyArgs.isEmpty()) {
                    module.callAttr(funcName)
                } else {
                    module.callAttr(funcName, *pyArgs)
                }
                result.toString()
            } catch (e: Throwable) {
                Log.e(TAG, "callPy($funcName) failed", e)
                return@withContext Result.failure(e)
            }
            // 检查是否是错误响应
            try {
                val element = json.parseToJsonElement(raw)
                // 只有 JsonObject 才检查 error 字段；JsonArray 等直接视为成功
                if (element is JsonObject && element.containsKey("error")) {
                    val msg = element["error"]?.jsonPrimitive?.contentOrNull ?: "未知错误"
                    Log.w(TAG, "$funcName returned error: $msg")
                    Result.failure(IptvException(msg))
                } else {
                    Result.success(raw)
                }
            } catch (e: Throwable) {
                // 非 JSON 或解析失败
                Log.e(TAG, "$funcName response parse failed: $raw", e)
                Result.failure(IptvException("响应解析失败: ${e.message}"))
            }
        }

    /**
     * 调用并反序列化到指定类型。
     */
    private suspend inline fun <reified T> callPyTyped(
        funcName: String,
        vararg args: Any?
    ): Result<T> {
        val result = callPy(funcName, *args)
        return result.fold(
            onSuccess = { raw ->
                try {
                    Result.success(json.decodeFromString<T>(raw))
                } catch (e: Throwable) {
                    Log.e(TAG, "decode $funcName response failed: $raw", e)
                    Result.failure(IptvException("反序列化失败: ${e.message}"))
                }
            },
            onFailure = { Result.failure(it) }
        )
    }

    // -----------------------------------------------------------------
    // 初始化与状态
    // -----------------------------------------------------------------

    /** 初始化 Python 环境 + ServerContext 单例。返回 'OK' 或 'FAILED: ...' */
    suspend fun initContext(extFilesDir: String = "", filesDir: String = "", logLevel: String = "info", nativeLibDir: String = ""): Result<Unit> {
        val raw = callPyRaw("init_context", extFilesDir, filesDir, logLevel, nativeLibDir)
        return if (raw.startsWith("OK")) {
            Result.success(Unit)
        } else {
            Result.failure(IptvException(raw.removePrefix("FAILED:").trim()))
        }
    }

    /** 设置应用版本信息（供 Web 界面使用） */
    suspend fun setAppInfo(version: String, buildDate: String): Result<Unit> {
        val raw = callPyRaw("set_app_info", version, buildDate)
        return if (raw.startsWith("OK")) {
            Result.success(Unit)
        } else {
            Result.failure(IptvException(raw))
        }
    }

    /** 设置 Python 日志等级（debug/info/warn/error），影响 app.log 文件和 logcat 输出 */
    suspend fun setLogLevel(level: String): Result<Unit> {
        val raw = callPyRaw("set_log_level", level)
        return if (raw.startsWith("OK")) {
            Result.success(Unit)
        } else {
            Result.failure(IptvException(raw))
        }
    }

    suspend fun getStatus(): Result<IptvStatus> =
        callPyTyped("get_status_json")

    // -----------------------------------------------------------------
    // 频道查询
    // -----------------------------------------------------------------

    suspend fun getChannels(
        page: Int = 1,
        size: Int = 100,
        group: String = "",
        search: String = "",
        validFilter: String = ""
    ): Result<IptvChannelsPage> =
        callPyTyped("get_channels_json", page, size, group, search, validFilter)

    suspend fun getChannel(idx: Int): Result<IptvChannel> =
        callPyTyped("get_channel_json", idx)

    suspend fun getGroups(): Result<List<IptvGroup>> =
        callPyTyped("get_groups_json")

    // -----------------------------------------------------------------
    // 频道 CRUD
    // -----------------------------------------------------------------

    /** 添加频道，返回新频道的索引 */
    suspend fun addChannel(url: String, name: String, group: String = ""): Result<Int> {
        val result = callPyTyped<IdxResponse>("add_channel", url, name, group)
        return result.map { it.idx }
    }

    /** 更新频道字段。fields 是字段名到值的映射 */
    suspend fun updateChannel(idx: Int, fields: Map<String, String>): Result<Unit> {
        val jsonStr = toJsonObject(fields).toString()
        return callPyTyped<OkResponse>("update_channel", idx, jsonStr).map { Unit }
    }

    suspend fun deleteChannel(idx: Int): Result<Unit> =
        callPyTyped<OkResponse>("delete_channel", idx).map { Unit }

    /** 清空所有本地频道（source 为空的频道），返回清除数量 */
    suspend fun clearLocalChannels(): Result<Int> =
        callPyTyped<ClearedResponse>("clear_local_channels").map { it.cleared }

    /** 从 M3U 内容导入频道，返回导入数量和可选的 EPG URL（从 M3U 头部 x-tvg-url 提取） */
    suspend fun importChannels(content: String, name: String = ""): Result<Pair<Int, String>> {
        val result = callPyTyped<ImportedResponse>("import_channels", content, name)
        return result.map { it.imported to it.epgUrl }
    }

    /** 生成 M3U 文本（用于导出/分享）。返回 M3U 文本和频道数量 */
    suspend fun getM3uText(
        group: String = "",
        validOnly: Boolean = false,
        search: String = ""
    ): Result<M3uTextResponse> =
        callPyTyped("get_m3u_text", group, validOnly, search)

    // -----------------------------------------------------------------
    // 订阅源管理
    // -----------------------------------------------------------------

    suspend fun getSources(): Result<List<IptvSource>> =
        callPyTyped("get_sources_json")

    suspend fun addSource(url: String, name: String = ""): Result<Int> {
        val result = callPyTyped<CountResponse>("add_source", url, name)
        return result.map { it.count }
    }

    suspend fun deleteSource(idx: Int): Result<Int> {
        val result = callPyTyped<CountResponse>("delete_source", idx)
        return result.map { it.count }
    }

    suspend fun updateSource(idx: Int, fields: Map<String, String>): Result<Unit> {
        val jsonStr = toJsonObject(fields).toString()
        return callPyTyped<OkResponse>("update_source", idx, jsonStr).map { Unit }
    }

    /** 触发订阅源重载（异步）。url 为空则加载所有已配置源。返回是否成功启动 */
    suspend fun reloadSources(url: String = ""): Result<Boolean> =
        callPyTyped<StartedResponse>("reload_sources", url).map { it.started }

    // -----------------------------------------------------------------
    // 备份与恢复
    // -----------------------------------------------------------------

    /**
     * 导出所有可备份的配置（订阅源 + EPG 源）为 JSON 字符串。
     * 用于写入外部存储文件，卸载重装后可恢复。
     */
    suspend fun exportConfig(): Result<String> =
        callPy("export_config")

    /**
     * 从 JSON 字符串恢复配置（订阅源 + EPG 源），并触发 reload。
     * 内部会调用 reload_sources / reload_epg 加载频道和 EPG。
     */
    suspend fun importConfig(json: String): Result<Unit> =
        callPyTyped<OkResponse>("import_config", json).map { Unit }

    suspend fun getSourceStatus(): Result<IptvSourceStatus> =
        callPyTyped("get_source_status_json")

    // -----------------------------------------------------------------
    // EPG 订阅源
    // -----------------------------------------------------------------

    suspend fun getEpgSources(): Result<List<IptvEpgSource>> =
        callPyTyped("get_epg_sources_json")

    suspend fun addEpgSource(url: String, name: String = ""): Result<Int> {
        val result = callPyTyped<CountResponse>("add_epg_source", url, name)
        return result.map { it.count }
    }

    suspend fun deleteEpgSource(idx: Int): Result<Int> {
        val result = callPyTyped<CountResponse>("delete_epg_source", idx)
        return result.map { it.count }
    }

    suspend fun updateEpgSource(idx: Int, fields: Map<String, String>): Result<Unit> {
        val jsonStr = toJsonObject(fields).toString()
        return callPyTyped<OkResponse>("update_epg_source", idx, jsonStr).map { Unit }
    }

    suspend fun reloadEpg(): Result<Boolean> =
        callPyTyped<StartedResponse>("reload_epg").map { it.started }

    suspend fun getEpgStatus(): Result<IptvEpgStatus> =
        callPyTyped("get_epg_status_json")

    // -----------------------------------------------------------------
    // EPG 节目单
    // -----------------------------------------------------------------

    /**
     * 获取指定频道的节目单。
     * 匹配优先级：tvgName > tvgId > commaName > channelName。
     */
    suspend fun getEpg(
        channelName: String = "",
        tvgId: String = "",
        tvgName: String = "",
        commaName: String = ""
    ): Result<IptvEpgList> =
        callPyTyped("get_epg_json", channelName, tvgId, tvgName, commaName)

    /** 获取所有有 EPG 数据的频道 ID 列表 */
    suspend fun getEpgChannels(): Result<List<String>> {
        // get_epg_channels_json 返回 {"channels": [...]}
        val result = callPyTyped<JsonObject>("get_epg_channels_json")
        return result.fold(
            onSuccess = { obj ->
                try {
                    val channels = obj["channels"]?.jsonArray?.map { it.jsonPrimitive.content } ?: emptyList()
                    Result.success(channels)
                } catch (e: Throwable) {
                    Result.failure(e)
                }
            },
            onFailure = { Result.failure(it) }
        )
    }

    // -----------------------------------------------------------------
    // 扫描
    // -----------------------------------------------------------------

    /**
     * 启动 URL 范围扫描（异步）。baseUrl 支持 [1-255] 范围表达式。
     * @param engine 扫描引擎 ("requests" / "ffprobe" / "mpv")
     * @param retry 是否启用智能重试
     * @param append 是否追加模式
     */
    suspend fun startScan(
        baseUrl: String, timeout: Int = 10, threads: Int = 4,
        engine: String = "requests", retry: Boolean = false, append: Boolean = false
    ): Result<Boolean> =
        callPyTyped<StartedResponse>("start_scan", baseUrl, timeout, threads, engine, retry, append)
            .map { it.started }

    suspend fun stopScan(): Result<Unit> =
        callPyTyped<OkResponse>("stop_scan").map { Unit }

    suspend fun getScanStatus(): Result<ScanStatus> =
        callPyTyped("get_scan_status_json")

    suspend fun getScanResults(): Result<List<ScanResult>> =
        callPyTyped("get_scan_results_json")

    /** 启动频道网络验证 */
    suspend fun startValidate(timeout: Int = 10, threads: Int = 4): Result<Boolean> =
        callPyTyped<StartedResponse>("start_validate", timeout, threads).map { it.started }

    // -----------------------------------------------------------------
    // 频道映射
    // -----------------------------------------------------------------

    suspend fun getMappings(): Result<List<MappingEntry>> =
        callPyTyped("get_mappings_json")

    suspend fun addMapping(
        rawName: String,
        standardName: String,
        logoUrl: String = "",
        groupName: String = ""
    ): Result<Unit> =
        callPyTyped<OkResponse>("add_mapping", rawName, standardName, logoUrl, groupName).map { Unit }

    /**
     * 删除映射。
     * - 只传 standardName：删除该 standardName 下所有 rawName
     * - 同时传 standardName 和 rawName：删除单条
     */
    suspend fun deleteMapping(standardName: String, rawName: String = ""): Result<Unit> =
        callPyTyped<OkResponse>("delete_mapping", standardName, rawName).map { Unit }

    /** 刷新远程映射缓存（同步阻塞） */
    suspend fun refreshMappings(): Result<Unit> =
        callPyTyped<OkResponse>("refresh_mappings").map { Unit }

    // -----------------------------------------------------------------
    // 局域网管理服务器（TV 端遥控器输入不便，手机浏览器扫码管理）
    // -----------------------------------------------------------------

    /** 启动 HTTP 管理服务器，返回局域网 URL */
    suspend fun startAdminServer(port: Int = 8080): Result<AdminServerInfo> =
        callPyTyped("start_admin_server", port)

    /** 设置自定义访问令牌（空字符串清除自定义令牌，改为自动生成） */
    suspend fun setAdminToken(token: String): Result<TokenResponse> =
        callPyTyped("set_admin_token", token)

    /** 停止 HTTP 管理服务器 */
    suspend fun stopAdminServer(): Result<OkResponse> =
        callPyTyped("stop_admin_server")

    /** 查询管理服务器状态和 URL */
    suspend fun getAdminUrl(): Result<AdminServerInfo> =
        callPyTyped("get_admin_url")

    /** 轮询虚拟遥控器命令（从 admin 页面发送的遥控指令） */
    suspend fun pollRemoteCommand(): Result<RemoteCommandResponse> =
        callPyTyped("poll_remote_command")

    /** 上报当前播放状态到 admin 服务器（供遥控器页面显示） */
    suspend fun setPlayerStatus(statusJson: String): Result<Unit> {
        return callPy("set_player_status", statusJson).map { }
    }

    // -----------------------------------------------------------------
    // 每文件播放设置持久化（#24）
    // -----------------------------------------------------------------

    /** 读取指定 URL 的播放设置 */
    suspend fun loadPlaybackSettings(url: String): Result<PlaybackSettingsResponse> =
        callPyTyped("load_playback_settings", url)

    /** 保存指定 URL 的播放设置 */
    suspend fun savePlaybackSettings(url: String, settingsJson: String, name: String = ""): Result<Unit> =
        callPyTyped<OkResponse>("save_playback_settings", url, settingsJson, name).map { Unit }

    // -----------------------------------------------------------------
    // 字幕
    // -----------------------------------------------------------------

    suspend fun searchSubtitles(
        query: String = "",
        imdbId: String = "",
        language: String = "all",
        filePath: String = ""
    ): Result<SubtitleSearchResponse> =
        callPyTyped("search_subtitles", query, imdbId, language, filePath)

    /** 下载字幕到指定目录，返回字幕文件路径 */
    suspend fun downloadSubtitle(
        downloadLink: String,
        destDir: String,
        fileName: String = "",
        language: String = ""
    ): Result<String> =
        callPyTyped<PathResponse>("download_subtitle", downloadLink, destDir, fileName, language)
            .map { it.path }

    // -----------------------------------------------------------------
    // 缓存
    // -----------------------------------------------------------------

    /** 清空缓存。cacheType: "all"/"logo"/"epg"/"thumbnails"/"subtitle"。返回删除数量 */
    suspend fun clearCache(cacheType: String = "all"): Result<Int> =
        callPyTyped<ClearCacheResponse>("clear_cache", cacheType).map { it.deletedCount }

    /** 批量获取频道缩略图文件路径。返回 url -> file_path 映射 */
    suspend fun getThumbnailPaths(urls: List<String>): Result<Map<String, String>> {
        val json = JsonArray(urls.map { JsonPrimitive(it) }).toString()
        return callPyTyped<ThumbnailPathsResponse>("get_thumbnail_paths", json).map { it.paths }
    }

    /** 保存截图文件作为频道缩略图 */
    suspend fun captureThumbnail(url: String, filePath: String): Result<Unit> =
        callPy("capture_thumbnail", url, filePath).map { }

    /** 后台生成缩略图（Python 端用独立 libmpv handle 截帧，不影响前台播放器）。返回缩略图路径 */
    suspend fun generateThumbnailBg(url: String): Result<GenerateThumbnailBgResponse> =
        callPyTyped("generate_thumbnail_bg", url)

    // -----------------------------------------------------------------
    // 内部工具
    // -----------------------------------------------------------------

    /** 把 Map<String, String> 转为 JsonObject（用于 update_channel / update_source） */
    private fun toJsonObject(fields: Map<String, String>): JsonObject =
        buildJsonObject {
            fields.forEach { (k, v) -> put(k, JsonPrimitive(v)) }
        }

    companion object {
        private const val TAG = "IptvRepository"

        @Volatile
        private var INSTANCE: IptvRepository? = null

        fun getInstance(): IptvRepository =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: IptvRepository().also { INSTANCE = it }
            }
    }
}

/** IPTV 业务异常，携带 Python 端返回的错误消息 */
class IptvException(message: String) : Exception(message)
