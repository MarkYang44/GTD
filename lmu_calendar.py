"""Validated, manually published LMU schedules. Never fetches external data."""
from datetime import date, datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import tempfile
from typing import TypedDict
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from lmu_guide_data import CARS

TIMEZONE = 'Europe/London'
from gtd_paths import runtime_root

DEFAULT_DIR = runtime_root() / 'data' / 'lmu' / 'calendar'
OFFICIAL_HOSTS = ('lemansultimate.com', 'racecontrol.gg', 'studio-397.com')
INPUT_BOUNDS = {'minutes': (1, 1440), 'lap': (10, 1800), 'fuel': (.01, 100),
                'tank': (.1, 1000), 'formation': (0, 1000), 'rate': (.01, 100), 'loss': (0, 3600)}


class Copy(TypedDict):
    zh: str
    en: str


class Eligibility(TypedDict):
    minimumSR: str | None
    badge: str | None
    subscription: str | None


class Evidence(TypedDict):
    gameVersion: str | None
    trackCharacteristics: Copy | None
    bop: Copy | None
    recentPerformance: Copy | None
    sources: list[str]


class RecommendedCar(TypedDict):
    carId: str
    rank: int
    summary: Copy
    drivingCharacteristics: Copy | None
    driverType: Copy | None
    evidence: Evidence


class StrategyInputs(TypedDict):
    minutes: float
    lap: float
    fuel: float
    tank: float
    formation: float
    rate: float
    loss: float


class Strategy(TypedDict):
    carId: str
    inputs: StrategyInputs
    calculationNotes: Copy
    pitStopRequirement: Copy | None
    pitWindow: Copy | None
    tireStrategy: Copy | None
    tireChangeRecommendation: Copy | None
    trafficManagement: Copy | None
    fasterClassAdvice: Copy | None
    slowerClassAdvice: Copy | None
    overtakingAdvice: Copy | None
    beingLappedAdvice: Copy | None
    sources: list[str]


class Event(TypedDict):
    id: str
    name: str
    track: str
    trackId: str | None
    layout: str | None
    eventType: str
    sessions: list[str]
    durationMinutes: float | None
    classes: list[str]
    eventLevel: str | None
    eligibility: Eligibility
    weather: Copy | None
    trackConditions: Copy | None
    allowedCars: dict[str, list[str]]
    recommendedCars: dict[str, list[RecommendedCar]]
    strategy: list[Strategy]
    sources: list[str]


class Calendar(TypedDict):
    schemaVersion: int
    weekStart: str | None
    weekEnd: str | None
    lastUpdated: str | None
    timezone: str
    gameVersion: str | None
    sources: list[str]
    events: list[Event]


def empty_calendar() -> Calendar:
    return dict(schemaVersion=1, weekStart=None, weekEnd=None, lastUpdated=None,
                timezone=TIMEZONE, gameVersion=None, sources=[], events=[])


def parse_timestamp(value: str) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
            r'\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)', value):
        raise ValueError('Timestamp must be ISO 8601 with seconds and UTC offset.')
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.utcoffset() is None:
        raise ValueError('Timestamp needs a UTC offset.')
    return result


def uk_time(value: str | None) -> str:
    return parse_timestamp(value).astimezone(ZoneInfo(TIMEZONE)).strftime('%Y-%m-%d %H:%M %Z') if value else 'Not Published'


def _object(value, keys, path):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ValueError(f'{path}: expected fields {", ".join(keys)}.')


def _text(value, path, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > 4000:
        raise ValueError(f'{path}: expected nonempty text (maximum 4000 characters).')


def _copy(value, path, nullable=False):
    if nullable and value is None:
        return
    _object(value, Copy.__annotations__, path)
    for language in ('zh', 'en'):
        _text(value[language], path + '.' + language)


def _sources(value, path):
    if not isinstance(value, list) or len(value) > 20:
        raise ValueError(f'{path}: expected up to 20 official source links.')
    for url in value:
        _text(url, path)
        parsed = urlparse(url)
        host = parsed.hostname or ''
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or not any(host == domain or host.endswith('.' + domain) for domain in OFFICIAL_HOSTS)):
            raise ValueError(f'{path}: use an HTTPS LMU, RaceControl or Studio 397 source.')


def _number(value, bounds, path):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not bounds[0] <= value <= bounds[1]):
        raise ValueError(f'{path}: expected a finite number in {bounds}.')


def _date(value, path):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError(f'{path}: expected YYYY-MM-DD.')
    return date.fromisoformat(value)


def _car(car_id, event, path):
    car = CARS.get(car_id) if isinstance(car_id, str) else None
    if not car or car.car_class not in event['classes']:
        raise ValueError(f'{path}: car must exist in the catalog and match an event class.')
    allowed = event['allowedCars'].get(car.car_class)
    if allowed is not None and car_id not in allowed:
        raise ValueError(f'{path}: car is not in the published eligible-car list.')
    return car


def validate_calendar(data: Calendar) -> Calendar:
    """Validate shape plus cross-field rules; null means genuinely unknown."""
    _object(data, Calendar.__annotations__, 'calendar')
    if type(data['schemaVersion']) is not int or data['schemaVersion'] != 1 or data['timezone'] != TIMEZONE:
        raise ValueError('calendar: schemaVersion must be 1 and timezone Europe/London.')
    _text(data['gameVersion'], 'gameVersion', nullable=True)
    _sources(data['sources'], 'sources')
    if not isinstance(data['events'], list) or len(data['events']) > 100:
        raise ValueError('events: expected up to 100 events.')
    if data['weekStart'] is None:
        if data['weekEnd'] is not None or data['lastUpdated'] is not None or data['events']:
            raise ValueError('An unpublished calendar must have null week bounds/update and no events.')
        return data
    start, end = _date(data['weekStart'], 'weekStart'), _date(data['weekEnd'], 'weekEnd')
    if (end - start).days != 6:
        raise ValueError('weekEnd must be six days after weekStart (inclusive week).')
    parse_timestamp(data['lastUpdated'])
    seen = set()
    for event in data['events']:
        _object(event, Event.__annotations__, 'event')
        for field in ('id', 'name', 'track', 'eventType'):
            _text(event[field], field)
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', event['id']) or event['id'] in seen:
            raise ValueError('event.id: use a unique alphanumeric slug.')
        seen.add(event['id'])
        if event['eventType'] not in ('Daily', 'Weekly', 'Special', 'Championship'):
            raise ValueError('eventType: use Daily, Weekly, Special or Championship.')
        for field in ('layout', 'eventLevel', 'trackId'):
            _text(event[field], field, nullable=True)
        _object(event['eligibility'], Eligibility.__annotations__, 'eligibility')
        for field, value in event['eligibility'].items():
            _text(value, 'eligibility.' + field, nullable=True)
        for field in ('weather', 'trackConditions'):
            _copy(event[field], field, nullable=True)
        _sources(event['sources'], 'event.sources')
        if event['durationMinutes'] is not None:
            _number(event['durationMinutes'], (1, 1440), 'durationMinutes')
        classes = event['classes']
        if not isinstance(classes, list) or not classes or len(classes) > 10:
            raise ValueError('classes must contain 1–10 class names.')
        for class_name in classes:
            _text(class_name, 'classes')
        if len(set(classes)) != len(classes):
            raise ValueError('classes must be unique.')
        sessions = event['sessions']
        if not isinstance(sessions, list) or len(sessions) > 2000:
            raise ValueError('sessions must contain up to 2000 ISO timestamps.')
        parsed_sessions = [parse_timestamp(item) for item in sessions]
        if len(set(parsed_sessions)) != len(parsed_sessions):
            raise ValueError('sessions must be unique instants.')
        if any(not start <= item.astimezone(ZoneInfo(TIMEZONE)).date() <= end for item in parsed_sessions):
            raise ValueError('Session UK date must fall within the calendar week.')
        allowed = event['allowedCars']
        if not isinstance(allowed, dict) or not set(allowed).issubset(classes):
            raise ValueError('allowedCars keys must match event classes.')
        for class_name, car_ids in allowed.items():
            if not isinstance(car_ids, list) or not car_ids:
                raise ValueError('Published eligible-car lists cannot be empty; omit unknown lists.')
            for car_id in car_ids:
                _text(car_id, 'allowedCars')
            if len(set(car_ids)) != len(car_ids):
                raise ValueError('allowedCars entries must be unique.')
            for car_id in car_ids:
                if car_id in CARS and CARS[car_id].car_class != class_name:
                    raise ValueError('allowedCars catalog car/class mismatch.')
        recommendations = event['recommendedCars']
        if not isinstance(recommendations, dict) or not set(recommendations).issubset(classes):
            raise ValueError('recommendedCars keys must match event classes.')
        for class_name, cars in recommendations.items():
            if not isinstance(cars, list) or len(cars) > 3:
                raise ValueError('Recommend at most three cars per class.')
            ids, ranks = set(), set()
            for rec in cars:
                _object(rec, RecommendedCar.__annotations__, 'recommendation')
                car = _car(rec['carId'], event, 'recommendation.carId')
                if car.car_class != class_name or rec['carId'] in ids or type(rec['rank']) is not int or rec['rank'] not in (1, 2, 3) or rec['rank'] in ranks:
                    raise ValueError('Recommendations require unique cars and ranks 1–3 in the matching class.')
                ids.add(rec['carId']); ranks.add(rec['rank'])
                _copy(rec['summary'], 'summary')
                for field in ('drivingCharacteristics', 'driverType'):
                    _copy(rec[field], field, nullable=True)
                evidence = rec['evidence']
                _object(evidence, Evidence.__annotations__, 'evidence')
                _text(evidence['gameVersion'], 'evidence.gameVersion', nullable=True)
                for field in ('trackCharacteristics', 'bop', 'recentPerformance'):
                    _copy(evidence[field], 'evidence.' + field, nullable=True)
                _sources(evidence['sources'], 'evidence.sources')
        if not isinstance(event['strategy'], list) or len(event['strategy']) > 30:
            raise ValueError('strategy: expected up to 30 per-car estimates.')
        strategy_cars = set()
        for strategy in event['strategy']:
            _object(strategy, Strategy.__annotations__, 'strategy')
            _car(strategy['carId'], event, 'strategy.carId')
            if strategy['carId'] in strategy_cars:
                raise ValueError('strategy: duplicate car.')
            strategy_cars.add(strategy['carId'])
            _object(strategy['inputs'], StrategyInputs.__annotations__, 'inputs')
            for field, bounds in INPUT_BOUNDS.items():
                _number(strategy['inputs'][field], bounds, 'inputs.' + field)
            if event['durationMinutes'] is not None and strategy['inputs']['minutes'] != event['durationMinutes']:
                raise ValueError('Strategy duration must match the published race duration.')
            for field in Strategy.__annotations__:
                if field not in ('carId', 'inputs', 'sources'):
                    _copy(strategy[field], field, nullable=field != 'calculationNotes')
            _sources(strategy['sources'], 'strategy.sources')
    return data


def read_calendar(path: Path) -> Calendar:
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Calendar file exceeds 4 MiB.')
    return validate_calendar(json.loads(path.read_text(encoding='utf-8')))


def _atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def record_failure(root: Path, *, lock_owned: bool = False):
    """Serialize failed-file reports too; never disturb another writer's lock."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.update.lock'
    if not lock_owned:
        try:
            lock.mkdir()
        except FileExistsError:
            return
    try:
        _atomic_json(root / 'status.json', {'failed': True, 'attemptedAt': datetime.now(timezone.utc).isoformat()})
    finally:
        if not lock_owned:
            lock.rmdir()


def load_calendar(root: Path | None = None) -> dict:
    root = root or Path(os.environ.get('GTD_LMU_CALENDAR_DIR', DEFAULT_DIR))
    fallback = False
    current_unreadable = False
    data = None
    for index, path in enumerate([root / 'current.json', root / 'previous.json', *sorted((root / 'archive').glob('*.json'), reverse=True)]):
        try:
            candidate = read_calendar(path)
            if candidate['weekStart'] is None and index > 0:
                continue
            data = candidate; fallback = index > 0
            break
        except (OSError, ValueError, TypeError, OverflowError):
            if index == 0 and path.exists():
                current_unreadable = True
            continue
    try:
        failed = json.loads((root / 'status.json').read_text(encoding='utf-8')).get('failed') is True
    except (OSError, ValueError, AttributeError):
        failed = False
    data = data or empty_calendar()
    state = 'update-failed' if failed or fallback or current_unreadable else ('partial' if missing_fields(data) else ('ready' if data['events'] else 'empty'))
    stale = bool(data['weekEnd'] and date.fromisoformat(data['weekEnd']) < datetime.now(ZoneInfo(TIMEZONE)).date())
    return dict(data=data, state=state, fallback=fallback, stale=stale)


def publish_calendar(data: Calendar, root: Path = DEFAULT_DIR) -> bool:
    """Single-writer publication; validation failure leaves the current file intact."""
    root.mkdir(parents=True, exist_ok=True)
    lock = root / '.update.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('An update is already in progress; inspect .update.lock if a process crashed.') from None
    try:
        try:
            validate_calendar(data)
            encoded = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
            if len(encoded.encode('utf-8')) > 4 * 1024 * 1024:
                raise ValueError('Published calendar would exceed 4 MiB.')
            old = load_calendar(root)['data']
            try:
                current_valid = read_calendar(root / 'current.json') == data
            except (OSError, ValueError, TypeError, OverflowError):
                current_valid = False
            if current_valid:
                _atomic_json(root / 'status.json', {'failed': False})
                return False
            if old['weekStart']:
                if data['weekStart'] is None or data['weekStart'] < old['weekStart']:
                    raise ValueError('Do not replace a published calendar with an earlier or unpublished week.')
                if parse_timestamp(data['lastUpdated']) < parse_timestamp(old['lastUpdated']):
                    raise ValueError('lastUpdated cannot precede the current publication.')
                if data['weekStart'] != old['weekStart']:
                    archive = root / 'archive' / (old['weekStart'] + '.json')
                    if archive.exists():
                        if read_calendar(archive) != old:
                            raise ValueError('Week archive already exists with different data; it is immutable.')
                    else:
                        _atomic_json(archive, old)
                _atomic_json(root / 'previous.json', old)
            if not old['weekStart'] and data['weekStart']:
                _atomic_json(root / 'previous.json', data)
            _atomic_json(root / 'current.json', data)
            _atomic_json(root / 'status.json', {'failed': False})
            return True
        except (ValueError, TypeError, OSError, OverflowError):
            record_failure(root, lock_owned=True)
            raise
    finally:
        lock.rmdir()


def ordered_sessions(sessions: list[str]) -> list[str]:
    return sorted(sessions, key=parse_timestamp)


def missing_fields(data: Calendar) -> list[str]:
    missing = []
    for event in data['events']:
        prefix = event['id'] + ': '
        for field in ('layout', 'durationMinutes', 'eventLevel', 'weather', 'trackConditions'):
            if event[field] is None:
                missing.append(prefix + field)
        if not event['sessions']: missing.append(prefix + 'sessions')
        if not event['sources']: missing.append(prefix + 'official sources')
        for field, value in event['eligibility'].items():
            if value is None: missing.append(prefix + 'eligibility.' + field)
        for class_name in event['classes']:
            if not event['recommendedCars'].get(class_name): missing.append(prefix + class_name + ' recommendations')
            if class_name not in event['allowedCars']: missing.append(prefix + class_name + ' eligible cars')
    return missing
