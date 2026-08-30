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
    strength_zh: str
    caution_zh: str


@dataclass(frozen=True, slots=True)
class Recommendation:
    car_slug: str
    fit: str
    fit_zh: str


@dataclass(frozen=True, slots=True)
class Circuit:
    slug: str
    name: str
    location: str
    location_zh: str
    length_km: str
    is_dlc: bool
    image: str
    source_url: str
    image_source_url: str
    character: str
    character_zh: str
    challenge: str
    challenge_zh: str
    advice: str
    advice_zh: str
    lmgt3: tuple[Recommendation, Recommendation, Recommendation]
    hypercar: tuple[Recommendation, Recommendation, Recommendation]


def _car(
    slug: str,
    name: str,
    car_class: str,
    image_source_url: str,
    strength: str,
    caution: str,
    strength_zh: str,
    caution_zh: str,
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
        strength_zh=strength_zh,
        caution_zh=caution_zh,
    )


CARS: dict[str, Car] = {
    car.slug: car
    for car in (
        _car("aston-martin-vantage-lmgt3", "Aston Martin Vantage AMR LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Aston-3-1024x576.png", "compliant platform and calm braking", "can lean into safe understeer", "平台循规蹈矩，制动动作平和", "可以放心地带着安全转向不足驾驶"),
        _car("bmw-m4-lmgt3", "BMW M4 LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-09.42.22.99-1024x576.png", "stable, kerb-friendly front-engine balance", "front tyres punish overdriving", "稳定的前置引擎平衡，兼容路肩（kerb）", "前轮会惩罚过度驾驶"),
        _car("corvette-z06-lmgt3-r", "Corvette Z06 LMGT3.R", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/12/Le-Mans-Ultimate-Screenshot-2026.06.03-10.06.06.28-1024x576.png", "confident braking and predictable traction", "throttle rotation needs patience", "制动信心足，牵引力（traction）可预测", "需要耐心用油门带动车尾转向"),
        _car("ferrari-296-lmgt3", "Ferrari 296 LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/11/Ferrari-54-1-1024x576.png", "agile direction changes and balanced aero", "rough kerbs can unsettle it", "方向变化灵活，空气动力学平衡", "粗暴路肩可能打乱车身"),
        _car("ford-mustang-lmgt3", "Ford Mustang LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Le-Mans-Ultimate-Screenshot-2026.06.03-09.53.29.53-1024x576.png", "straight-line speed and accessible torque", "mass and front-tyre load show in tight sectors", "直线速度快，扭矩易于掌控", "车重和前轮负荷在紧凑路段很明显"),
        _car("lamborghini-huracan-lmgt3-evo2", "Lamborghini Huracan LMGT3 Evo2", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.22-17.33.23.00-1024x576.png", "fast response in flowing corners", "rear movement requires smooth inputs", "连续弯反应迅速", "尾部动态需要平顺操作"),
        _car("lexus-rc-f-lmgt3", "Lexus RC F LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/06/le-mans-ultimate.exe-Screenshot-2025.05.20-12.33.09.16-1024x576.png", "reassuring stability and usable V8 delivery", "slower rotation in very tight changes", "稳定感令人安心，V8 输出易用", "极紧凑的方向变化中转向较慢"),
        _car("mclaren-720s-lmgt3-evo", "McLaren 720S LMGT3 Evo", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2024/11/McLaren-70-3-1024x576.png", "aero efficiency and high-speed confidence", "low-speed traction and tall kerbs need care", "空气动力学效率（aero efficiency）高，高速信心足", "低速牵引力和高路肩需要小心"),
        _car("porsche-911-gt3-r", "Porsche 911 GT3 R LMGT3", "LMGT3", "https://lemansultimate.com/wp-content/uploads/2025/02/Lm100-Screenshot-2025.02.13-13.57.39.75-1024x576.png", "traction and rotation from the rear-engine layout", "trail braking can provoke the rear", "后置引擎带来牵引力（traction）和转向", "循迹刹车（trail braking）可能激发车尾"),
        _car("alpine-a424", "Alpine A424", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/09/Alpine-Solo-LM-19-1024x576.png", "compact, nimble response", "braking stability is setup-sensitive", "车身紧凑，反应灵活", "制动稳定性（braking stability）取决于调校（setup）"),
        _car("bmw-m-hybrid-v8", "BMW M Hybrid V8", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.47.35.97-1024x576.png", "stable platform and kerb confidence", "needs patience to rotate in slow corners", "平台稳定，过路肩有信心", "低速弯需要耐心让车转起来"),
        _car("cadillac-v-series-r", "Cadillac V-Series.R", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/le-mans-ultimate.exe-Screenshot-2025.07.15-14.16.55.62-1024x576.png", "strong braking and mechanical traction", "torque can stress the rear tyres", "制动强，机械牵引力（traction）好", "扭矩可能增加后轮负荷"),
        _car("ferrari-499p", "Ferrari 499P", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.55.45.94-1024x576.png", "aero performance and decisive rotation", "rewards precise inputs more than corrections", "空气动力学性能和果断转向", "比起修正动作，更奖励精准操作"),
        _car("peugeot-9x8-2024", "Peugeot 9X8 2024", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-10.20.35.91-1024x576.png", "agile modern aero package", "balance is sensitive to setup and kerb use", "现代化空气动力学套件灵活", "平衡对调校（setup）和路肩使用敏感"),
        _car("porsche-963", "Porsche 963", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Porsche-963-2-1024x576.png", "broad, approachable operating window", "tyre temperature still needs monitoring", "操作窗口（operating window）宽广，容易上手", "仍需监控轮胎温度"),
        _car("toyota-gr010-hybrid", "Toyota GR010-Hybrid", "Hypercar", "https://lemansultimate.com/wp-content/uploads/2024/02/Le-Mans-Ultimate-Screenshot-2026.06.03-12.31.24.88-1024x576.png", "stability, traction, and endurance-friendly behaviour", "slower rotation can cost time in tight sectors", "稳定、牵引力（traction）好，适合耐力赛节奏", "在紧凑路段转向较慢，可能损失时间"),
    )
}


def _recommend(car_slug: str, fit: str, fit_zh: str) -> Recommendation:
    return Recommendation(car_slug, fit, fit_zh)


def _circuit(
    slug: str,
    name: str,
    location: str,
    location_zh: str,
    length_km: str,
    is_dlc: bool,
    image_source_url: str,
    character: str,
    character_zh: str,
    challenge: str,
    challenge_zh: str,
    advice: str,
    advice_zh: str,
    lmgt3: tuple[Recommendation, Recommendation, Recommendation],
    hypercar: tuple[Recommendation, Recommendation, Recommendation],
) -> Circuit:
    return Circuit(
        slug=slug,
        name=name,
        location=location,
        location_zh=location_zh,
        length_km=length_km,
        is_dlc=is_dlc,
        image=f"kozekilmu/guide/tracks/{slug}.webp",
        source_url=f"{_LMU}circuit/{_CIRCUIT_SOURCE_SLUGS[slug]}/",
        image_source_url=image_source_url,
        character=character,
        character_zh=character_zh,
        challenge=challenge,
        challenge_zh=challenge_zh,
        advice=advice,
        advice_zh=advice_zh,
        lmgt3=lmgt3,
        hypercar=hypercar,
    )


CIRCUITS: tuple[Circuit, ...] = (
    _circuit("bahrain", "Bahrain", "Sakhir, Bahrain", "萨基尔，巴林（Sakhir, Bahrain）", "5.412", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Bahrain-20-1-1024x576.png", "Heavy stops, low-speed traction, and rear-tyre management.", "重刹区、低速牵引力（traction）和后轮胎管理。", "Repeated braking zones make exits and rear temperatures matter through a stint.", "连续制动区让出弯和后轮温度在一段赛程中都很关键。", "Brake in a straight line, release the pedal patiently, and protect the rear tyres on exit.", "保持直线制动，耐心松开踏板，出弯保护后轮。", (_recommend("bmw-m4-lmgt3", "Its stable, kerb-friendly balance keeps Bahrain's heavy stops calm.", "这款车稳定的前置引擎平衡，兼容路肩可应对Bahrain 的重刹区与后轮胎管理。"), _recommend("corvette-z06-lmgt3-r", "Confident braking and predictable traction suit Bahrain's slow exits.", "这款车制动信心足，牵引力（traction）可预测可应对Bahrain 的重刹区与后轮胎管理。"), _recommend("lexus-rc-f-lmgt3", "Reassuring stability supports rear-tyre management after Bahrain's heavy stops.", "这款车稳定感令人安心，V8 输出易用可应对Bahrain 的重刹区与后轮胎管理。")), (_recommend("toyota-gr010-hybrid", "Its stable traction-oriented behaviour fits Bahrain's slow exits and long stints.", "这款车稳定、牵引力（traction）好，适合耐力赛节奏可应对Bahrain 的重刹区与后轮胎管理。"), _recommend("cadillac-v-series-r", "Strong braking and mechanical traction help at Bahrain's repeated heavy stops.", "这款车制动强，机械牵引力（traction）好可应对Bahrain 的重刹区与后轮胎管理。"), _recommend("porsche-963", "Its broad operating window makes Bahrain's rear-tyre management approachable.", "这款车操作窗口（operating window）宽广，容易上手可应对Bahrain 的重刹区与后轮胎管理。"))),
    _circuit("barcelona", "Circuit de Barcelona-Catalunya", "Montmeló, Spain", "蒙特梅洛，西班牙（Montmeló, Spain）", "4.657", True, "https://lemansultimate.com/wp-content/uploads/2026/07/Barca-11-1024x576.png", "Long loaded corners plus a mixed technical final sector.", "长距离负荷弯，搭配技术性很强的末段。", "Sustained lateral load tests tyre balance before the slower final sequence.", "持续的横向负荷会在进入较慢末段前考验轮胎平衡。", "Keep steering inputs tidy in the loaded turns, then prioritize a clean final-sector exit.", "负荷弯里保持转向输入整洁，然后优先保证末段出弯干净。", (_recommend("ferrari-296-lmgt3", "Agile direction changes and balanced aero suit Barcelona's loaded corners.", "这款车方向变化灵活，空气动力学平衡可应对Barcelona 的长距离负荷弯。"), _recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence helps through Barcelona's long loaded turns.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Barcelona 的长距离负荷弯。"), _recommend("porsche-911-gt3-r", "Rear-engine traction helps the technical final sector after loaded corners.", "这款车后置引擎带来牵引力（traction）和转向可应对Barcelona 的长距离负荷弯。")), (_recommend("ferrari-499p", "Aero performance and decisive rotation fit Barcelona's long loaded corners.", "这款车空气动力学性能和果断转向可应对Barcelona 的长距离负荷弯。"), _recommend("peugeot-9x8-2024", "Its agile aero package responds well to Barcelona's mixed final sector.", "这款车现代化空气动力学套件灵活可应对Barcelona 的长距离负荷弯。"), _recommend("porsche-963", "The broad operating window supports Barcelona's sustained tyre load.", "这款车操作窗口（operating window）宽广，容易上手可应对Barcelona 的长距离负荷弯。"))),
    _circuit("le-mans", "Circuit de la Sarthe", "Le Mans, France", "勒芒，法国（Le Mans, France）", "13.626", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Desktop-Screenshot-2024.01.30-13.22.32.90-1024x576.png", "Low drag, extreme braking zones, and long full-throttle runs.", "低下压力、极重制动区和长距离全油门。", "Stability under the biggest stops must coexist with efficient straight-line running.", "最大制动时的稳定性必须和直道效率共存。", "Use conservative braking references in traffic and preserve momentum onto each long straight.", "交通中采用保守的制动参考点，并保持进入每条长直道的速度。", (_recommend("ford-mustang-lmgt3", "Straight-line speed and accessible torque serve Le Mans' long full-throttle runs.", "这款车直线速度快，扭矩易于掌控可应对Le Mans 的低下压力长直道。"), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency gives confidence while minimizing drag on Le Mans' straights.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Le Mans 的低下压力长直道。"), _recommend("ferrari-296-lmgt3", "Balanced aero helps link Le Mans' extreme braking zones to fast changes.", "这款车方向变化灵活，空气动力学平衡可应对Le Mans 的低下压力长直道。")), (_recommend("cadillac-v-series-r", "Strong braking supports Le Mans' extreme stops before long straights.", "这款车制动强，机械牵引力（traction）好可应对Le Mans 的低下压力长直道。"), _recommend("porsche-963", "Its broad window is reassuring across Le Mans' long, changing lap.", "这款车操作窗口（operating window）宽广，容易上手可应对Le Mans 的低下压力长直道。"), _recommend("ferrari-499p", "Aero performance suits the low-drag and high-speed demands of Le Mans.", "这款车空气动力学性能和果断转向可应对Le Mans 的低下压力长直道。"))),
    _circuit("paul-ricard", "Circuit Paul Ricard", "Le Castellet, France", "勒卡斯泰莱，法国（Le Castellet, France）", "5.842", True, "https://lemansultimate.com/wp-content/uploads/2025/12/PaulRicard_1-1024x576.jpg", "Mistral straight, Signes commitment, and a technical final sector.", "Mistral 直道、Signes 全力攻弯和技术末段。", "The lap swings from straight-line efficiency to high-speed commitment and slow rotation.", "单圈从直线效率切换到高速决心与低速转向。", "Build confidence progressively through Signes, then brake early enough to organize the final sector.", "逐步建立 Signes 的信心，之后提前制动来整理末段。", (_recommend("mclaren-720s-lmgt3-evo", "Aero efficiency and high-speed confidence suit the Mistral and Signes.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Paul Ricard 的高速 Signes 与技术末段。"), _recommend("ferrari-296-lmgt3", "Balanced aero and agile changes help Paul Ricard's technical final sector.", "这款车方向变化灵活，空气动力学平衡可应对Paul Ricard 的高速 Signes 与技术末段。"), _recommend("porsche-911-gt3-r", "Rear-engine traction helps launch from Paul Ricard's slower final corners.", "这款车后置引擎带来牵引力（traction）和转向可应对Paul Ricard 的高速 Signes 与技术末段。")), (_recommend("peugeot-9x8-2024", "Its agile aero package fits Signes commitment and the technical final sector.", "这款车现代化空气动力学套件灵活可应对Paul Ricard 的高速 Signes 与技术末段。"), _recommend("ferrari-499p", "Aero performance supports Paul Ricard's fast Signes sequence.", "这款车空气动力学性能和果断转向可应对Paul Ricard 的高速 Signes 与技术末段。"), _recommend("alpine-a424", "Compact response helps rotate through Paul Ricard's technical final sector.", "这款车车身紧凑，反应灵活可应对Paul Ricard 的高速 Signes 与技术末段。"))),
    _circuit("cota", "Circuit of the Americas", "Austin, United States", "奥斯汀，美国（Austin, United States）", "5.513", True, "https://lemansultimate.com/wp-content/uploads/2024/09/Desktop-Screenshot-2024.08.29-10.14.03.02-1-1024x576.png", "Uphill braking, fast esses, and slow traction zones.", "上坡制动、高速连续弯和低速牵引区。", "The opening climb and esses punish unstable braking, while slow exits reward patience.", "开局爬升和连续弯会惩罚不稳定制动，低速出弯则奖励耐心。", "Place the car early uphill, use smooth direction changes in the esses, and square slow exits.", "上坡提前放置车身，连续弯平顺变向，低速出弯尽量摆正车身。", (_recommend("bmw-m4-lmgt3", "Stable kerb-friendly balance helps COTA's uphill braking and fast esses.", "这款车稳定的前置引擎平衡，兼容路肩可应对COTA 的上坡制动与高速连续弯。"), _recommend("corvette-z06-lmgt3-r", "Confident braking and traction match COTA's uphill stops and slow exits.", "这款车制动信心足，牵引力（traction）可预测可应对COTA 的上坡制动与高速连续弯。"), _recommend("ferrari-296-lmgt3", "Agile direction changes suit COTA's fast esses and mixed-speed flow.", "这款车方向变化灵活，空气动力学平衡可应对COTA 的上坡制动与高速连续弯。")), (_recommend("porsche-963", "Its approachable operating window helps COTA's mixed braking and esses.", "这款车操作窗口（operating window）宽广，容易上手可应对COTA 的上坡制动与高速连续弯。"), _recommend("cadillac-v-series-r", "Strong braking and traction support COTA's uphill stops and slow zones.", "这款车制动强，机械牵引力（traction）好可应对COTA 的上坡制动与高速连续弯。"), _recommend("ferrari-499p", "Decisive rotation works through COTA's fast esses when inputs stay precise.", "这款车空气动力学性能和果断转向可应对COTA 的上坡制动与高速连续弯。"))),
    _circuit("daytona", "Daytona International Speedway", "Daytona Beach, United States", "代托纳比奇，美国（Daytona Beach, United States）", "5.729", True, "https://lemansultimate.com/wp-content/uploads/2026/07/Daytona-11-1024x576.png", "Banking efficiency, infield traction, and Bus Stop stability.", "高速倾斜弯效率、内场牵引力和 Bus Stop 稳定性。", "Drafting and banking reward efficiency, but the infield and Bus Stop punish abrupt inputs.", "跟车和倾斜弯奖励效率，但内场与 Bus Stop 会惩罚突兀操作。", "Carry clean speed through banking, then settle the car before the Bus Stop kerbs.", "在倾斜弯保持干净速度，进入 Bus Stop 路肩前先让车身稳定。", (_recommend("ford-mustang-lmgt3", "Straight-line speed and accessible torque help Daytona's banking efficiency.", "这款车直线速度快，扭矩易于掌控可应对Daytona 的倾斜弯与 Bus Stop。"), _recommend("bmw-m4-lmgt3", "Stable kerb-friendly balance keeps Daytona's Bus Stop composed.", "这款车稳定的前置引擎平衡，兼容路肩可应对Daytona 的倾斜弯与 Bus Stop。"), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency supports Daytona banking while retaining high-speed confidence.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Daytona 的倾斜弯与 Bus Stop。")), (_recommend("cadillac-v-series-r", "Strong braking and traction fit Daytona's infield and Bus Stop approach.", "这款车制动强，机械牵引力（traction）好可应对Daytona 的倾斜弯与 Bus Stop。"), _recommend("porsche-963", "Its broad operating window keeps Daytona's banking and infield manageable.", "这款车操作窗口（operating window）宽广，容易上手可应对Daytona 的倾斜弯与 Bus Stop。"), _recommend("bmw-m-hybrid-v8", "Kerb confidence helps stabilize the Daytona Bus Stop.", "这款车平台稳定，过路肩有信心可应对Daytona 的倾斜弯与 Bus Stop。"))),
    _circuit("fuji", "Fuji Speedway", "Oyama, Japan", "小山町，日本（Oyama, Japan）", "4.563", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Fuji-8-1-1024x576.png", "A very long straight followed by a slow technical third sector.", "超长直道，接着是低速技术性第三段。", "The straight demands exit speed, then the final sector needs controlled rotation and traction.", "直道要求出弯速度，末段则需要受控转向和牵引力。", "Protect the exit onto the straight, then slow the hands down for the technical third sector.", "保护通往直道的出弯，然后在技术性第三段放慢手上动作。", (_recommend("bmw-m4-lmgt3", "Stable front-engine balance helps Fuji's braking after the very long straight.", "这款车稳定的前置引擎平衡，兼容路肩可应对Fuji 的超长直道和低速技术路段。"), _recommend("porsche-911-gt3-r", "Rear-engine traction supports Fuji's slow technical-sector exits.", "这款车后置引擎带来牵引力（traction）和转向可应对Fuji 的超长直道和低速技术路段。"), _recommend("corvette-z06-lmgt3-r", "Predictable traction fits Fuji's transition from the straight to slow corners.", "这款车制动信心足，牵引力（traction）可预测可应对Fuji 的超长直道和低速技术路段。")), (_recommend("toyota-gr010-hybrid", "Stability and traction suit Fuji's long-straight braking and slow sector.", "这款车稳定、牵引力（traction）好，适合耐力赛节奏可应对Fuji 的超长直道和低速技术路段。"), _recommend("porsche-963", "Its broad operating window helps manage Fuji's contrasting sectors.", "这款车操作窗口（operating window）宽广，容易上手可应对Fuji 的超长直道和低速技术路段。"), _recommend("cadillac-v-series-r", "Strong braking is useful at the end of Fuji's very long straight.", "这款车制动强，机械牵引力（traction）好可应对Fuji 的超长直道和低速技术路段。"))),
    _circuit("imola", "Imola", "Imola, Italy", "伊莫拉，意大利（Imola, Italy）", "4.909", True, "https://lemansultimate.com/wp-content/uploads/2024/07/Imola-Statics-1-1-1024x576.png", "Narrow rhythm, tall kerbs, repeated braking, and traction.", "狭窄节奏、高路肩、反复制动和牵引力。", "Limited width magnifies mistakes while tall kerbs challenge braking and composure.", "赛道宽度有限会放大失误，高路肩也会考验制动与车身稳定。", "Respect the kerbs, place the car early, and sacrifice entry speed for traction.", "尊重路肩，提前放置车身，以入弯速度换取出弯牵引力。", (_recommend("porsche-911-gt3-r", "Rear-engine traction suits Imola's repeated braking and narrow exits.", "这款车后置引擎带来牵引力（traction）和转向可应对Imola 的高路肩与反复制动。"), _recommend("bmw-m4-lmgt3", "Kerb-friendly balance helps absorb Imola's tall kerbs.", "这款车稳定的前置引擎平衡，兼容路肩可应对Imola 的高路肩与反复制动。"), _recommend("aston-martin-vantage-lmgt3", "Calm braking supports Imola's narrow rhythm and repeated stops.", "这款车平台循规蹈矩，制动动作平和可应对Imola 的高路肩与反复制动。")), (_recommend("porsche-963", "Its broad operating window helps keep Imola's narrow rhythm manageable.", "这款车操作窗口（operating window）宽广，容易上手可应对Imola 的高路肩与反复制动。"), _recommend("bmw-m-hybrid-v8", "Stable kerb confidence fits Imola's tall kerbs and repeated braking.", "这款车平台稳定，过路肩有信心可应对Imola 的高路肩与反复制动。"), _recommend("toyota-gr010-hybrid", "Stability and traction reward careful exits on Imola's narrow layout.", "这款车稳定、牵引力（traction）好，适合耐力赛节奏可应对Imola 的高路肩与反复制动。"))),
    _circuit("interlagos", "Interlagos", "São Paulo, Brazil", "圣保罗，巴西（São Paulo, Brazil）", "4.309", True, "https://lemansultimate.com/wp-content/uploads/2024/11/Interlagos-1-1024x576.png", "Elevation, a short lap, mixed-speed corners, and traction exits.", "起伏、短单圈、中高速混合弯和出弯牵引力。", "Compressed lap time makes every traction exit and elevation change highly visible.", "紧凑单圈会放大每次牵引力出弯和地形起伏的影响。", "Prioritize exits over aggressive entries and keep the platform settled over crests.", "出弯优先于激进入弯，并在坡顶保持平台稳定。", (_recommend("ferrari-296-lmgt3", "Agile direction changes suit Interlagos' mixed-speed elevation changes.", "这款车方向变化灵活，空气动力学平衡可应对Interlagos 的地形起伏和牵引力出弯。"), _recommend("porsche-911-gt3-r", "Rear-engine traction helps Interlagos' repeated traction exits.", "这款车后置引擎带来牵引力（traction）和转向可应对Interlagos 的地形起伏和牵引力出弯。"), _recommend("corvette-z06-lmgt3-r", "Predictable traction supports Interlagos' short lap and slow exits.", "这款车制动信心足，牵引力（traction）可预测可应对Interlagos 的地形起伏和牵引力出弯。")), (_recommend("ferrari-499p", "Decisive rotation fits Interlagos' mixed-speed elevation changes.", "这款车空气动力学性能和果断转向可应对Interlagos 的地形起伏和牵引力出弯。"), _recommend("porsche-963", "Its broad window helps keep Interlagos' short, changing lap composed.", "这款车操作窗口（operating window）宽广，容易上手可应对Interlagos 的地形起伏和牵引力出弯。"), _recommend("cadillac-v-series-r", "Mechanical traction serves Interlagos' frequent traction exits.", "这款车制动强，机械牵引力（traction）好可应对Interlagos 的地形起伏和牵引力出弯。"))),
    _circuit("lusail", "Lusail International Circuit", "Lusail, Qatar", "卢赛尔，卡塔尔（Lusail, Qatar）", "5.419", True, "https://lemansultimate.com/wp-content/uploads/2025/05/Qatar2-1024x576.jpg", "Sustained medium/high-speed load and tyre temperature.", "持续中高速轮胎负荷（tyre load）和轮胎温度。", "Long loaded sequences expose tyre temperature and balance over a full stint.", "长距离负荷组合会暴露一段赛程里的轮胎温度与平衡。", "Avoid sliding the loaded tyres, keep steering corrections small, and watch temperatures.", "避免让负荷轮胎滑动，保持小幅转向修正，并监控温度。", (_recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence suits Lusail's sustained medium-speed load.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Lusail 的持续中高速负荷。"), _recommend("ferrari-296-lmgt3", "Balanced aero supports Lusail's long loaded corners and tyre control.", "这款车方向变化灵活，空气动力学平衡可应对Lusail 的持续中高速负荷。"), _recommend("lamborghini-huracan-lmgt3-evo2", "Fast response helps Lusail's flowing medium/high-speed sequence with smooth inputs.", "这款车连续弯反应迅速可应对Lusail 的持续中高速负荷。")), (_recommend("ferrari-499p", "Aero performance fits Lusail's sustained high-speed tyre load.", "这款车空气动力学性能和果断转向可应对Lusail 的持续中高速负荷。"), _recommend("peugeot-9x8-2024", "Its agile aero package suits Lusail's flowing medium-speed sections.", "这款车现代化空气动力学套件灵活可应对Lusail 的持续中高速负荷。"), _recommend("alpine-a424", "Compact response helps manage Lusail's long loaded sequences.", "这款车车身紧凑，反应灵活可应对Lusail 的持续中高速负荷。"))),
    _circuit("monza", "Monza", "Monza, Italy", "蒙扎，意大利（Monza, Italy）", "5.793", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Monza-21-1024x576.png", "Maximum speed, heavy chicane braking, and aggressive kerbs.", "最高速度、重刹减速弯和激进路肩。", "Top speed matters, but the chicanes demand stable braking and measured kerb use.", "最高速很重要，但减速弯需要稳定制动和克制的路肩使用。", "Brake straight, do not attack every kerb, and prioritize exits onto the long straights.", "直线制动，不要每个路肩都硬吃，优先保证驶上长直道的出弯。", (_recommend("ford-mustang-lmgt3", "Straight-line speed and torque suit Monza's maximum-speed focus.", "这款车直线速度快，扭矩易于掌控可应对Monza 的长直道与重刹减速弯。"), _recommend("mclaren-720s-lmgt3-evo", "Aero efficiency supports Monza's long straights and fast approaches.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Monza 的长直道与重刹减速弯。"), _recommend("ferrari-296-lmgt3", "Balanced aero helps stabilize Monza's heavy chicane braking.", "这款车方向变化灵活，空气动力学平衡可应对Monza 的长直道与重刹减速弯。")), (_recommend("cadillac-v-series-r", "Strong braking supports Monza's heavy chicane stops.", "这款车制动强，机械牵引力（traction）好可应对Monza 的长直道与重刹减速弯。"), _recommend("porsche-963", "Its approachable window helps manage Monza's kerbs and braking.", "这款车操作窗口（operating window）宽广，容易上手可应对Monza 的长直道与重刹减速弯。"), _recommend("ferrari-499p", "Aero performance pairs with Monza's maximum-speed, heavy-braking layout.", "这款车空气动力学性能和果断转向可应对Monza 的长直道与重刹减速弯。"))),
    _circuit("portimao", "Portimão", "Portimão, Portugal", "波尔蒂芒，葡萄牙（Portimão, Portugal）", "4.653", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Portimao-7-1-1024x576.png", "Blind crests, compression, rotation, and traction.", "盲顶、压缩、转向和牵引力。", "Sightlines vanish over crests, and compression tests balance before traction-critical exits.", "坡顶会遮挡视线，压缩段会在关键出弯前考验平衡。", "Use repeatable references over blind crests and delay throttle until the car is settled.", "在盲顶使用可重复的参考点，等车身稳定后再延后加油。", (_recommend("porsche-911-gt3-r", "Rear-engine traction helps Portimão's blind-crest exits and rotation.", "这款车后置引擎带来牵引力（traction）和转向可应对Portimão 的盲顶与压缩段。"), _recommend("ferrari-296-lmgt3", "Agile direction changes fit Portimão's compression and changing rhythm.", "这款车方向变化灵活，空气动力学平衡可应对Portimão 的盲顶与压缩段。"), _recommend("mclaren-720s-lmgt3-evo", "High-speed confidence supports Portimão's blind crests when inputs stay smooth.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Portimão 的盲顶与压缩段。")), (_recommend("ferrari-499p", "Decisive rotation suits Portimão's compression and blind crests.", "这款车空气动力学性能和果断转向可应对Portimão 的盲顶与压缩段。"), _recommend("alpine-a424", "Compact response helps rotate through Portimão's changing elevations.", "这款车车身紧凑，反应灵活可应对Portimão 的盲顶与压缩段。"), _recommend("peugeot-9x8-2024", "Its agile aero package fits Portimão's crests and flowing changes.", "这款车现代化空气动力学套件灵活可应对Portimão 的盲顶与压缩段。"))),
    _circuit("sebring", "Sebring International Raceway", "Sebring, United States", "赛百灵，美国（Sebring, United States）", "6.019", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Sebring-13-1-1024x576.png", "Bumps, rough braking surfaces, and traction over concrete seams.", "颠簸、粗糙制动路面和混凝土接缝上的牵引力。", "Surface movement disrupts braking references and asks for a platform that tolerates bumps.", "路面起伏会打乱制动参考，需要能容忍颠簸的操作平台。", "Leave margin over the worst seams, brake progressively, and let the car move underneath you.", "在最差接缝处留余量，渐进制动，让车在你身下自由活动。", (_recommend("bmw-m4-lmgt3", "Kerb-friendly stable balance helps Sebring's bumps and concrete seams.", "这款车稳定的前置引擎平衡，兼容路肩可应对Sebring 的颠簸路面与混凝土接缝。"), _recommend("aston-martin-vantage-lmgt3", "A compliant platform and calm braking suit Sebring's rough braking surfaces.", "这款车平台循规蹈矩，制动动作平和可应对Sebring 的颠簸路面与混凝土接缝。"), _recommend("corvette-z06-lmgt3-r", "Predictable traction helps Sebring's concrete seams and slow exits.", "这款车制动信心足，牵引力（traction）可预测可应对Sebring 的颠簸路面与混凝土接缝。")), (_recommend("cadillac-v-series-r", "Strong braking and mechanical traction support Sebring's rough surfaces.", "这款车制动强，机械牵引力（traction）好可应对Sebring 的颠簸路面与混凝土接缝。"), _recommend("porsche-963", "Its broad operating window helps manage Sebring's bumps over a stint.", "这款车操作窗口（operating window）宽广，容易上手可应对Sebring 的颠簸路面与混凝土接缝。"), _recommend("bmw-m-hybrid-v8", "Stable platform and kerb confidence fit Sebring's concrete seams.", "这款车平台稳定，过路肩有信心可应对Sebring 的颠簸路面与混凝土接缝。"))),
    _circuit("silverstone-international", "Silverstone International", "Silverstone, United Kingdom", "银石，英国（Silverstone, United Kingdom）", "2.979", True, "https://lemansultimate.com/wp-content/uploads/2025/09/le-mans-ultimate.exe-Screenshot-2025.09.24-11.03.48.85-1024x576.png", "Compact lap, frequent traffic, and repeated direction changes.", "紧凑单圈、频繁交通和反复变向。", "Short lap traffic leaves little recovery time, while repeated changes reward a responsive platform.", "短单圈里的交通几乎没有补救时间，反复变向则奖励响应灵敏的平台。", "Plan passes early, preserve exit speed, and make one clean steering input per change.", "提前规划超车，保护出弯速度，每次变向只做一次干净的转向输入。", (_recommend("mclaren-720s-lmgt3-evo", "High-speed confidence and aero efficiency suit Silverstone's repeated direction changes.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Silverstone 的快速反复变向。"), _recommend("ferrari-296-lmgt3", "Agile direction changes help in Silverstone International's compact traffic flow.", "这款车方向变化灵活，空气动力学平衡可应对Silverstone 的快速反复变向。"), _recommend("bmw-m4-lmgt3", "Stable balance gives predictable references amid Silverstone's frequent traffic.", "这款车稳定的前置引擎平衡，兼容路肩可应对Silverstone 的快速反复变向。")), (_recommend("ferrari-499p", "Decisive rotation fits Silverstone's compact repeated changes.", "这款车空气动力学性能和果断转向可应对Silverstone 的快速反复变向。"), _recommend("porsche-963", "Its approachable window helps manage traffic on Silverstone's short lap.", "这款车操作窗口（operating window）宽广，容易上手可应对Silverstone 的快速反复变向。"), _recommend("peugeot-9x8-2024", "Agile aero response supports Silverstone's quick direction changes.", "这款车现代化空气动力学套件灵活可应对Silverstone 的快速反复变向。"))),
    _circuit("spa", "Spa-Francorchamps", "Stavelot, Belgium", "斯塔沃洛，比利时（Stavelot, Belgium）", "7.004", False, "https://lemansultimate.com/wp-content/uploads/2024/02/Spa-11-1024x576.png", "High-speed aero, elevation, a long lap, and variable weather.", "高速空气动力学、起伏、长单圈和多变天气。", "Commitment through elevation changes must be balanced against weather and tyre variation.", "应对地形起伏的决心必须和天气、轮胎变化平衡。", "Build speed gradually in changing conditions and leave margin at the high-speed compressions.", "在变化条件中逐步提速，并在高速压缩处留出余量。", (_recommend("mclaren-720s-lmgt3-evo", "High-speed aero confidence suits Spa's elevation and fast aero sections.", "这款车空气动力学效率（aero efficiency）高，高速信心足可应对Spa 的高速起伏与多变天气。"), _recommend("ferrari-296-lmgt3", "Balanced aero and agile changes fit Spa's long, variable lap.", "这款车方向变化灵活，空气动力学平衡可应对Spa 的高速起伏与多变天气。"), _recommend("bmw-m4-lmgt3", "Stable balance provides predictable behaviour as Spa weather changes.", "这款车稳定的前置引擎平衡，兼容路肩可应对Spa 的高速起伏与多变天气。")), (_recommend("ferrari-499p", "Aero performance and decisive rotation fit Spa's high-speed elevation changes.", "这款车空气动力学性能和果断转向可应对Spa 的高速起伏与多变天气。"), _recommend("porsche-963", "Its broad operating window helps through Spa's long lap and weather shifts.", "这款车操作窗口（operating window）宽广，容易上手可应对Spa 的高速起伏与多变天气。"), _recommend("cadillac-v-series-r", "Strong braking and traction support Spa's mixed high-speed and wet transitions.", "这款车制动强，机械牵引力（traction）好可应对Spa 的高速起伏与多变天气。"))),
    _circuit("laguna-seca", "WeatherTech Raceway Laguna Seca", "Monterey, United States", "蒙特雷，美国（Monterey, United States）", "3.602", True, "https://lemansultimate.com/wp-content/uploads/2026/07/1920x1080LAG_3-1024x576.jpg", "Low-speed traction, elevation, and the Corkscrew sequence.", "低速牵引力、起伏和 Corkscrew 组合。", "The Corkscrew drops away quickly, so the car must rotate without compromising the next exit.", "Corkscrew 会迅速下坠，因此车身必须转过来又不牺牲下一处出弯。", "Brake early over the crest, use one smooth rotation at the Corkscrew, and protect traction.", "过坡顶提前制动，在 Corkscrew 用一次平顺转向，并保护牵引力。", (_recommend("porsche-911-gt3-r", "Rear-engine traction helps Laguna Seca's low-speed exits and Corkscrew recovery.", "这款车后置引擎带来牵引力（traction）和转向可应对Laguna Seca 的低速起伏与 Corkscrew。"), _recommend("corvette-z06-lmgt3-r", "Predictable traction and braking suit Laguna Seca's elevation changes.", "这款车制动信心足，牵引力（traction）可预测可应对Laguna Seca 的低速起伏与 Corkscrew。"), _recommend("bmw-m4-lmgt3", "Stable balance helps the braking and kerb approach to the Corkscrew.", "这款车稳定的前置引擎平衡，兼容路肩可应对Laguna Seca 的低速起伏与 Corkscrew。")), (_recommend("porsche-963", "Its broad operating window keeps Laguna Seca's Corkscrew sequence approachable.", "这款车操作窗口（operating window）宽广，容易上手可应对Laguna Seca 的低速起伏与 Corkscrew。"), _recommend("cadillac-v-series-r", "Strong braking and traction help at Laguna Seca's low-speed elevation changes.", "这款车制动强，机械牵引力（traction）好可应对Laguna Seca 的低速起伏与 Corkscrew。"), _recommend("bmw-m-hybrid-v8", "Kerb confidence and stability support the Corkscrew approach.", "这款车平台稳定，过路肩有信心可应对Laguna Seca 的低速起伏与 Corkscrew。"))),
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
        if not all((
            car.name.strip(),
            car.strength.strip(),
            car.caution.strip(),
            car.strength_zh.strip(),
            car.caution_zh.strip(),
        )):
            raise ValueError(f"blank car copy: {car.slug}")
        if car.image and not _is_local_guide_image(car.image, "cars"):
            raise ValueError(f"non-local car image: {car.slug}")
        if not _is_lmu_url(car.source_url) or not _is_lmu_url(car.image_source_url):
            raise ValueError(f"non-LMU car source: {car.slug}")

    circuit_slugs = tuple(circuit.slug for circuit in CIRCUITS)
    if len(circuit_slugs) != len(set(circuit_slugs)):
        raise ValueError("duplicate circuit slug")

    for circuit in CIRCUITS:
        if not all((
            circuit.name.strip(),
            circuit.location.strip(),
            circuit.location_zh.strip(),
            circuit.length_km.strip(),
            circuit.character.strip(),
            circuit.character_zh.strip(),
            circuit.challenge.strip(),
            circuit.challenge_zh.strip(),
            circuit.advice.strip(),
            circuit.advice_zh.strip(),
        )):
            raise ValueError(f"blank circuit copy: {circuit.slug}")
        if circuit.image and not _is_local_guide_image(circuit.image, "tracks"):
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
                if not recommendation.fit.strip() or not recommendation.fit_zh.strip():
                    raise ValueError(f"blank recommendation copy: {circuit.slug}")
                car = CARS.get(recommendation.car_slug)
                if car is None:
                    raise ValueError(f"missing recommended car: {recommendation.car_slug}")
                if car.car_class != expected_class:
                    raise ValueError(f"class mismatch: {recommendation.car_slug}")


validate_guide_data()
