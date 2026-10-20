"""Read-only source review metadata for the circuit guide and car catalog."""
from lmu_practice_data import CAR_NOTES, TRACK_NOTES, CHECKED_ON, GAME_CHECKED_ON, GAME_REFERENCE, GAME_SOURCE

RECOMMENDATION_REVIEWS = {}


def recommendation_review(circuit, car):
    result = dict(applicable_version=None, evidence_url=None, checked_on=CHECKED_ON,
                  sources=[circuit.source_url, CAR_NOTES[car.slug]['source_url']])
    result.update(RECOMMENDATION_REVIEWS.get(f'{circuit.slug}:{car.slug}', {}))
    return result


def sleeper_review(circuit, car, class_name):
    result = dict(applicable_version=None, evidence_url=None, checked_on=GAME_CHECKED_ON,
                  sources=[circuit.source_url, CAR_NOTES[car.slug]['source_url']])
    result.update(RECOMMENDATION_REVIEWS.get(f'sleeper:{circuit.slug}:{class_name.lower()}', {}))
    return result


def template_context():
    return dict(car_notes=CAR_NOTES, track_notes=TRACK_NOTES,
                recommendation_review=recommendation_review, sleeper_review=sleeper_review,
                game_reference=GAME_REFERENCE, game_source=GAME_SOURCE, game_checked_on=GAME_CHECKED_ON)
