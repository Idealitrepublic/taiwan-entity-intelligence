# Report font

`NotoSansTC-Regular.ttf` is a static weight-400 instance of Google Fonts'
Noto Sans TC TrueType font. It is distributed under the adjacent SIL Open Font
License and embedded/subset into PDF reports, so viewers do not require local
Chinese fonts or network access.

Official upstream: https://github.com/google/fonts/tree/main/ofl/notosanstc
Source file: `NotoSansTC[wght].ttf`.
The checked-in font is a deployment asset, not a remotely fetched runtime resource.

SHA-256 of original variable TTF:
`864727d210d54f2537bbe23b3a839436c3992af72de9322af5270897246bd44f`.
SHA-256 of the checked-in static instance:
`721137c83733b9ed7d7a54c11947c31bd2d3741a95f17353213ba83d29eac0bc`.
Build-time conversion used fonttools 4.61.1, weight 400; fonttools is not a runtime
dependency. No glyph subset was removed from this deployment asset.
