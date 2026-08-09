#!/usr/bin/env python3
"""
YouTube、Instagram 与 Bilibili 视频批量下载工具 — 命令行入口。

同一批任务可以混合包含 YouTube、Instagram 和 Bilibili 链接。程序会自动识别平台，
并为不同平台选择对应的 yt-dlp 下载参数。

核心下载逻辑位于 downloader.py，本文件仅保留命令行交互与结果展示。
"""

import re
import sys
from typing import Optional

from downloader import (
    AUDIO,
    DOWNLOADS_DIR,
    FLAC,
    MP3,
    PLATFORM_NAMES,
    STANDARD,
    TURBO,
    VIDEO,
    VideoTask,
    DownloadResult,
    check_ffmpeg,
    download_tasks,
    aria2c_path,
    make_task,
)

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
    """让交互式用户选择视频或 MP3 音频，直接回车默认视频。"""
    print("请选择下载类型：")
    print("  1. 视频（默认）")
    print("  2. MP3 音频（最高可用音质）")

    while True:
        choice = input("选择 1 或 2（直接回车选择视频）: ").strip().lower()
        if choice in {"", "1", "video", "v"}:
            return VIDEO
        if choice in {"2", "audio", "a"}:
            return AUDIO
        print("⚠️  请输入 1 或 2。")


def choose_audio_format() -> str:
    """让音频用户选择 MP3 V0 或源 FLAC，直接回车默认 MP3。"""
    print("请选择音频输出格式：")
    print("  1. MP3 V0（默认，兼容性最佳）")
    print("  2. 源 FLAC（无 FLAC 时自动回退 MP3 V0）")
    while True:
        choice = input("选择 1 或 2（直接回车选择 MP3）: ").strip().lower()
        if choice in {"", "1", "mp3"}:
            return MP3
        if choice in {"2", "flac"}:
            return FLAC
        print("⚠️  请输入 1 或 2。")


def parse_command_line(args: list[str]) -> tuple[str, str, str, list[str]]:
    """解析媒体、音频格式与速度标志，并返回 URL 参数。"""
    if "--flac" in args and "--audio" not in args:
        raise ValueError("--flac 只能与 --audio 一起使用")
    media_type = AUDIO if "--audio" in args else VIDEO
    audio_format = FLAC if "--flac" in args else MP3
    speed_mode = TURBO if "--turbo" in args else STANDARD
    flags = {"--audio", "--flac", "--turbo"}
    urls = [value for value in args if value not in flags]
    return media_type, audio_format, speed_mode, urls


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
    print(f"📁 文件保存在: {DOWNLOADS_DIR.resolve()}")
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
            media_type, audio_format, speed_mode, url_args = parse_command_line(
                sys.argv[1:]
            )
        except ValueError as error:
            print(f"❌ 错误：{error}")
            print(
                "   用法: python main.py [--audio [--flac]] "
                "[--turbo] <URL1> [URL2] [URL3] ..."
            )
            return 1
        tasks = get_tasks_from_args(url_args)
        if not tasks:
            print("❌ 错误：未提供合法的 YouTube、Instagram 或 Bilibili 视频链接。")
            print(
                "   用法: python main.py [--audio [--flac]] "
                "[--turbo] <URL1> [URL2] [URL3] ..."
            )
            return 1
    else:
        try:
            media_type = choose_media_type()
            audio_format = (
                choose_audio_format() if media_type == AUDIO else MP3
            )
            speed_mode = choose_speed_mode()
            tasks = get_tasks_from_user(media_type=media_type)
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return 130

    if speed_mode == TURBO and aria2c_path() is None:
        print("⚠️  未检测到 aria2c；Bilibili 任务将自动使用标准模式。")

    media_name = MEDIA_TYPE_NAMES[media_type]
    print(f"\n📋 共 {len(tasks)} 个{media_name}待下载：")
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
    )
    print_summary(results, media_type=media_type)
    return 1 if any(result is None for _, result in results) else 0


if __name__ == "__main__":
    sys.exit(main())
