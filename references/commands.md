# 编译、预览、合成与验证

要求 Python 3.9+、FFmpeg（libass/subtitles、libx264）、ffprobe 和中文字体。脚本仅依赖 Python 标准库。下载、ASR、OCR 为独立可选工具，按 recognition.md 选择，不由本脚本安装。

在任务目录执行，`SKILL_DIR` 指向本技能安装目录；JSON 格式见 cues-and-layout.md。

```sh
python3 "$SKILL_DIR/scripts/subtitle_pipeline.py" build work/reviewed-cues.json --out work/subtitles
python3 "$SKILL_DIR/scripts/subtitle_pipeline.py" render work/source.mp4 work/subtitles outputs/preview.png --start 12.5 --frame
python3 "$SKILL_DIR/scripts/subtitle_pipeline.py" render work/source.mp4 work/subtitles outputs/preview.mp4 --start 12 --duration 5 --audio aac
python3 "$SKILL_DIR/scripts/subtitle_pipeline.py" render work/source.mp4 work/subtitles outputs/final.mp4
python3 "$SKILL_DIR/scripts/subtitle_pipeline.py" verify work/source.mp4 outputs/final.mp4 --audio-copied --report work/media-check.json
```

预览截取会还原全片字幕时间，再重置输出时间，避免12秒的画面却显示0秒字幕。全片保持原声复制；若音轨不能装进MP4，明确使用 `--audio aac`，验证时不要加 `--audio-copied`。样片边界可能有音频包长度差，精确样片使用AAC转码。切勿用 `--start`/`--duration` 导出的预览冒充全片；verify 的时长检查只针对全片。

脚本拒绝覆盖已有视频，产物名改变即可重试；编译输出目录会更新同名ASS/SRT。暂存目录只包含本次字幕副本，渲染结束自动清理，不删除用户素材。路径通过参数传递，不执行用户输入的 shell 片段；字幕过滤器使用安全临时文件名，支持含空格、引号和非ASCII字符的输入路径。

默认使用通用软件编码器 libx264、CRF19，兼顾质量与体积。大视频可依据当前机器改用已经验证的硬件编码器，不应照搬固定5Mbps到所有画幅。MP4只选择第一路音轨；多音轨视频先检查哪一路是所需原声，有明确需求再调整映射。

## 视觉和内容验收

编译器的文本框估算不能替代 libass 实际渲染。逐条或分批渲染字幕到纯色画布，检测裁切与相交；再到真实成片确认背景对比度、原文避让、时序与可读时长。至少抽看开头/结尾、每个布局类型、最长句、场景切换和双字幕同时出现的帧。对重叠检查必须使用已识别的原文框，不能只检测新增中文字幕相互避让。

ASR/OCR 覆盖审阅和译文校对单独记录，不宣称“全片解码成功”等于“所有语义正确”。字符像素检测只证明某区域有像素，不是识别准确率指标。

## 测试

```sh
python3 -m unittest discover -s tests -v
```

测试使用自行生成的短片与虚构文本，不包含真实视频、账号信息或私人转写。运行时安装中文字体并设置 `SUBTITLE_TEST_FONT` 可指定字体；默认 macOS 为 Heiti SC，其他平台为 Noto Sans CJK SC。
