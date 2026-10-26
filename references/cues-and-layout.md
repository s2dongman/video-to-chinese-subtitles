# 字幕数据与布局

`scripts/subtitle_pipeline.py build` 接收 UTF-8 JSON；时间为全片秒，坐标为源视频经旋转后的显示像素，左上角为原点。脚本只编译已经校对的译文，不自动做 ASR、OCR 或翻译。

```json
{
  "width": 1920,
  "height": 1080,
  "bottom_padding": 144,
  "font": "Heiti SC",
  "voice_size": 45,
  "screen_size": 46,
  "cues": [
    {"id":"s1", "kind":"screen", "start":1, "end":4,
     "source":"A quiet morning", "language":"en", "zh":"安静的早晨",
     "original_box":[400,950,1520,1010]},
    {"id":"v1", "kind":"voice", "start":1.2, "end":3.8,
     "source":"It's beautiful here.", "language":"en", "zh":"这里真美。",
     "x":960, "y":1048}
  ]
}
```

- `kind`: `voice` 或 `screen`；`id` 必须唯一。`original_box` 是 `[left,top,right,bottom]`，必须在原画面范围内。
- `zh` 支持真实换行。反斜杠、ASS 控制字符大括号会规范化，避免将文本意外解释为格式控制。
- 默认字号根据源画面高度 / 1080 缩放。`voice_size`/`screen_size` 是1080基准字号；每条的可选 `font_size` 是最终像素字号。
- `screen` 用底部居中锚点，默认在 `original_box` 上方留26/1080画面高的间距；若无框，必须提供 `x,y`。`voice` 为中心锚点，默认 y=1048/1080×源高。`x,y` 可逐条覆盖。
- `bottom_padding` 只控制新增黑边高度；源片已有黑边时设0，并按实际有效画面区域设置每条坐标。总高度需为偶数。
- 编译器检查大致文本宽高、边界和已知原文框相交；这是保守估算，不是字体渲染测量。拒绝时通过换行、位置或字号修复，不以关闭检查替代处理。屏幕译文在同一时间有不同位置时允许共存，但仍检查框相交；语音默认不允许时间重叠。
- 原文框必须覆盖所有会被新增译文遮挡的画面文字，不仅额外说明。顶端标题、贴底对白、竖屏均应逐场景布局。估算通过后仍需用实际字体渲染确认。

同时出现的原文、两种译文框不能相交。空间不足先让长句换行、选择空白位置；贴底原文下方没有空间时将语音字幕放入新增底栏。保证可读与不重叠，不能机械保留1048坐标。
