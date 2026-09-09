"""Versioned editorial content, source-review metadata, and readable diffs."""
import json
from pathlib import Path
from lmu_guide_data import CARS, CIRCUITS
from lmu_practice_data import CAR_NOTES, TRACK_NOTES, CHECKED_ON, GAME_REFERENCE, GAME_SOURCE

CONTENT_DIR = Path(__file__).resolve().parent / 'data' / 'lmu'
# Set an override only after reviewing evidence for the exact recommendation.
# key: circuit-slug:car-slug; values: applicable_version, evidence_url, checked_on.
RECOMMENDATION_REVIEWS = {}
FIELD_LABELS = {
    'name': ('名称', 'Name'), 'href': ('条目位置', 'Record location'),
    'build_reference': ('官方版本参考', 'Official build reference'),
    'strength': ('优点', 'Strengths'), 'caution': ('注意事项', 'Caveats'),
    'character': ('赛道特点', 'Circuit character'), 'challenge': ('挑战', 'Challenge'),
    'advice': ('驾驶建议', 'Driving advice'), 'fit': ('推荐理由', 'Recommendation reason'),
    'observation': ('来源要点', 'Source notes'), 'exercise': ('练习与复盘', 'Practice and reflection'),
    'applicable_version': ('适用游戏版本', 'Applicable game version'),
    'checked_on': ('来源核验日期', 'Source review date'),
    'sources': ('资料来源', 'Sources'), 'evidence_url': ('版本验证证据', 'Version evidence'),
}


def pair(zh, en):
    return {'zh': zh, 'en': en}


def recommendation_review(circuit, car):
    result = dict(applicable_version=None, evidence_url=None, checked_on=CHECKED_ON,
                  sources=[circuit.source_url, CAR_NOTES[car.slug]['source_url']])
    result.update(RECOMMENDATION_REVIEWS.get(f'{circuit.slug}:{car.slug}', {}))
    return result


def current_records(include_research=True):
    records = {}
    for kind, entities, notes in [('circuit', CIRCUITS, TRACK_NOTES), ('car', CARS.values(), CAR_NOTES)]:
        for entity in entities:
            names = ['character', 'challenge', 'advice'] if kind == 'circuit' else ['strength', 'caution']
            fields = {name: pair(getattr(entity, name + '_zh'), getattr(entity, name)) for name in names}
            if include_research:
                note = notes[entity.slug]
                fields.update(observation=pair(note['observation_zh'], note['observation']), exercise=pair(note['exercise_zh'], note['exercise']),
                              applicable_version=pair(note['applicable_version'] or '未验证', note['applicable_version'] or 'Unverified'),
                              checked_on=pair(note['checked_on'], note['checked_on']), sources=pair(note['source_url'], note['source_url']))
                if note.get('evidence_url'):
                    fields['evidence_url'] = pair(note['evidence_url'], note['evidence_url'])
            records[f'{kind}:{entity.slug}'] = dict(name=entity.name, href=f'/kozekilmu/{"tracks" if kind == "circuit" else "cars"}#{entity.slug}', fields=fields)
    for circuit in CIRCUITS:
        for recommendation in (*circuit.lmgt3, *circuit.hypercar):
            car = CARS[recommendation.car_slug]
            fields = {'fit': pair(recommendation.fit_zh, recommendation.fit)}
            if include_research:
                review = recommendation_review(circuit, car)
                fields.update(applicable_version=pair(review['applicable_version'] or '未验证', review['applicable_version'] or 'Unverified'), checked_on=pair(review['checked_on'], review['checked_on']), sources=pair('\n'.join(review['sources']), '\n'.join(review['sources'])), evidence_url=pair(review['evidence_url'] or '尚无实测证据', review['evidence_url'] or 'No driving-test evidence'))
            records[f'recommendation:{circuit.slug}:{car.slug}'] = dict(name=f'{circuit.name} · {car.name}', href=f'/kozekilmu/tracks#{circuit.slug}', fields=fields)
    if include_research:
        records['reference:game'] = dict(name='LMU', href='/kozekilmu/updates', fields={
            'build_reference': pair(GAME_REFERENCE, GAME_REFERENCE),
            'checked_on': pair(CHECKED_ON, CHECKED_ON), 'sources': pair(GAME_SOURCE, GAME_SOURCE)})
    return records


def compare_records(previous, current):
    changes = []
    for key in sorted(set(previous) | set(current)):
        old = previous.get(key)
        new = current.get(key)
        fields = []
        for field in sorted(set((old or {}).get('fields', {})) | set((new or {}).get('fields', {}))):
            before = (old or {}).get('fields', {}).get(field)
            after = (new or {}).get('fields', {}).get(field)
            if before != after:
                labels = FIELD_LABELS.get(field, (field, field))
                fields.append(dict(label=pair(*labels), before=before, after=after))
        if old is not None and new is not None:
            for field in ('name', 'href'):
                if old[field] != new[field]:
                    fields.append(dict(label=pair(*FIELD_LABELS[field]), before=pair(old[field], old[field]), after=pair(new[field], new[field])))
        if fields or old is None or new is None:
            record = new or old
            changes.append(dict(key=key, name=record['name'], href=record['href'], kind=key.split(':')[0], status='added' if old is None else 'removed' if new is None else 'changed', fields=fields))
    return changes


def history():
    manifest = json.loads((CONTENT_DIR / 'releases.json').read_text(encoding='utf-8'))
    result = []
    previous = None
    for release in manifest:
        records = json.loads((CONTENT_DIR / release['snapshot']).read_text(encoding='utf-8'))
        # The import baseline is not a claim that all old content was newly authored.
        changes = [] if previous is None else compare_records(previous, records)
        result.append(dict(**release, changes=changes))
        previous = records
    return list(reversed(result))


def template_context():
    latest = history()[0]
    reviews = [recommendation_review(circuit, CARS[rec.car_slug]) for circuit in CIRCUITS for rec in (*circuit.lmgt3, *circuit.hypercar)]
    validated = sum(bool(item['applicable_version'] and item['evidence_url']) for item in reviews)
    return dict(car_notes=CAR_NOTES, track_notes=TRACK_NOTES, recommendation_review=recommendation_review,
                content_version=latest['version'], content_date=latest['date'],
                game_reference=GAME_REFERENCE, game_source=GAME_SOURCE, game_checked_on=CHECKED_ON, validated_recommendations=validated, total_recommendations=len(reviews))
