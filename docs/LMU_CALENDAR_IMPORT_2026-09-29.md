# 本周赛历手动录入试验

- 周期标签：2026-09-29 至 2026-10-05，依据官方说明的周二轮换周期。公开首页只能证明核验当天的当前安排，不能证明七天内每一天都相同。
- 核验时间：2026-10-01 14:38 UTC；使用 Codex Browser 人工查看。
- 数据性质：部分真实赛事数据，不是完整周赛历，也不是合成演示数据。
- 官方公开来源：https://www.racecontrol.gg/
- 官方论坛赛历入口：https://community.lemansultimate.com/index.php?threads/3158/

## 已录入

| 官方赛事名称 | 官方赛道显示名称 | 组别 | 级别 |
| --- | --- | --- | --- |
| LMGT3 Fixed | Spa Francorchamps | LMGT3 | Beginner |
| LMP3 Fixed | Bahrain Wec 2023 | LMP3 | Beginner |
| LMGT3 Sprint Cup | Long Beach 2026 | LMGT3 | Intermediate |

组别依据官方赛事名称；没有由赛事名称推断具体车辆名单。
Bahrain 的 WEC 2023 和 Long Beach 的 2026 为官方显示的赛道版本标识；不是额外核验出的布局规格。

## 信息边界

公开首页还列出 Logitech McLaren G Challenge - Q1、ELMS Sprint Trophy、One Stint Sprint、ELMS Super 60、Prototype Fixed、WEC-Xperience。未核实其当前参赛组别，因此未发布这些赛事。rFactor 2 的 Formula Classic / Open Wheel Sprint 排除。

首页显示的 Duration 为 32 / 32 / 44 minutes，但未明确这是比赛净时长还是包含练习及排位的总场次时长，因此 durationMinutes 保持 null。
首页显示 1 Oct 滚动近期时段，未标明时区，也没有完整一周时间表，因此 sessions 保持空数组，没有自行扩展重复时段。
天气、赛道状态、SR、徽章、订阅、允许车型、车型推荐及燃油策略均未核实，保持未发布。没有利用旧图片文件名推断当前天气，没有填入虚构油耗或 BoP。

官方论坛置顶帖（最后编辑 2026-09-24）要求今后的安排查看官方 Discord #online-status-schedule，且说明赛历通常周二上午 UTC 更换。当前浏览器访问官方 Discord 邀请链接后显示账号注册/登录入口，未能读取公告；没有注册、加入服务器或发送消息。搜索到的玩家转载为上一周，不用于本周录入。

## 实际流程与验收

输入文件：data/lmu/calendar/imports/2026-09-29.json。

```sh
venv/bin/python scripts/update_lmu_calendar.py data/lmu/calendar/imports/2026-09-29.json --check
venv/bin/python scripts/update_lmu_calendar.py data/lmu/calendar/imports/2026-09-29.json
```

校验输出 Valid calendar；实际发布输出 Calendar published。缺失字段正常报告。赛历单元测试 12 项通过。浏览器实际页面显示三项赛事、正确周范围、英国 BST 更新时间及部分数据提示；赛事来源展开后可见官方链接。没有代码更改或新增自动更新。
