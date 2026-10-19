# 字段白名单与映射

以 `scripts/media_metainfo.py` 的 `FIELDS` 为执行白名单。未列出的字段，包括任意EXIF技术标签，拒绝写入或删除。JSON键名区分大小写。所有用户文本按字面值传给工具，不作为命令执行。

| JSON字段 | 类型 | ExifTool字段 |
|---|---|---|
| title | 字符串 | XMP-dc:Title |
| description | 字符串 | XMP-dc:Description |
| creator | 字符串数组 | XMP-dc:Creator |
| editor | 字符串 | XMP-photoshop:CaptionWriter |
| contributors | 字符串数组 | XMP-dc:Contributor |
| keywords | 字符串数组 | XMP-dc:Subject |
| source_url | HTTP(S)网址 | XMP-dc:Source |
| original_image_url | HTTP(S)网址 | XMP-jkmedia:OriginalImageURL |
| reference_urls | HTTP(S)网址数组 | XMP-jkmedia:ReferenceURLs |
| creator_url | HTTP(S)网址 | XMP-iptcCore:CreatorWorkURL |
| license_url | HTTP(S)网址 | XMP-xmpRights:WebStatement |
| usage_terms | 字符串 | XMP-xmpRights:UsageTerms |
| rights | 字符串 | XMP-dc:Rights |
| credit | 字符串 | XMP-photoshop:Credit |
| project | 字符串 | XMP-jkmedia:Project |
| series | 字符串 | XMP-jkmedia:Series |
| asset_id | 字符串 | XMP-jkmedia:AssetID |
| page | 字符串 | XMP-jkmedia:Page |
| version | 字符串 | XMP-jkmedia:Version |
| rating | 整数-1到5 | XMP-xmp:Rating |
| content_kind | 内容类别枚举 | XMP-jkmedia:ContentKind |
| people_scope | 人物范围枚举 | XMP-jkmedia:PeopleScope |
| ai_note | 字符串 | XMP-jkmedia:AINote |
| fictional_characters | 字符串数组 | XMP-jkmedia:FictionalCharacters |
| source_credits | 字符串 | XMP-jkmedia:SourceCredits |
| depicted_real_people | 字符串数组，仅实拍真人 | XMP-iptcExt:PersonInImage |
| photographer | 字符串，仅真实拍摄，含风景实拍 | XMP-jkmedia:Photographer |

`creator` 指本作品创作者，`source_credits` 指参考照片、插画、音乐等来源的署名与许可；不要把参考照片作者声明为AI合成画面的实拍摄影师。`depicted_real_people` 用于真实拍摄的人物，不记录AI模拟演员的身份；选角、虚构角色、历史人物想象使用描述和 `fictional_characters`。

`source_url` 保存来源页面，`original_image_url` 保存原图文件网址。微信media_id等平台回执放外部台账。不要把临时签名下载链接、带密码或token的网址写入可分发文件。

## 仅允许清理的真人细节与授权字段

以下字段只能在 `remove` 中出现，不能添加或赋值：

- `model_release_id` → XMP-plus:ModelReleaseID
- `model_release_status` → XMP-plus:ModelReleaseStatus
- `person_details` → XMP-iptcExt:PersonInImageWDetails

程序不签发授权证明；不把AI人物当作已签署模特授权的真人。其他命名空间中的同类信息可能需要人工核对；预检不能声称覆盖所有厂商扩展。

## 列表、空值与原有信息

- `set` 对列表是替换整个目标字段，不是追加；填写想保留的完整列表。
- `remove` 明确删除目标字段，禁止 `all`、通配符或原始工具参数。
- 空字符串、空数组和null不表示删除，会被拒绝。
- 未指定字段保留。发现与内容分类冲突的原字段时，计划会阻断，需明确列出清理项。
- 首版不编辑多语言lang-alt子项；若ExifTool触及非目标语言版本，保护核验将拒绝结果。

MKV以保留原有标签的方式维护一个全局 `JK_METAINFO` JSON标签；这些信息不保证出现在每个播放器的常规“属性”面板中。读取时由本脚本还原上述统一字段。旁车记录不改变媒体内原有字段。
