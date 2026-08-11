#!/usr/bin/env python3
"""
YouTube、Instagram 与 Bilibili 视频批量下载工具 — 命令行入口。

同一批任务可以混合包含 YouTube、Instagram 和 Bilibili 链接。程序会自动识别平台，
并为不同平台选择对应的 yt-dlp 下载参数。

核心下载逻辑位于 downloader.py，本文件仅保留命令行交互与结果展示。
"""

import re
import sys
from pathlib import Path
from typing import Optional

from collection_resolver import (
    CollectionEntry,
    CollectionPreview,
    resolve_collection,
)
from download_errors import DownloadFailure, format_cli_error
from downloader import (
    AUDIO,
    AUDIO_FORMATS,
    DOWNLOADS_DIR,
    FLAC,
    MP3,
    PLATFORM_NAMES,
    STANDARD,
    SOURCE,
    TURBO,
    VIDEO,
    WAV,
    VideoTask,
    DownloadResult,
    check_ffmpeg,
    download_tasks,
    ensure_downloads_dir,
    aria2c_path,
    detect_collection_platform,
    make_task,
)
from folder_picker import FolderPickerUnavailable, choose_folder

MEDIA_TYPE_NAMES = {
    VIDEO: "视频",
    AUDIO: "音频",
}


# ---------------------------------------------------------------------------
# 命令行交互辅助
# ---------------------------------------------------------------------------
def is_virtualenv_activation_command(value: str) -> bool:
    """判断输入是否为终端自动注入的 Python 虚拟环境激活命令。"""
    return bool(
        re.fullmatch(
            r"(?:source|\.)\s+(?:['\"])?[^\r\n]+/(?:\.venv|venv)/bin/activate(?:['\"])?",
            value.strip(),
        )
    )


def choose_media_type() -> str:
    """让交互式用户选择视频或音频，直接回车默认视频。"""
    print("请选择下载类型：")
    print("  1. 视频（默认）")
    print("  2. 音频（最高可用音质，可选择输出格式）")

    while True:
        choice = input("选择 1 或 2（直接回车选择视频）: ").strip().lower()
        if choice in {"", "1", "video", "v"}:
            return VIDEO
        if choice in {"2", "audio", "a"}:
            return AUDIO
        print("⚠️  请输入 1 或 2。")


def choose_audio_format() -> str:
    """让音频用户选择四种输出格式，直接回车默认 MP3。"""
    print("请选择音频输出格式：")
    print("  1. MP3 V0（默认，兼容性最佳）")
    print("  2. 源 FLAC（无 FLAC 时自动回退 MP3 V0）")
    print("  3. 原始音频（保留源音轨编码与扩展名）")
    print("  4. WAV PCM（文件较大，不会提升源音质）")
    while True:
        choice = input("选择 1 至 4（直接回车选择 MP3）: ").strip().lower()
        if choice in {"", "1", "mp3"}:
            return MP3
        if choice in {"2", "flac"}:
            return FLAC
        if choice in {"3", "source", "original"}:
            return SOURCE
        if choice in {"4", "wav"}:
            return WAV
        print("⚠️  请输入 1、2、3 或 4。")


def parse_command_line(
    args: list[str],
) -> tuple[str, str, str, list[str], str | None, str | None]:
    """确定性解析媒体、格式、速度、URL 与合集条目选择。"""
    media_type = VIDEO
    speed_mode = STANDARD
    flac_alias = False
    explicit_audio_format: str | None = None
    item_selection: str | None = None
    output_dir: str | None = None
    urls: list[str] = []

    index = 0
    while index < len(args):
        value = args[index]
        if value == "--audio":
            media_type = AUDIO
        elif value == "--flac":
            flac_alias = True
        elif value == "--turbo":
            speed_mode = TURBO
        elif value in {
            "--audio-format",
            "--items",
            "--output-dir",
            "--download-dir",
        }:
            if index + 1 >= len(args) or args[index + 1].startswith("--"):
                raise ValueError(f"{value} 需要提供一个值")
            raw_option_value = args[index + 1].strip()
            option_value = (
                raw_option_value
                if value in {"--output-dir", "--download-dir"}
                else raw_option_value.lower()
            )
            if not option_value:
                raise ValueError(f"{value} 需要提供一个值")
            if value == "--audio-format":
                if explicit_audio_format is not None:
                    raise ValueError("--audio-format 不能重复使用")
                explicit_audio_format = option_value
            elif value == "--items":
                if item_selection is not None:
                    raise ValueError("--items 不能重复使用")
                item_selection = option_value
            else:
                if output_dir is not None:
                    raise ValueError("下载目录参数不能重复使用")
                output_dir = option_value
            index += 1
        elif value.startswith("-"):
            raise ValueError(f"未知参数: {value}")
        else:
            urls.append(value)
        index += 1

    if flac_alias and media_type != AUDIO:
        raise ValueError("--flac 只能与 --audio 一起使用")
    if explicit_audio_format is not None and media_type != AUDIO:
        raise ValueError("--audio-format 只能与 --audio 一起使用")
    if (
        explicit_audio_format is not None
        and explicit_audio_format not in AUDIO_FORMATS
    ):
        choices = ", ".join(sorted(AUDIO_FORMATS))
        raise ValueError(f"不支持的音频格式: {explicit_audio_format}；可选 {choices}")
    if flac_alias and explicit_audio_format not in {None, FLAC}:
        raise ValueError("--flac 与非 FLAC 的 --audio-format 不能同时使用")

    audio_format = explicit_audio_format or (FLAC if flac_alias else MP3)
    return media_type, audio_format, speed_mode, urls, item_selection, output_dir


def choose_download_location() -> Path:
    """Let an interactive user keep downloads, type a path, or pick a folder."""
    default_dir = DOWNLOADS_DIR.resolve()
    print("请选择下载位置：")
    print(f"  1. 默认位置（{default_dir}）")
    print("  2. 手动输入文件夹路径")
    print("  3. 打开系统文件夹选择器")
    while True:
        choice = input("选择 1 至 3（直接回车使用默认位置）: ").strip().lower()
        if choice in {"", "1", "default"}:
            return ensure_downloads_dir()
        if choice in {"2", "manual"}:
            value = input("下载文件夹路径: ").strip()
            if not value:
                print("⚠️  路径不能为空；若要使用默认位置请选择 1。")
                continue
            try:
                return ensure_downloads_dir(value)
            except ValueError as error:
                print(f"⚠️  {error}")
                continue
        if choice in {"3", "browse", "picker"}:
            try:
                selected = choose_folder(default_dir)
            except FolderPickerUnavailable as error:
                print(f"⚠️  {error}")
                continue
            if selected is None:
                print("已取消文件夹选择，请重新选择下载位置。")
                continue
            try:
                return ensure_downloads_dir(selected)
            except ValueError as error:
                print(f"⚠️  {error}")
                continue
        print("⚠️  请输入 1、2 或 3。")


def parse_item_selection(
    value: str,
    available_ids: list[str],
    limit: int = 100,
) -> list[str]:
    """解析 ``all``、逗号列表或闭区间，并按用户顺序返回条目 ID。"""
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("条目选择不能为空")

    if normalized == "all":
        selected = list(available_ids)
    else:
        selected: list[str] = []
        for token in (part.strip() for part in normalized.split(",")):
            if not token:
                raise ValueError("条目选择格式无效")
            match = re.fullmatch(r"(\d+)-(\d+)", token)
            if match:
                start, end = (int(part) for part in match.groups())
                if start > end:
                    raise ValueError(f"条目范围无效: {token}")
                selected.extend(str(index) for index in range(start, end + 1))
            else:
                selected.append(token)

    if len(selected) > limit:
        raise ValueError(f"一次最多选择 {limit} 个条目")
    if len(set(selected)) != len(selected):
        raise ValueError("不能重复选择同一条目")
    unavailable = [entry_id for entry_id in selected if entry_id not in available_ids]
    if unavailable:
        raise ValueError(f"所选条目不存在或不可下载: {', '.join(unavailable)}")
    if not selected:
        raise ValueError("请至少选择一个条目")
    return selected


def _print_collection_entries(
    previews: list[CollectionPreview],
    numbered_entries: list[tuple[str, CollectionEntry]],
) -> None:
    print("\n📚 检测到播放列表、合集或分 P：")
    for preview in previews:
        if preview.requires_selection:
            print(f"   {preview.title}")
    for entry_id, entry in numbered_entries:
        status = (
            ""
            if entry.selectable
            else f"（不可下载：{entry.unavailable_reason or '未知原因'}）"
        )
        print(f"  {entry_id}. {entry.title}{status}")


def resolve_cli_tasks(
    inputs: list[str],
    item_selection: str | None = None,
    interactive: bool = False,
) -> list[VideoTask]:
    """解析单条或合集输入；合集由 ``--items`` 或交互输入明确选择。"""
    if not inputs:
        raise ValueError("至少需要提供一个链接")

    previews = [resolve_collection(value) for value in inputs]
    numbered_entries: list[tuple[str, CollectionEntry]] = []
    for preview in previews:
        for entry in preview.entries:
            numbered_entries.append((str(len(numbered_entries) + 1), entry))

    requires_selection = any(preview.requires_selection for preview in previews)
    selectable_ids = [
        entry_id
        for entry_id, entry in numbered_entries
        if entry.selectable and entry.url
    ]
    if not selectable_ids:
        raise ValueError("没有可下载的条目")

    if requires_selection:
        _print_collection_entries(previews, numbered_entries)
        selection = item_selection
        if selection is None:
            if not interactive:
                raise ValueError(
                    "检测到播放列表、合集或分 P；请使用 --items all 或 --items 1,3-5 选择条目"
                )
            selection = input("选择条目（all 或 1,3-5，最多 100 项）: ")
        selected_ids = parse_item_selection(selection, selectable_ids)
    else:
        if item_selection is not None:
            raise ValueError("--items 仅用于播放列表、合集或分 P")
        if len(selectable_ids) > 100:
            raise ValueError("一次最多选择 100 个条目")
        selected_ids = selectable_ids

    by_id = {entry_id: entry for entry_id, entry in numbered_entries}
    tasks: list[VideoTask] = []
    for entry_id in selected_ids:
        entry = by_id[entry_id]
        if entry.url:
            tasks.append((entry.platform, entry.url))
    return tasks


def choose_speed_mode() -> str:
    """让交互式用户选择是否为 Bilibili 启用极速模式。"""
    print("是否启用 Bilibili 极速模式？")
    print("  y. 启用 aria2c 多连接下载")
    print("  n. 标准模式（默认）")

    while True:
        choice = input("启用极速模式？(y/N): ").strip().lower()
        if choice in {"", "n", "no"}:
            return STANDARD
        if choice in {"y", "yes"}:
            return TURBO
        print("⚠️  请输入 y 或 n。")


def get_inputs_from_user(media_type: str = VIDEO) -> list[str]:
    """交互式收集单条、播放列表、合集或分 P 链接。"""
    media_name = MEDIA_TYPE_NAMES[media_type]
    print(f"🎬 YouTube + Instagram + Bilibili {media_name}批量下载工具")
    print("=" * 56)
    print("请逐行粘贴单条视频、播放列表、合集或分 P 链接，每行一个。")
    print("三个平台的链接可以任意混合，输入空行后开始解析。")
    print("⚠️  Instagram 与 Bilibili 的部分内容需要配置登录 Cookie。\n")

    inputs: list[str] = []
    while True:
        value = input(f"链接 {len(inputs) + 1}（空行结束）: ").strip()
        if is_virtualenv_activation_command(value):
            continue
        if not value:
            if not inputs:
                print("❌ 至少需要输入一个链接。\n")
                continue
            return inputs
        if make_task(value) or detect_collection_platform(value):
            inputs.append(value)
        else:
            print("⚠️  无法识别该输入，请粘贴受支持平台的链接或分享文案。\n")


def get_tasks_from_user(media_type: str = VIDEO) -> list[VideoTask]:
    """交互式获取混合平台链接，每行一个，空行结束。"""
    media_name = MEDIA_TYPE_NAMES[media_type]
    print(f"🎬 YouTube + Instagram + Bilibili {media_name}批量下载工具")
    print("=" * 56)
    print("请逐行粘贴 YouTube、Instagram 或 Bilibili 视频链接，每行一个。")
    print("三个平台的链接可以任意混合，输入空行后开始下载。")
    print("⚠️  Instagram 与 Bilibili 的部分内容需要配置登录 Cookie。\n")

    tasks: list[VideoTask] = []
    count = 1

    while True:
        value = input(f"链接 {count}（空行结束）: ").strip()

        # 某些 IDE 会在程序占用 stdin 后注入虚拟环境激活命令。
        if is_virtualenv_activation_command(value):
            continue

        if not value:
            if not tasks:
                print("❌ 至少需要输入一个链接。\n")
                continue
            break

        task = make_task(value)
        if task:
            tasks.append(task)
            count += 1
        else:
            print("⚠️  无法识别该链接，请输入受支持的 YouTube、Instagram 或 Bilibili 视频链接。\n")

    print(f"\n📋 已收集 {len(tasks)} 个链接。")
    return tasks


def get_tasks_from_args(args: list[str]) -> list[VideoTask]:
    """从命令行参数提取所有合法的混合平台链接。"""
    tasks: list[VideoTask] = []
    invalid: list[str] = []

    for value in args:
        task = make_task(value)
        if task:
            tasks.append(task)
        else:
            invalid.append(value)

    if invalid:
        print("⚠️  以下参数不是受支持的视频链接，已跳过：")
        for value in invalid:
            print(f"   - {value}")
        print()

    return tasks


# 保留与旧程序相近的函数名，便于已有调用方式迁移。
def get_urls_from_user() -> list[str]:
    """交互式获取链接，仅返回标准化 URL 列表。"""
    return [url for _, url in get_tasks_from_user()]


def get_urls_from_args() -> list[str]:
    """从 sys.argv 获取链接，仅返回标准化 URL 列表。"""
    return [url for _, url in get_tasks_from_args(sys.argv[1:])]


# ---------------------------------------------------------------------------
# 结果展示
# ---------------------------------------------------------------------------
def print_single_result(result: DownloadResult) -> None:
    """格式化输出单个视频的下载结果。"""
    print(f"  平台:     {result['platform']}")
    print(f"  标题:     {result['title']}")
    print(f"  保存路径: {result['filepath']}")
    if result.get("media_type") == AUDIO:
        print(f"  格式:     {result['format']}")
        source_codec = result.get("source_acodec", "未知")
        source_bitrate = result.get("source_abr_kbps", "未知")
        print(f"  源音轨:   {source_codec} / {source_bitrate} kbps")
        if result.get("audio_format_fallback"):
            print("  提示:     源站未提供 FLAC，已自动回退至 MP3 V0")
    else:
        print(f"  分辨率:   {result['resolution']}")
        print(f"  帧率:     {result['fps']} fps")
        print(f"  视频编码: {result['vcodec']}")
    print(f"  音频编码: {result['acodec']}")
    print(f"  文件大小: {result['filesize']}")
    used_mode = result.get("speed_mode_used", STANDARD)
    mode_name = "极速模式" if used_mode == TURBO else "标准模式"
    if result.get("turbo_fallback"):
        mode_name += "（极速模式已降级）"
    print(f"  下载模式: {mode_name}")


def print_summary(
    results: list[tuple[VideoTask, Optional[DownloadResult]]],
    media_type: str = VIDEO,
    output_dir: str | Path | None = None,
) -> None:
    """打印包含平台信息的批量下载汇总。"""
    total = len(results)
    success = sum(1 for _, result in results if result is not None)
    failed = total - success

    print("\n\n" + "=" * 60)
    media_name = MEDIA_TYPE_NAMES[media_type]
    print(f"📊 混合平台{media_name}批量下载汇总报告")
    print("=" * 60)

    if success:
        print(f"\n✅ 成功 {success}/{total}：\n")
        for index, (_, result) in enumerate(results, start=1):
            if result:
                print(f"  {index}. [{result['platform']}] {result['title']}")
                if result.get("media_type") == AUDIO:
                    print(
                        f"     格式: {result['format']}  |  "
                        f"源音轨: {result.get('source_acodec', '未知')} "
                        f"{result.get('source_abr_kbps', '未知')}kbps  |  "
                        f"文件大小: {result['filesize']}"
                    )
                    if result.get("audio_format_fallback"):
                        print("     源站未提供 FLAC，已自动回退至 MP3 V0")
                else:
                    print(
                        f"     分辨率: {result['resolution']}  |  "
                        f"文件大小: {result['filesize']}"
                    )
                used_mode = result.get("speed_mode_used", STANDARD)
                mode_name = "极速模式" if used_mode == TURBO else "标准模式"
                if result.get("turbo_fallback"):
                    mode_name += "（极速模式已降级）"
                print(f"     下载模式: {mode_name}")
                print(f"     路径: {result['filepath']}\n")

    if failed:
        print(f"❌ 失败 {failed}/{total}：\n")
        for index, (task, result) in enumerate(results, start=1):
            if result is None:
                platform, url = task
                print(f"  {index}. [{PLATFORM_NAMES[platform]}] {url}\n")

    print("=" * 60)
    if failed == 0:
        print(f"🎉 全部 {total} 个{media_name}下载成功！")
    elif success == 0:
        print(f"😞 全部 {total} 个{media_name}下载失败，请检查链接、Cookie 和网络后重试。")
    else:
        print(f"📦 {success} 个成功，{failed} 个失败。")
    print(f"📁 文件保存在: {ensure_downloads_dir(output_dir)}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# 程序入口
# ---------------------------------------------------------------------------
def main() -> int:
    """解析输入，确认任务并执行批量下载。"""
    if not check_ffmpeg():
        print("⚠️  警告：未检测到 FFmpeg。")
        print("   最高质量音视频的合并及 MP4 封装需要 FFmpeg。")
        print("   macOS: brew install ffmpeg")
        print("   Windows: 从 https://ffmpeg.org/download.html 下载并添加到 PATH")
        print("   Ubuntu: sudo apt install ffmpeg\n")

    command_line_mode = len(sys.argv) > 1
    if command_line_mode:
        try:
            (
                media_type,
                audio_format,
                speed_mode,
                url_args,
                item_selection,
                output_dir_value,
            ) = parse_command_line(sys.argv[1:])
            output_dir = ensure_downloads_dir(output_dir_value)
            tasks = resolve_cli_tasks(
                url_args,
                item_selection=item_selection,
                interactive=False,
            )
        except DownloadFailure as error:
            print(f"❌ {format_cli_error(error)}")
            return 1
        except ValueError as error:
            print(f"❌ 错误：{error}")
            print(
                "   用法: python main.py [--audio [--flac | --audio-format FORMAT]] "
                "[--turbo] [--output-dir PATH] [--items all|1,3-5] <URL1> [URL2] ..."
            )
            return 1
    else:
        try:
            media_type = choose_media_type()
            audio_format = (
                choose_audio_format() if media_type == AUDIO else MP3
            )
            speed_mode = choose_speed_mode()
            output_dir = choose_download_location()
            inputs = get_inputs_from_user(media_type=media_type)
            tasks = resolve_cli_tasks(inputs, interactive=True)
        except DownloadFailure as error:
            print(f"\n❌ {format_cli_error(error)}")
            return 1
        except ValueError as error:
            print(f"\n❌ 错误：{error}")
            return 1
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return 130

    if speed_mode == TURBO and aria2c_path() is None:
        print("⚠️  未检测到 aria2c；Bilibili 任务将自动使用标准模式。")

    media_name = MEDIA_TYPE_NAMES[media_type]
    print(f"\n📋 共 {len(tasks)} 个{media_name}待下载：")
    print(f"📁 下载位置: {output_dir}")
    for index, (platform, url) in enumerate(tasks, start=1):
        print(f"  {index}. [{PLATFORM_NAMES[platform]}] {url}")

    if not command_line_mode:
        try:
            confirm = input(f"\n开始下载{media_name}？(Y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return 130
        if confirm and confirm != "y":
            print("已取消。")
            return 0

    results = download_tasks(
        tasks,
        media_type=media_type,
        audio_format=audio_format,
        speed_mode=speed_mode,
        output_dir=output_dir,
    )
    print_summary(results, media_type=media_type, output_dir=output_dir)
    return 1 if any(result is None for _, result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
