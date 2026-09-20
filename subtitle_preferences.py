"""Validate optional video text-track preferences shared by API and queue."""


def normalize_subtitle_options(value=None, media_type='video'):
    if value is None:
        return {}
    keys = ('subtitles', 'automatic', 'danmaku')
    if not isinstance(value, dict) or any(key not in keys for key in value):
        raise ValueError('subtitle_options 必须是字幕选项对象')
    if any(type(item) is not bool for item in value.values()):
        raise ValueError('字幕选项必须为布尔值')
    options = {key: value.get(key, False) for key in keys}
    if options['automatic'] and not options['subtitles']:
        raise ValueError('自动字幕需要先启用下载字幕')
    if media_type != 'video' and any(options.values()):
        raise ValueError('字幕与弹幕仅适用于视频下载')
    return options if any(options.values()) else {}
