package com.iptv.scanner.editor.pro.data

import android.util.Log
import java.util.Collections
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.launch

/**
 * 台标来源回退事件总线。
 *
 * Python 端记录失败并重新解析后，把受影响频道的 {index, logo} 发到这里，
 * ViewModel 收到后直接替换内存里的频道台标，Compose 自动重组显示下一级来源。
 */
object LogoFallbackBus {
    private val _updates = MutableSharedFlow<List<LogoUpdate>>(extraBufferCapacity = 32)
    val updates = _updates.asSharedFlow()

    fun publish(items: List<LogoUpdate>) {
        if (items.isNotEmpty()) _updates.tryEmit(items)
    }
}

/**
 * 图片加载失败上报器（Coil EventListener 调用）。
 *
 * 失败往往成批出现（规则地址 404），这里做 300ms 合并 + 去重，
 * 一次调用把一批地址交给 Python，避免每个失败图片都跨桥查询全部频道。
 */
object LogoFailureReporter {
    private const val TAG = "LogoFailureReporter"
    private const val MERGE_WINDOW_MS = 300L

    private val pending: MutableSet<String> = Collections.synchronizedSet(LinkedHashSet())
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var job: Job? = null

    fun report(url: String) {
        val value = url.trim()
        if (value.isEmpty()) return
        if (!(value.startsWith("http://") || value.startsWith("https://") ||
                value.startsWith("file://") || value.startsWith("/"))) {
            return
        }
        pending.add(value)
        synchronized(this) {
            if (job?.isActive == true) return
            job = scope.launch {
                delay(MERGE_WINDOW_MS)
                val batch = synchronized(pending) {
                    pending.toList().also { pending.clear() }
                }
                if (batch.isEmpty()) return@launch
                IptvRepository.getInstance().reportLogoFailures(batch).fold(
                    onSuccess = { LogoFallbackBus.publish(it) },
                    onFailure = { Log.d(TAG, "report logo failures failed: ${it.message}") },
                )
            }
        }
    }
}
