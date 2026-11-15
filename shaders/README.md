# MPV 用户着色器目录

本目录存放 GLSL 着色器文件（`.glsl` / `.hook`），供 MPV 播放器加载使用。

## 内置着色器

以下着色器已内置，开箱即用，无需额外下载：

| 预设名      | 说明                          | 文件名                         | 大小    | 许可证     |
|------------|------------------------------|-------------------------------|---------|-----------|
| `ravu`     | RAVU 锐利放大（r3 版本）      | `ravu_r3.hook`                | 123 KB  | LGPL-3.0+ |
| `fsrcnnx`  | FSRCNNX 超分辨率（8-0-4-1）   | `FSRCNNX_x2_8-0-4-1.glsl`    | 71 KB   | LGPL-3.0+ |
| `anime4k`  | Anime4K 动画增强（3文件组合）  | `Anime4K_Clamp_Highlights.glsl` | 2.8 KB | MIT       |
|            |                              | `Anime4K_Restore_CNN_S.glsl`  | 17 KB   | MIT       |
|            |                              | `Anime4K_Upscale_CNN_x2_S.glsl` | 19 KB | MIT       |
| `krig`     | KrigBilateral 色度升频        | `KrigBilateral.hook`          | 12 KB   | LGPL-3.0+ |
| `ssim`     | SSimDownscaler 高质量降频     | `SSimDownscaler.glsl`         | 5.7 KB  | LGPL-3.0+ |

## 着色器来源

- **RAVU** — [bjin/mpv-prescalers](https://github.com/bjin/mpv-prescalers) (LGPL-3.0+)
- **FSRCNNX** — [igv/FSRCNN-TensorFlow](https://github.com/igv/FSRCNN-TensorFlow) (LGPL-3.0+)
- **Anime4K** — [bloc97/Anime4K](https://github.com/bloc97/Anime4K) (MIT)
- **KrigBilateral** — [igv gist](https://gist.github.com/igv/a015fc885d5c22e6891820ad89555637) (LGPL-3.0+)
- **SSimDownscaler** — [igv gist](https://gist.github.com/igv/36508af3ffc84410fe39761d6969be10) (LGPL-3.0+)

## 额外文件

以下文件也包含在内，但不在预设列表中，可手动使用：

| 文件名                     | 说明                    |
|---------------------------|------------------------|
| `ravu_r4.hook`            | RAVU r4 版本（更高质量） |
| `Anime4K_Restore_CNN_M.glsl` | Anime4K 中等质量恢复   |
| `adaptive_sharpen.glsl`   | 自适应锐化着色器        |

## 添加自定义着色器

1. 下载 `.glsl` 或 `.hook` 着色器文件
2. 放入本目录
3. 在视频调整对话框的着色器下拉框中选择该文件

## 注意事项

- 着色器在 GPU 渲染管线运行，不需要 copy-back 硬件解码
- 多个着色器可通过 MPV 的 `glsl-shaders` 属性用逗号分隔加载
- 着色器性能取决于 GPU，低端 GPU 可能导致帧率下降
- Android 端着色器文件在应用启动时自动从 assets 复制到 `filesDir/shaders/`
