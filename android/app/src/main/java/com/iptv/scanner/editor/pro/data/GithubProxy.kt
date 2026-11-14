package com.iptv.scanner.editor.pro.data

import java.net.URI

/**
 * GitHub 加速代理 URL 改写（与 Python 端 utils/github_proxy.py 保持同一套规则）。
 *
 * 只改写 GitHub 相关域名，其余地址（用户自己的订阅源、EPG 源、播放地址）保持原样。
 */
object GithubProxy {

    const val DEFAULT_PROXY = "gh-proxy.com"

    /** 与 Python 端 utils/github_proxy.PROXY_LIST 保持一致；Python 不可用时作为兜底展示 */
    val PROXY_LIST = listOf(
        "github.chenc.dev",
        "github.xxlab.tech",
        "gh-proxy.com",
        "ghfast.top",
        "gh.sixyin.com",
        "cdn.gh-proxy.com",
        "gh.noki.icu",
        "ghproxy.monkeyray.net",
        "cdn.akaere.online",
        "ghfile.geekertao.top",
        "gh.jiji.gv.uy",
        "ghproxy.net",
        "down.mxw.xx.kg",
        "gh.beimengvv.xyz",
        "ghp.keleyaa.com",
        "github.tbap.top",
        "github.ednovas.xyz",
        "gh.dpik.top",
        "gh.idayer.com",
        "cfgh.ikgy.top",
        "proxy.yaoyaoling.net",
        "git.yylx.win",
        "777.z321.cc.cd",
        "gh.acmsz.top",
        "gg.z321.cc.cd",
    )

    private val GITHUB_HOSTS = setOf(
        "github.com",
        "githubusercontent.com",
        "raw.githubusercontent.com",
        "gist.githubusercontent.com",
        "objects.githubusercontent.com",
        "codeload.github.com",
    )

    /** 是否属于需要走加速代理的 GitHub 域名 */
    fun isGithubUrl(url: String): Boolean {
        val host = hostOf(url) ?: return false
        if (host in GITHUB_HOSTS) return true
        return host.endsWith(".github.com") || host.endsWith(".githubusercontent.com")
    }

    /** 按开关与代理域名改写 URL；非 GitHub 地址或未启用时原样返回 */
    fun rewrite(url: String, enabled: Boolean, proxy: String): String {
        if (!enabled || url.isBlank()) return url
        if (!isGithubUrl(url)) return url
        val host = normalizeProxy(proxy)
        if (hostOf(url) == host) return url
        return "https://$host/$url"
    }

    private fun normalizeProxy(proxy: String): String {
        val trimmed = proxy.trim().lowercase()
            .removePrefix("https://")
            .removePrefix("http://")
            .trimEnd('/')
        return trimmed.ifBlank { DEFAULT_PROXY }
    }

    private fun hostOf(url: String): String? {
        return try {
            val parsed = URI(url.trim())
            val scheme = parsed.scheme?.lowercase()
            if (scheme != "http" && scheme != "https") return null
            parsed.host?.lowercase()?.trimEnd('.')
        } catch (e: Exception) {
            null
        }
    }
}

/**
 * 进程内共享的当前代理配置，供 Coil 台标加载等非 ViewModel 场景读取。
 * 由 AppViewModel 在启动/保存设置时同步更新；未加载前按默认（开启 + 默认代理）。
 */
object GithubProxyRuntime {
    @Volatile
    var enabled: Boolean = true

    @Volatile
    var proxy: String = GithubProxy.DEFAULT_PROXY
}
