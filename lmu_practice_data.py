"""Short paraphrases of sources read on 2026-09-09; exercises are editorial.

These notes are not driving tests or confirmation of compatibility with a build.
Source URLs are retained per entity; no remote fetching occurs at runtime.
"""
from lmu_guide_data import CARS, CIRCUITS

CHECKED_ON = '2026-09-09'
GAME_REFERENCE = 'V1.4.1.4'
GAME_SOURCE = 'https://guide.lemansultimate.com/hc/en-gb/articles/17478704157071-V1-4-1-4-Update-V1-4-Patch-1-Hotfix-4'

# slug: source observation (zh/en), proposed exercise (zh/en)
_TRACK_ROWS = {
'bahrain': ('官方强调高温与轮胎衰退。', 'The official overview highlights heat and tire degradation.', '固定油量连续跑短 stint，比较前后段圈速与出弯打滑次数，先追求稳定。', 'Run a short stint at a fixed starting fuel load; compare early and late pace and exit slides before chasing a peak lap.'),
'barcelona': ('高速长弯、技术中速段与长直道共同考验轮胎和车辆平衡。', 'Fast sweepers, technical medium-speed sections, and the main straight test tires and balance.', '把高速弯和技术段分开练习，记录持续加方向仍推头的位置，减少额外转向。', 'Practice sweepers and technical sections separately; note where extra steering adds scrub rather than rotation.'),
'le-mans': ('官方同时指出 Mulsanne 高速直道及 Indianapolis、Arnage 技术弯的挑战。', 'The overview contrasts the Mulsanne straight with technical Indianapolis and Arnage.', '分段复习高速末端制动和低速出弯，先建立可重复的制动参照。', 'Rehearse braking after fast sections and slow-corner exits separately, establishing repeatable braking references.'),
'paul-ricard': ('官方介绍 Mistral 直道布局变化，以及蓝红色高摩擦缓冲区。', 'The overview describes Mistral layout changes and abrasive blue/red runoff.', '先确认当前布局；用赛道内参照练制动，别把彩色缓冲区当正常走线。', 'Confirm the selected layout and use on-track braking references; keep colored runoff out of your normal line.'),
'cota': ('第一赛段高速起伏，后半圈更偏技术性，且常面对高温。', 'A fast, undulating first sector contrasts with a technical second half and heat.', '单练第一段连续换向，避免为一个弯抢速度而破坏后续走线；再检查后半圈出弯。', 'Practice the opening direction changes as a sequence, then review exits in the technical half.'),
'daytona': ('公路布局结合高速椭圆部分与技术内场，需要兼顾两种特性。', 'The road course combines superspeedway speed with a technical infield.', '分别记录内场损失与高速段表现；调整前后用相同油量比较整圈，而非只看极速。', 'Track infield losses and fast-section performance separately; compare complete laps at equal fuel, not top speed alone.'),
'fuji': ('1.47 km 长直道、技术区和多变天气构成主要挑战。', 'A 1.47 km straight, technical sections, and changeable weather define the challenge.', '反复练习通向主直道的出弯，再在不同天气中重建制动参照。', 'Repeat the exit onto the main straight, then rebuild braking references in different weather.'),
'imola': ('官方列出 Tamburello、Villeneuve、Tosa、Rivazza 等起伏赛段。', 'The overview highlights an undulating lap through Tamburello, Villeneuve, Tosa, and Rivazza.', '按这些弯组拆分练习，以连续干净圈验证节奏，再逐步增加速度。', 'Practice those corner groups separately; establish consecutive clean laps before increasing pace.'),
'interlagos': ('Senna S、高低起伏和天气变化使走线衔接很重要。', 'The Senna S, elevation changes, and variable weather shape the circuit.', '把 Senna S 当完整组合练习，记录出口位置；雨天重新检查视线与制动点。', 'Practice the Senna S as one sequence and record exit position; reassess sightlines and braking in rain.'),
'lusail': ('官方记录从白昼跑到灯光下的耐力赛，并提醒存在不同布局。', 'The overview describes endurance racing from daylight into floodlights and multiple layouts.', '先核对布局，分别练白天和夜间参照，比较相同弯的制动识别是否稳定。', 'Confirm the layout, then compare daytime and nighttime braking references at the same corners.'),
'monza': ('长直道、复杂减速弯和高速是官方概括的核心特征。', 'Long straights, demanding chicanes, and speed are the core features.', '分开练直道末端减速和减速弯出口，优先保证接下来直道的起始速度。', 'Separate end-of-straight braking practice from chicane exits, prioritizing speed onto the following straight.'),
'portimao': ('起伏与多种弯速带来较高滑移能量，对轮胎要求高。', 'Elevation changes and varied corner speeds create high sliding energy and tire demands.', '在坡顶与落差处减少突然输入；用连续圈检查滑移与胎况，而非只追单圈。', 'Reduce abrupt inputs around crests and elevation changes; assess sliding over consecutive laps.'),
'sebring': ('混凝土跑道遗留的颠簸是官方特别强调的难点。', 'Concrete runway bumps are a defining challenge in the official overview.', '固定设置比较不同走线的颠簸与方向修正，选出能重复完成的路线。', 'With setup fixed, compare bumps and steering corrections on alternate lines; favor a repeatable route.'),
'silverstone-international': ('官方强调快速流畅的走向及 Copse、Maggots–Becketts 等弯。', 'The overview emphasizes flowing speed, Copse, and Maggots–Becketts.', '确认使用包含这些弯的布局后，连贯练习换向，记录每个出口是否为下一弯留好位置。', 'On a layout containing these corners, practice linked changes of direction and check positioning for the next turn.'),
'spa': ('海拔起伏、长赛道和快速变化的天气是官方提示的挑战。', 'Elevation, a long lap, and rapidly changing weather are highlighted.', '按赛段检查抓地变化，先留制动余量，再逐步确认高速弯入口速度。', 'Check grip by sector, retain braking margin, and build confidence in fast-corner entry speeds progressively.'),
'laguna-seca': ('Corkscrew 是有明显落差的盲左—右组合，赛道缓冲空间有限。', 'The Corkscrew is a blind left-right drop, with limited runoff around the circuit.', '低速熟悉 Corkscrew 的参照和落点，连跑无越界圈后再提速。', 'Learn the Corkscrew references and landing at reduced speed, then build pace after consecutive clean laps.'),
}

# Each linked guide was opened and its handling section read; version unspecified.
_CAR_ROWS = {
'aston-martin-vantage-lmgt3': ('aston-martin-vantage-lmgt3-evo-guide-the-inside-line', '指南描述入弯推头，也提醒重刹可能让车尾突然滑动。', 'The guide describes entry understeer and possible rear snaps under hard braking.', '逐步调整拖刹释放，记录转向改善是否伴随车尾不稳。', 'Vary brake release gradually and note whether improved rotation costs rear stability.'),
'bmw-m4-lmgt3': ('lmu-bmw-m4-gt3-the-inside-line', '指南建议渐进给油并平顺回正，以减少出弯车尾突发滑动。', 'The guide favors progressive throttle and smooth steering unwind to limit exit snaps.', '用同一弯比较急给油与渐进给油，观察出口速度和修正次数。', 'Compare throttle ramps at one corner, observing exit speed and steering corrections.'),
'corvette-z06-lmgt3-r': ('lmu-chevrolet-corvette-z06-gt3-r-guide-the-inside-line', '指南强调主动转向特性，并提醒长段驾驶时照顾后胎。', 'The guide notes eager rotation and the need to manage rear tires during stints.', '练习过弯心后平顺回正，用连续圈观察后胎滑移是否增加。', 'Practice smooth steering unwind after the apex and monitor rear sliding over consecutive laps.'),
'ferrari-296-lmgt3': ('lmu-ferrari-296-lmgt3-guide-the-inside-line', '指南提醒高速弯、脏空气和雨地中的车尾稳定性。', 'The guide flags rear stability in fast corners, dirty air, and wet conditions.', '先稳定单车高速段，再留距离练跟车，避免直接照搬单车入口速度。', 'Establish solo fast-corner consistency, then practice following with space rather than copying solo entry speeds.'),
'ford-mustang-lmgt3': ('lmu-ford-mustang-gt3-guide-the-inside-line', '指南认为入弯准备不足会持续推头，建议先充分降速。', 'The guide warns that insufficient preparation and entry speed reduction produce persistent understeer.', '把减速做在入弯前，比较更早准备是否换来更顺畅的出弯。', 'Complete more speed reduction before turning and compare the resulting exit quality.'),
'lamborghini-huracan-lmgt3-evo2': ('lmu-lamborghini-huracan-gt3-evo-2-the-inside-line', '指南区分入弯车尾活动与给油后出弯推头，也提醒过度拖刹。', 'The guide distinguishes a mobile rear on entry from power-on exit understeer and warns against excessive trail braking.', '分开记录入弯和出弯问题，先平顺释放刹车，再调整给油时机。', 'Log entry and exit problems separately; smooth brake release before adjusting throttle timing.'),
'lexus-rc-f-lmgt3': ('lmu-lexus-rc-f-lmgt3-guide-the-inside-line', '指南建议重视出口速度，并对路肩保持谨慎。', 'The guide emphasizes exit speed and caution over kerbs.', '先用少吃路肩的路线稳定跑圈，再单独试验路肩是否真的带来收益。', 'Build consistency with modest kerb use, then test kerbs one at a time for actual gains.'),
'mclaren-720s-lmgt3-evo': ('lmu-mclaren-720s-gt3-evo-the-inside-line', '指南建议直线制动并保持弯速，注意过度转向消耗后胎。', 'The guide favors straight-line braking and carried corner speed, while noting rear-tire costs from oversteer.', '比较流畅过弯与弯心过度减速，记录后胎滑移而不只看最快圈。', 'Compare flowing cornering with excessive apex slowing; track rear sliding as well as peak pace.'),
'porsche-911-gt3-r': ('lmu-porsche-911-gt3-r-guide-the-inside-line', '指南强调平顺控制重心转移，给油前先让车身稳定并完成转向。', 'The guide stresses smooth weight transfer and settling and rotating the car before acceleration.', '固定油量练习缓慢衔接松刹与给油，比较长段后半程是否仍能稳定出弯。', 'Practice a smooth brake-to-throttle transition at fixed fuel and check exit consistency late in a stint.'),
'alpine-a424': ('lmu-alpine-a424-guide-the-inside-line', '指南描述默认设置下的推头，并建议为制动留出更长距离。', 'The guide describes default-setup understeer and a need for more deliberate braking distance.', '先采用保守制动参照；确认能持续到达弯心后，再逐步缩短减速距离。', 'Start with conservative braking references and shorten the zone only after consistently reaching the apex.'),
'bmw-m-hybrid-v8': ('lmu-bmw-m-hybrid-v8-guide-the-inside-line', '指南强调冷胎、冷刹车阶段的控制，特别是夜间。', 'The guide highlights cold tires and brakes, particularly during night running.', '分别记录出站圈与热态圈的制动参照，不把热胎经验直接用于冷胎。', 'Record out-lap and warmed-up braking references separately instead of transferring warm-tire assumptions.'),
'cadillac-v-series-r': ('lmu-cadillac-v-series-r-guide-the-inside-line', '指南提醒重刹后轮锁死及高速段车尾敏感。', 'The guide warns about rear locking under heavy braking and rear sensitivity at speed.', '从直线渐进制动开始，记录锁死发生阶段，再练转向与松刹衔接。', 'Begin with progressive straight-line braking, log where lockups occur, then practice the turn-in transition.'),
'ferrari-499p': ('lmu-ferrari-499p-guide-the-inside-line', '指南提醒出弯给油时车尾可能突发滑动，雨地和旧胎更需留意。', 'The guide flags power-on exit snaps, especially in rain or on worn tires.', '比较新旧胎下的给油坡度，优先找到不用反复修方向的加速方式。', 'Compare throttle ramps on fresh and worn tires, aiming for acceleration without repeated corrections.'),
'peugeot-9x8-2024': ('lmu-peugeot-9x8-2024-guide-the-inside-line', '指南认为车头未转好就给油会加重推头，迫使二次收油。', 'The guide explains that accelerating before rotation is complete increases understeer and forces another lift.', '在同一弯延后一点给油，检查是否减少二次收油并改善出口位置。', 'Delay throttle slightly at one corner and check whether it reduces second lifts and improves exit position.'),
'porsche-963': ('lmu-porsche-963-guide-the-inside-line', '指南描述较中性的平衡，但过于激进的出弯仍会诱发转向过度。', 'The guide describes neutral balance but notes that aggressive exits can still induce oversteer.', '保留相同设置，比较不同给油速度下的出弯稳定性，记录连续圈而非偶然最快圈。', 'Keep setup fixed and compare throttle application rates over consecutive laps, not one exceptional lap.'),
'toyota-gr010-hybrid': ('lmu-toyota-gr010-guide-the-inside-line', '指南提醒入弯过快会转为推头，刹车锁死时需释放压力恢复滚动。', 'The guide warns that excessive entry speed induces understeer and advises releasing pressure to recover from locking.', '先降低入口速度，比较是否更早稳定给油；单独练习识别并释放锁死。', 'Reduce entry speed and compare how soon stable acceleration becomes possible; separately practice lockup recognition and release.'),
}

TRACK_NOTES = {slug: dict(observation_zh=row[0], observation=row[1], exercise_zh=row[2], exercise=row[3], checked_on=CHECKED_ON, applicable_version=None, source_url=next(c.source_url for c in CIRCUITS if c.slug == slug), source_name='Le Mans Ultimate', basis='official-description') for slug, row in _TRACK_ROWS.items()}
CAR_NOTES = {slug: dict(observation_zh=row[1], observation=row[2], exercise_zh=row[3], exercise=row[4], checked_on=CHECKED_ON, applicable_version=None, source_url=f'https://coachdaveacademy.com/tutorials/{row[0]}/', source_name='Coach Dave Academy / The Inside Line', basis='driving-guide') for slug, row in _CAR_ROWS.items()}

# Future per-record reviews must be explicit; do not bump CHECKED_ON globally.
# Example key: car:bmw-m4-lmgt3; values: checked_on, applicable_version, evidence_url.
NOTE_REVIEWS = {}
for _kind, _notes in [('circuit', TRACK_NOTES), ('car', CAR_NOTES)]:
    for _slug, _note in _notes.items():
        _note.update(NOTE_REVIEWS.get(f'{_kind}:{_slug}', {}))
