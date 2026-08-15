# 下载文件封面兜底机制设计

## 目标

当源站没有封面，或源封面下载/嵌入失败时，为支持封面的音频文件和项目输出的 MP4 视频随机嵌入一张内置兜底图片，避免最终媒体文件无封面。源封面始终优先且不得被覆盖。

## 已确认范围

- 音频：MP3、FLAC、M4A/MP4、OGG 和 Opus 等当前容器支持封面的输出。
- 视频：项目统一输出的 MP4。
- 不支持当前封面写入流程的 WAV 和 WebM 保持原样，不为封面而转码或转封装。
- 每次下载、重试或重新下载都独立随机选择；同一内容的不同下载结果可以使用不同兜底图。
- 封面嵌入失败只记录警告，不把已经成功下载的媒体判定为下载失败。

## 资源

用户提供的 6 张方形原图将原样移动到 `assets/fallback_covers/`，仅统一文件名，不重新压缩、不生成变体：

| 目标文件 | 原文件 | 格式 | 尺寸 |
| --- | --- | --- | --- |
| `cover-01.png` | `10319268-6284-4932-B124-441356EBC322.PNG` | PNG | 1254×1254 |
| `cover-02.jpg` | `80FE2ECE-7AF4-4A1A-A1A4-603804CA2159.jpg` | JPEG | 941×941 |
| `cover-03.jpg` | `9CFB3921-A973-440F-B6F7-A087A14D36B1.jpg` | JPEG | 852×852 |
| `cover-04.png` | `B5CCBC21-C283-4890-A1C8-74B4B299BC5C.PNG` | PNG | 1254×1254 |
| `cover-05.png` | `F6FC1CB9-493C-48F0-A794-320A471277E7.PNG` | PNG | 1254×1254 |
| `cover-06.jpg` | `IMG_9655.jpg` | JPEG | 1080×1080 |

## 架构

新增独立模块 `media_cover.py`，负责且仅负责最终文件的封面状态：

```python
@dataclass(frozen=True)
class CoverOutcome:
    embedded: bool
    source: Literal["source", "fallback", "none"]
    fallback_name: str | None = None

def ensure_media_cover(
    filepath: Path,
    *,
    chooser: Callable[[Sequence[Path]], Path] = secrets.choice,
) -> CoverOutcome:
    ...
```

流程：

1. 根据最终扩展名判断容器是否受支持；不支持则返回 `none`。
2. 使用 Mutagen 检查最终文件是否已经包含封面。存在时返回 `source`，不调用随机选择器，也不改写文件。
3. 没有封面时，从 6 张资源中调用一次 `chooser`，将图片写入对应容器并重新检查。
4. 写入成功返回 `fallback`；资源缺失、文件损坏或写入失败时记录警告并返回 `none`。

封面检测与写入按容器实现：

- MP3：ID3 `APIC`。
- FLAC：picture block。
- M4A/MP4 视频：MPEG-4 `covr`，由 Mutagen 写入，不重编码音视频流。
- OGG/Opus：`METADATA_BLOCK_PICTURE`。

## yt-dlp 集成

- 音频继续使用现有 `writethumbnail` 和 `EmbedThumbnail`，源封面路径不变。
- YouTube、Instagram、Bilibili 视频增加 `writethumbnail=True` 和 `EmbedThumbnail`，使可获取的源封面优先写入最终 MP4。
- `EmbedThumbnail` 必须位于视频合并/重封装之后。
- 所有下载路径继续汇聚到 `_finalize_download_output()`；文件完成命名后调用 `ensure_media_cover()`，并将结果写入下载结果：
  - `cover_embedded`: 最终文件实际是否包含封面；
  - `cover_source`: `source`、`fallback` 或 `none`；
  - `fallback_cover`: 使用兜底时为资源文件名，否则为 `None`。

该设计不依赖 yt-dlp 的私有后处理队列。即使源封面元数据存在但实际下载或嵌入失败，最终文件检查仍能触发兜底。

## 并发与随机性

- 使用 `secrets.choice()` 每次独立选择，适用于当前多线程下载队列，不维护共享可变随机状态。
- 测试通过注入 `chooser` 固定选择或返回不同图片，生产环境不暴露用户配置。
- 重试和重新下载会重新执行最终封面检查；新生成且无源封面的文件会重新随机。

## 错误处理

- 已有源封面永不覆盖。
- 图片资源目录为空、指定资源不存在、Mutagen 无法解析媒体或写入失败时，记录包含文件路径和原因的警告。
- 封面失败不删除、不回滚、不重编码媒体文件；下载任务仍按媒体下载结果完成。
- 不把内置兜底图片复制到下载目录，也不产生同名 JPG sidecar。

## 测试与验收

- 资源合同：目录恰好包含 6 张有效 PNG/JPEG，重命名前后 SHA-256 不变。
- 单元合同：支持扩展名、随机选择器每次调用、已有封面不覆盖、失败返回 `none`、WAV/WebM 不调用选择器。
- 真实容器集成：用临时短媒体验证 MP3、FLAC、M4A 和 MP4 的实际写入与再次检测；MP4 写入前后视频/音频流编码保持不变。
- yt-dlp 配置：三平台视频均下载源缩略图，并在合并/重封装后嵌入。
- 下载路径：普通下载、Bilibili 标准/极速回退、重试和重新下载均返回实际 `cover_source`。
- 完整回归：全量 unittest、compileall、下载文件清单比较；不修改既有 `downloads/` 文件。
