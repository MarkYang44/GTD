"""Immutable, source-attributed content for the LMU circuit guide."""

from dataclasses import dataclass


GUIDE_UPDATED = "2026-08-30"
_LMU = "https://lemansultimate.com/"
_CAR_SOURCE_SLUGS = {
    "aston-martin-vantage-lmgt3": "aston-martin-vantage-amr-lmgt3",
}
_CIRCUIT_SOURCE_SLUGS = {
    "bahrain": "bahrain",
    "barcelona": "circuit-de-barcelona-catalunya",
    "le-mans": "circuit-de-la-sarthe",
    "paul-ricard": "circuit-paul-ricard",
    "cota": "cota",
    "daytona": "daytona-international-speedway",
    "fuji": "fuji",
    "imola": "imola",
    "interlagos": "interlagos",
    "lusail": "lusail-international",
    "monza": "monza",
    "portimao": "portimao",
    "sebring": "sebring",
    "silverstone-international": "silverstone-international",
    "spa": "spa",
    "laguna-seca": "weathertech-raceway-laguna-seca",
}


@dataclass(frozen=True, slots=True)
class Car:
    slug: str
    name: str
    car_class: str
    image: str
    source_url: str
    image_source_url: str
    strength: str
    caution: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    car_slug: str
    fit: str


@dataclass(frozen=True, slots=True)
class Circuit:
    slug: str
    name: str
    location: str
    length_km: str
    is_dlc: bool
    image: str
    source_url: str
    image_source_url: str
    character: str
    challenge: str
    advice: str
    lmgt3: tuple[Recommendation, Recommendation, Recommendation]
    hypercar: tuple[Recommendation, Recommendation, Recommendation]


def _car(
    slug: str,
    name: str,
    car_class: str,
    image_source_url: str,
    strength: str,
    caution: str,
) -> Car:
    return Car(
        slug=slug,
        name=name,
        car_class=car_class,
        image=f"kozekilmu/guide/cars/{slug}.webp",
        source_url=f"{_LMU}cars/{_CAR_SOURCE_SLUGS.get(slug, slug)}/",
        image_source_url=image_source_url,
        strength=strength,
        caution=caution,
    )


CARS: dict[str, Car] = {
    car.slug: car
    for car in (
        _car("aston-martin-vantage-lmgt3", "Aston Martin Vantage AMR LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Aston-3-1024x576.png", "compliant platform and calm braking", "can lean into safe understeer"),
        _car("bmw-m4-lmgt3", "BMW M4 LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-09.42.22.99-1024x576.png", "stable, kerb-friendly front-engine balance", "front tyres punish overdriving"),
        _car("corvette-z06-lmgt3-r", "Corvette Z06 LMGT3.R", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-10.06.06.28-1024x576.png", "confident braking and predictable traction", "throttle rotation needs patience"),
        _car("ferrari-296-lmgt3", "Ferrari 296 LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/11/Ferrari-54-1-1024x576.png", "agile direction changes and balanced aero", "rough kerbs can unsettle it"),
        _car("ford-mustang-lmgt3", "Ford Mustang LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Le-Mans-Ultimate-Screenshot-2026.06.03-09.53.29.53-1024x576.png", "straight-line speed and accessible torque", "mass and front-tyre load show in tight sectors"),
        _car("lamborghini-huracan-lmgt3-evo2", "Lamborghini Huracan LMGT3 Evo2", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.22-17.33.23.00-1024x576.png", "fast response in flowing corners", "rear movement requires smooth inputs"),
        _car("lexus-rc-f-lmgt3", "Lexus RC F LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.20-12.33.09.16-1024x576.png", "reassuring stability and usable V8 delivery", "slower rotation in very tight changes"),
        _car("mclaren-720s-lmgt3-evo", "McLaren 720S LMGT3 Evo", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/11/McLaren-70-3-1024x576.png", "aero efficiency and high-speed confidence", "low-speed traction and tall kerbs need care"),
        _car("porsche-911-gt3-r", "Porsche 911 GT3 R LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Lm100-Screenshot-2025.02.13-13.57.39.75-1024x576.png", "traction and rotation from the rear-engine layout", "trail braking can provoke the rear"),
        _car("alpine-a424", "Alpine A424", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/09/Alpine-Solo-LM-19-1024x576.png", "compact, nimble response", "braking stability is setup-sensitive"),
        _car("bmw-m-hybrid-v8", "BMW M Hybrid V8", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.47.35.97-1024x576.png", "stable platform and kerb confidence", "needs patience to rotate in slow corners"),
        _car("cadillac-v-series-r", "Cadillac V-Series.R", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/le-mans-ultimate.exe-Screenshot-2025.07.15-14.16.55.62-1024x576.png", "strong braking and mechanical traction", "torque can stress the rear tyres"),
        _car("ferrari-499p", "Ferrari 499P", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.55.45.94-1024x576.png", "aero performance and decisive rotation", "rewards precise inputs more than corrections"),
        _car("peugeot-9x8-2024", "Peugeot 9X8 2024", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.20.35.91-1024x576.png", "agile modern aero package", "balance is sensitive to setup and kerb use"),
        _car("porsche-963", "Porsche 963", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Porsche-963-2-1024x576.png", "broad, approachable operating window", "tyre temperature still needs monitoring"),
        _car("toyota-gr010-hybrid", "Toyota GR010-Hybrid", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-12.31.24.88-1024x576.png", "stability, traction, and endurance-friendly behaviour", "slower rotation can cost time in tight sectors"),
    )
}


def _recommend(car_slug: str, fit: str) -> Recommendation:
    return Recommendation(car_slug, fit)


def _circuit(
    slug: str,
    name: str,
    location: str,
    length_km: str,
    is_dlc: bool,
    image_source_url: str,
    character: str,
    challenge: str,
    advice: str,
    lmgt3: tuple[Recommendation, Recommendation, Recommendation],
    hypercar: tuple[Recommendation, Recommendation, Recommendation],
) -> Circuit:
    return Circuit(
        slug=slug,
        name=name,
        location=location,
        length_km=length_km,
        is_dlc=is_dlc,
        image=f"kozekilmu/guide/tracks/{slug}.webp",
        source_url=f"{_LMU}circuit/{_CIRCUIT_SOURCE_SLUGS[slug]}/",
        image_source_url=image_source_url,
        character=character,
        challenge=challenge,
        advice=advice,
        lmgt3=lmgt3,
        hypercar=hypercar,
    )


CIRCUITS: tuple[Circuit, ...] = (
    _circuit("bahrain", "Bahrain", "Sakhir, Bahrain", "5.412", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Bahrain-20-1-1024x576.png", "Heavy stops, low-speed traction, and rear-tyre management.", "Repeated braking zones make exits and rear temperatures matter through a stint.", "Brake in a straight line, release the pedal patiently, and protect the rear tyres on exit.", (_recommend("bmw-m4-lmgt3", "Its stable, kerb-friendly balance keeps Bahrain's heavy stops calm."), _recommend("corvette-z06-lmgt3-r", "Confident braking and predictable traction suit Bahrain's slow exits."), _recommend("lexus-rc-f-lmgt3", "Reassuring stability supports rear-tyre management after Bahrain's heavy stops.")), (_recommend("toyota-gr010-hybrid", "Its stable traction-oriented behaviour fits Bahrain's slow exits and long stints."), _recommend("cadillac-v-series-r", "Strong braking and mechanical traction help at Bahrain's repeated heavy stops."), _recommend("porsche-963", "Its broad operating window makes Bahrain's rear-tyre management approachable."))),
    _circuit("barcelona", "Circuit de Barcelona-Catalunya", "Montmeló, Spain", "4.657", True, "https://lemansultimate.com/wp-content/uploads/2026/07/Barca-11-1024x576.png", "Long loaded corners plus a mixed technical final sector.", "Sustained lateral load tests tyre balance before the slower final sequence.", "Keep steering inputs tidy in the loaded turns, then prioritize a clean final-sector exit.", (_recommend("ferrari-296-lmgt3", "Agile direction changes and balanced aero suit Barcelona's loaded corners."), _recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence helps through Barcelona's long loaded turns."), _recommend("porsche-911-gt3-r", "Rear-engine traction helps the technical final sector after loaded corners.")), (_recommend("ferrari-499p", "Aero performance and decisive rotation fit Barcelona's long loaded corners."), _recommend("peugeot-9x8-2024", "Its agile aero package responds well to Barcelona's mixed final sector."), _recommend("porsche-963", "The broad operating window supports Barcelona's sustained tyre load."))),
    _circuit("le-mans", "Circuit de la Sarthe", "Le Mans, France", "13.626", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Desktop-Screenshot-2024.01.30-13.22.32.90-1024x576.png", "Low drag, extreme braking zones, and long full-throttle runs.", "Stability under the biggest stops must coexist with efficient straight-line running.", "Use conservative braking references in traffic and preserve momentum onto each long straight.", (_recommend("ford-mustang-lmgt3", "Straight-line speed and accessible torque serve Le Mans' long full-throttle runs."), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency gives confidence while minimizing drag on Le Mans' straights."), _recommend("ferrari-296-lmgt3", "Balanced aero helps link Le Mans' extreme braking zones to fast changes.")), (_recommend("cadillac-v-series-r", "Strong braking supports Le Mans' extreme stops before long straights."), _recommend("porsche-963", "Its broad window is reassuring across Le Mans' long, changing lap."), _recommend("ferrari-499p", "Aero performance suits the low-drag and high-speed demands of Le Mans."))),
    _circuit("paul-ricard", "Circuit Paul Ricard", "Le Castellet, France", "5.842", True, "https://lemansultimate.com/wp-content/uploads/2025/12/PaulRicard_1-1024x576.jpg", "Mistral straight, Signes commitment, and a technical final sector.", "The lap swings from straight-line efficiency to high-speed commitment and slow rotation.", "Build confidence progressively through Signes, then brake early enough to organize the final sector.", (_recommend("mclaren-720s-lmgt3-evo", "Aero efficiency and high-speed confidence suit the Mistral and Signes."), _recommend("ferrari-296-lmgt3", "Balanced aero and agile changes help Paul Ricard's technical final sector."), _recommend("porsche-911-gt3-r", "Rear-engine traction helps launch from Paul Ricard's slower final corners.")), (_recommend("peugeot-9x8-2024", "Its agile aero package fits Signes commitment and the technical final sector."), _recommend("ferrari-499p", "Aero performance supports Paul Ricard's fast Signes sequence."), _recommend("alpine-a424", "Compact response helps rotate through Paul Ricard's technical final sector."))),
    _circuit("cota", "Circuit of the Americas", "Austin, United States", "5.513", True, "https://lemansultimate.com/wp-content/uploads/2024/09/Desktop-Screenshot-2024.08.29-10.14.03.02-1-1024x576.png", "Uphill braking, fast esses, and slow traction zones.", "The opening climb and esses punish unstable braking, while slow exits reward patience.", "Place the car early uphill, use smooth direction changes in the esses, and square slow exits.", (_recommend("bmw-m4-lmgt3", "Stable kerb-friendly balance helps COTA's uphill braking and fast esses."), _recommend("corvette-z06-lmgt3-r", "Confident braking and traction match COTA's uphill stops and slow exits."), _recommend("ferrari-296-lmgt3", "Agile direction changes suit COTA's fast esses and mixed-speed flow.")), (_recommend("porsche-963", "Its approachable operating window helps COTA's mixed braking and esses."), _recommend("cadillac-v-series-r", "Strong braking and traction support COTA's uphill stops and slow zones."), _recommend("ferrari-499p", "Decisive rotation works through COTA's fast esses when inputs stay precise."))),
    _circuit("daytona", "Daytona International Speedway", "Daytona Beach, United States", "5.729", True, "https://lemansultimate.com/wp-content/uploads/2026/07/Daytona-11-1024x576.png", "Banking efficiency, infield traction, and Bus Stop stability.", "Drafting and banking reward efficiency, but the infield and Bus Stop punish abrupt inputs.", "Carry clean speed through banking, then settle the car before the Bus Stop kerbs.", (_recommend("ford-mustang-lmgt3", "Straight-line speed and accessible torque help Daytona's banking efficiency."), _recommend("bmw-m4-lmgt3", "Stable kerb-friendly balance keeps Daytona's Bus Stop composed."), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency supports Daytona banking while retaining high-speed confidence.")), (_recommend("cadillac-v-series-r", "Strong braking and traction fit Daytona's infield and Bus Stop approach."), _recommend("porsche-963", "Its broad operating window keeps Daytona's banking and infield manageable."), _recommend("bmw-m-hybrid-v8", "Kerb confidence helps stabilize the Daytona Bus Stop."))),
    _circuit("fuji", "Fuji Speedway", "Oyama, Japan", "4.563", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Fuji-8-1-1024x576.png", "A very long straight followed by a slow technical third sector.", "The straight demands exit speed, then the final sector needs controlled rotation and traction.", "Protect the exit onto the straight, then slow the hands down for the technical third sector.", (_recommend("bmw-m4-lmgt3", "Stable front-engine balance helps Fuji's braking after the very long straight."), _recommend("porsche-911-gt3-r", "Rear-engine traction supports Fuji's slow technical-sector exits."), _recommend("corvette-z06-lmgt3-r", "Predictable traction fits Fuji's transition from the straight to slow corners.")), (_recommend("toyota-gr010-hybrid", "Stability and traction suit Fuji's long-straight braking and slow sector."), _recommend("porsche-963", "Its broad operating window helps manage Fuji's contrasting sectors."), _recommend("cadillac-v-series-r", "Strong braking is useful at the end of Fuji's very long straight."))),
    _circuit("imola", "Imola", "Imola, Italy", "4.909", True, "https://lemansultimate.com/wp-content/uploads/2024/07/Imola-Statics-1-1-1024x576.png", "Narrow rhythm, tall kerbs, repeated braking, and traction.", "Limited width magnifies mistakes while tall kerbs challenge braking and composure.", "Respect the kerbs, place the car early, and sacrifice entry speed for traction.", (_recommend("porsche-911-gt3-r", "Rear-engine traction suits Imola's repeated braking and narrow exits."), _recommend("bmw-m4-lmgt3", "Kerb-friendly balance helps absorb Imola's tall kerbs."), _recommend("aston-martin-vantage-lmgt3", "Calm braking supports Imola's narrow rhythm and repeated stops.")), (_recommend("porsche-963", "Its broad operating window helps keep Imola's narrow rhythm manageable."), _recommend("bmw-m-hybrid-v8", "Stable kerb confidence fits Imola's tall kerbs and repeated braking."), _recommend("toyota-gr010-hybrid", "Stability and traction reward careful exits on Imola's narrow layout."))),
    _circuit("interlagos", "Interlagos", "São Paulo, Brazil", "4.309", True, "https://lemansultimate.com/wp-content/uploads/2024/11/Interlagos-1-1024x576.png", "Elevation, a short lap, mixed-speed corners, and traction exits.", "Compressed lap time makes every traction exit and elevation change highly visible.", "Prioritize exits over aggressive entries and keep the platform settled over crests.", (_recommend("ferrari-296-lmgt3", "Agile direction changes suit Interlagos' mixed-speed elevation changes."), _recommend("porsche-911-gt3-r", "Rear-engine traction helps Interlagos' repeated traction exits."), _recommend("corvette-z06-lmgt3-r", "Predictable traction supports Interlagos' short lap and slow exits.")), (_recommend("ferrari-499p", "Decisive rotation fits Interlagos' mixed-speed elevation changes."), _recommend("porsche-963", "Its broad window helps keep Interlagos' short, changing lap composed."), _recommend("cadillac-v-series-r", "Mechanical traction serves Interlagos' frequent traction exits."))),
    _circuit("lusail", "Lusail International Circuit", "Lusail, Qatar", "5.419", True, "https://lemansultimate.com/wp-content/uploads/2025/05/Qatar2-1024x576.jpg", "Sustained medium/high-speed load and tyre temperature.", "Long loaded sequences expose tyre temperature and balance over a full stint.", "Avoid sliding the loaded tyres, keep steering corrections small, and watch temperatures.", (_recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence suits Lusail's sustained medium-speed load."), _recommend("ferrari-296-lmgt3", "Balanced aero supports Lusail's long loaded corners and tyre control."), _recommend("lamborghini-huracan-lmgt3-evo2", "Fast response helps Lusail's flowing medium/high-speed sequence with smooth inputs.")), (_recommend("ferrari-499p", "Aero performance fits Lusail's sustained high-speed tyre load."), _recommend("peugeot-9x8-2024", "Its agile aero package suits Lusail's flowing medium-speed sections."), _recommend("alpine-a424", "Compact response helps manage Lusail's long loaded sequences."))),
    _circuit("monza", "Monza", "Monza, Italy", "5.793", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Monza-21-1024x576.png", "Maximum speed, heavy chicane braking, and aggressive kerbs.", "Top speed matters, but the chicanes demand stable braking and measured kerb use.", "Brake straight, do not attack every kerb, and prioritize exits onto the long straights.", (_recommend("ford-mustang-lmgt3", "Straight-line speed and torque suit Monza's maximum-speed focus."), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency supports Monza's long straights and fast approaches."), _recommend("ferrari-296-lmgt3", "Balanced aero helps stabilize Monza's heavy chicane braking.")), (_recommend("cadillac-v-series-r", "Strong braking supports Monza's heavy chicane stops."), _recommend("porsche-963", "Its approachable window helps manage Monza's kerbs and braking."), _recommend("ferrari-499p", "Aero performance pairs with Monza's maximum-speed, heavy-braking layout."))),
    _circuit("portimao", "Portimão", "Portimão, Portugal", "4.653", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Portimao-7-1-1024x576.png", "Blind crests, compression, rotation, and traction.", "Sightlines vanish over crests, and compression tests balance before traction-critical exits.", "Use repeatable references over blind crests and delay throttle until the car is settled.", (_recommend("porsche-911-gt3-r", "Rear-engine traction helps Portimão's blind-crest exits and rotation."), _recommend("ferrari-296-lmgt3", "Agile direction changes fit Portimão's compression and changing rhythm."), _recommend("mclaren-720s-lmgt3-evo", "High-speed confidence supports Portimão's blind crests when inputs stay smooth.")), (_recommend("ferrari-499p", "Decisive rotation suits Portimão's compression and blind crests."), _recommend("alpine-a424", "Compact response helps rotate through Portimão's changing elevations."), _recommend("peugeot-9x8-2024", "Its agile aero package fits Portimão's crests and flowing changes."))),
    _circuit("sebring", "Sebring International Raceway", "Sebring, United States", "6.019", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Sebring-13-1-1024x576.png", "Bumps, rough braking surfaces, and traction over concrete seams.", "Surface movement disrupts braking references and asks for a platform that tolerates bumps.", "Leave margin over the worst seams, brake progressively, and let the car move underneath you.", (_recommend("bmw-m4-lmgt3", "Kerb-friendly stable balance helps Sebring's bumps and concrete seams."), _recommend("aston-martin-vantage-lmgt3", "A compliant platform and calm braking suit Sebring's rough braking surfaces."), _recommend("corvette-z06-lmgt3-r", "Predictable traction helps Sebring's concrete seams and slow exits.")), (_recommend("cadillac-v-series-r", "Strong braking and mechanical traction support Sebring's rough surfaces."), _recommend("porsche-963", "Its broad operating window helps manage Sebring's bumps over a stint."), _recommend("bmw-m-hybrid-v8", "Stable platform and kerb confidence fit Sebring's concrete seams."))),
    _circuit("silverstone-international", "Silverstone International", "Silverstone, United Kingdom", "2.979", True, "https://lemansultimate.com/wp-content/uploads/2025/09/le-mans-ultimate.exe-Screenshot-2025.09.24-11.03.48.85-1024x576.png", "Compact lap, frequent traffic, and repeated direction changes.", "Short lap traffic leaves little recovery time, while repeated changes reward a responsive platform.", "Plan passes early, preserve exit speed, and make one clean steering input per change.", (_recommend("mclaren-720s-lmgt3-evo", "High-speed confidence and aero efficiency suit Silverstone's repeated direction changes."), _recommend("ferrari-296-lmgt3", "Agile direction changes help in Silverstone International's compact traffic flow."), _recommend("bmw-m4-lmgt3", "Stable balance gives predictable references amid Silverstone's frequent traffic.")), (_recommend("ferrari-499p", "Decisive rotation fits Silverstone's compact repeated changes."), _recommend("porsche-963", "Its approachable window helps manage traffic on Silverstone's short lap."), _recommend("peugeot-9x8-2024", "Agile aero response supports Silverstone's quick direction changes."))),
    _circuit("spa", "Spa-Francorchamps", "Stavelot, Belgium", "7.004", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Spa-11-1024x576.png", "High-speed aero, elevation, a long lap, and variable weather.", "Commitment through elevation changes must be balanced against weather and tyre variation.", "Build speed gradually in changing conditions and leave margin at the high-speed compressions.", (_recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence suits Spa's elevation and fast aero sections."), _recommend("ferrari-296-lmgt3", "Balanced aero and agile changes fit Spa's long, variable lap."), _recommend("bmw-m4-lmgt3", "Stable balance provides predictable behaviour as Spa weather changes.")), (_recommend("ferrari-499p", "Aero performance and decisive rotation fit Spa's high-speed elevation changes."), _recommend("porsche-963", "Its broad operating window helps through Spa's long lap and weather shifts."), _recommend("cadillac-v-series-r", "Strong braking and traction support Spa's mixed high-speed and wet transitions."))),
    _circuit("laguna-seca", "WeatherTech Raceway Laguna Seca", "Monterey, United States", "3.602", True, "https://lemansultimate.com/wp-content/uploads/2026/07/1920x1080LAG_3-1024x576.jpg", "Low-speed traction, elevation, and the Corkscrew sequence.", "The Corkscrew drops away quickly, so the car must rotate without compromising the next exit.", "Brake early over the crest, use one smooth rotation at the Corkscrew, and protect traction.", (_recommend("porsche-911-gt3-r", "Rear-engine traction helps Laguna Seca's low-speed exits and Corkscrew recovery."), _recommend("corvette-z06-lmgt3-r", "Predictable traction and braking suit Laguna Seca's elevation changes."), _recommend("bmw-m4-lmgt3", "Stable balance helps the braking and kerb approach to the Corkscrew.")), (_recommend("porsche-963", "Its broad operating window keeps Laguna Seca's Corkscrew sequence approachable."), _recommend("cadillac-v-series-r", "Strong braking and traction help at Laguna Seca's low-speed elevation changes."), _recommend("bmw-m-hybrid-v8", "Kerb confidence and stability support the Corkscrew approach."))),
)


def _is_local_guide_image(path: str, resource: str) -> bool:
    return (
        path.startswith(f"kozekilmu/guide/{resource}/")
        and path.endswith(".webp")
        and not path.startswith("/")
        and ".." not in path.split("/")
    )


def _is_lmu_url(url: str) -> bool:
    return url.startswith(_LMU)


def validate_guide_data() -> None:
    """Raise ValueError when the static guide contract is invalid."""
    car_slugs = tuple(CARS)
    if len(car_slugs) != len(set(car_slugs)) or any(key != car.slug for key, car in CARS.items()):
        raise ValueError("duplicate or mismatched car slug")

    for car in CARS.values():
        if car.car_class not in {"LMGT3", "Hypercar"}:
            raise ValueError(f"unsupported car class: {car.slug}")
        if not all((car.name.strip(), car.strength.strip(), car.caution.strip())):
            raise ValueError(f"blank car copy: {car.slug}")
        if not _is_local_guide_image(car.image, "cars"):
            raise ValueError(f"non-local car image: {car.slug}")
        if not _is_lmu_url(car.source_url) or not _is_lmu_url(car.image_source_url):
            raise ValueError(f"non-LMU car source: {car.slug}")

    circuit_slugs = tuple(circuit.slug for circuit in CIRCUITS)
    if len(circuit_slugs) != len(set(circuit_slugs)):
        raise ValueError("duplicate circuit slug")

    for circuit in CIRCUITS:
        if not all((circuit.name.strip(), circuit.location.strip(), circuit.length_km.strip(), circuit.character.strip(), circuit.challenge.strip(), circuit.advice.strip())):
            raise ValueError(f"blank circuit copy: {circuit.slug}")
        if not _is_local_guide_image(circuit.image, "tracks"):
            raise ValueError(f"non-local circuit image: {circuit.slug}")
        if not _is_lmu_url(circuit.source_url) or not _is_lmu_url(circuit.image_source_url):
            raise ValueError(f"non-LMU circuit source: {circuit.slug}")
        for recommendations, expected_class in ((circuit.lmgt3, "LMGT3"), (circuit.hypercar, "Hypercar")):
            if len(recommendations) != 3:
                raise ValueError(f"wrong recommendation count: {circuit.slug}")
            slugs = tuple(recommendation.car_slug for recommendation in recommendations)
            if len(slugs) != len(set(slugs)):
                raise ValueError(f"duplicate recommendation: {circuit.slug}")
            for recommendation in recommendations:
                if not recommendation.fit.strip():
                    raise ValueError(f"blank recommendation copy: {circuit.slug}")
                car = CARS.get(recommendation.car_slug)
                if car is None:
                    raise ValueError(f"missing recommended car: {recommendation.car_slug}")
                if car.car_class != expected_class:
                    raise ValueError(f"class mismatch: {recommendation.car_slug}")


validate_guide_data()
