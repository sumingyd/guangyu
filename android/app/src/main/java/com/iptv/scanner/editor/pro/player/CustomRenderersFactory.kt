package com.iptv.scanner.editor.pro.player

import android.content.Context
import android.os.Handler
import androidx.media3.common.MimeTypes
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.Renderer
import androidx.media3.exoplayer.audio.AudioRendererEventListener
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioOffloadSupportProvider
import androidx.media3.exoplayer.audio.DefaultAudioSink
import androidx.media3.exoplayer.audio.DefaultAudioTrackBufferSizeProvider
import androidx.media3.exoplayer.mediacodec.MediaCodecSelector
import androidx.media3.exoplayer.mediacodec.MediaCodecUtil

/**
 * ExoPlayer 渲染器工厂。
 *
 * 在 media3 默认渲染器之外补两处直播场景需要的定制：
 * 1. MP2 音频渲染器：系统没有 MP2 解码器时才注册（直播源 MP2/AC3 音轨常见）。
 *    之前为了排查「播放时钟卡死」临时注释掉了，现已确认 Mp2Decoder 的时钟问题已修复，
 *    改为按设备能力条件恢复，避免和系统解码器重复。
 * 2. 音频输出缓冲：加大 PCM / passthrough / offload 的 AudioTrack 缓冲，
 *    吸收直播抖动，缓解 1080 直播音画不同步（欠载）问题。
 *    offload（音频直通）仍交给 DefaultAudioOffloadSupportProvider 按设备能力判定。
 */
class CustomRenderersFactory(
    context: Context,
    /** 是否允许注册自带 MP2 渲染器（仍会再检查系统是否有 MP2 解码器） */
    private val enableMp2Renderer: Boolean = true
) : DefaultRenderersFactory(context) {

    override fun buildAudioRenderers(
        context: Context,
        extensionRendererMode: Int,
        mediaCodecSelector: MediaCodecSelector,
        enableFloatOutput: Boolean,
        audioSink: AudioSink,
        eventHandler: Handler,
        eventListener: AudioRendererEventListener,
        out: ArrayList<Renderer>
    ) {
        super.buildAudioRenderers(
            context, extensionRendererMode, mediaCodecSelector,
            enableFloatOutput, audioSink, eventHandler, eventListener, out
        )
        if (enableMp2Renderer && !hasSystemMp2Decoder()) {
            out.add(Mp2AudioRenderer(context, eventHandler, eventListener, audioSink))
            android.util.Log.i("CustomRenderersFactory", "MP2 renderer registered (no system MP2 decoder)")
        } else {
            android.util.Log.i("CustomRenderersFactory", "MP2 renderer skipped (system decoder available or disabled)")
        }
    }

    override fun buildAudioSink(
        context: Context,
        enableFloatOutput: Boolean,
        enableAudioTrackPlaybackParams: Boolean
    ): AudioSink {
        return DefaultAudioSink.Builder(context)
            .setEnableFloatOutput(enableFloatOutput)
            .setEnableAudioTrackPlaybackParams(enableAudioTrackPlaybackParams)
            .setAudioTrackBufferSizeProvider(
                DefaultAudioTrackBufferSizeProvider.Builder()
                    // 2.5s 上限能吸收直播码率抖动；下限 200ms 保证切换/seek 后不会欠载
                    .setMinPcmBufferDurationUs(200_000)
                    .setMaxPcmBufferDurationUs(750_000)
                    .setPcmBufferMultiplicationFactor(4)
                    .setPassthroughBufferDurationUs(1_000_000)
                    .setOffloadBufferDurationUs(1_500_000)
                    .build()
            )
            // 直通（offload）按设备能力开：不支持的设备自动回落 PCM
            .setAudioOffloadSupportProvider(DefaultAudioOffloadSupportProvider(context))
            .build()
    }

    private fun hasSystemMp2Decoder(): Boolean = try {
        MediaCodecUtil.getDecoderInfos(MimeTypes.AUDIO_MPEG_L2, false, false).isNotEmpty()
    } catch (_: Exception) {
        false
    }
}
