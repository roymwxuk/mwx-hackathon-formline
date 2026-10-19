"""Fictional league: clubs, squads and each player's hidden "true" tendencies.

The latent profiles are GEN-ONLY (DATA_SCHEMA.md §2.3). The engine never sees them;
they exist so we can later measure how well estimated baselines recover the truth.
"""

import random
from dataclasses import asdict, dataclass

from formline.schema.biography import synthetic_biography
from formline.schema.reference import POSITION_GROUPS, Club, ClubColors, Player


@dataclass(frozen=True)
class ClubSpec:
    slug: str
    name: str
    short_name: str
    primary: str
    secondary: str
    venue: str


CLUB_SPECS = [
    ClubSpec("harbourside", "Harbourside Athletic", "HAR", "#0B3D91", "#FFFFFF", "Quayside Park"),
    ClubSpec("northgate", "Northgate Rovers", "NOR", "#A6F28C", "#111111", "Gatehouse Lane"),
    ClubSpec("elderwick", "Elderwick Town", "ELD", "#1E6B3A", "#F2E8C9", "The Elder Ground"),
    ClubSpec("thornmoor", "Thornmoor United", "THO", "#7A1F2B", "#E9C46A", "Moorside Stadium"),
    ClubSpec("kestrelbay", "Kestrel Bay FC", "KES", "#F28C28", "#1A1A1A", "Cliff Road"),
    ClubSpec("corranvale", "Corranvale City", "COR", "#5B3F8C", "#DADDE3", "Vale Arena"),
]

# 4-3-3 starting XI, then 7 substitutes: (position, shirt number, starter).
SQUAD_TEMPLATE = [
    ("GK", 1, True), ("RB", 2, True), ("CB", 4, True), ("CB", 5, True), ("LB", 3, True),
    ("DM", 6, True), ("CM", 8, True), ("AM", 10, True),
    ("RW", 7, True), ("ST", 9, True), ("LW", 11, True),
    ("GK", 13, False), ("RB", 12, False), ("CB", 15, False), ("LB", 14, False),
    ("CM", 17, False), ("RW", 19, False), ("ST", 20, False),
]


@dataclass(frozen=True)
class PinnedPlayer:
    """A named player the UI mock and demo script rely on."""

    player_id: str
    first: str
    last: str
    ja: str
    position: str
    shirt_number: int
    foot: str
    profile: dict


# The demo storylines follow these players, so their ids and names are fixed.
PINNED: dict[str, list[PinnedPlayer]] = {
    "harbourside": [
        PinnedPlayer("ply_0107", "Tomas", "Reyner", "トマス・レイナー", "ST", 9, "right",
                     {"archetype": "power", "shot_power_mean_kmh": 95.0, "shot_power_sd_kmh": 7.0,
                      "shot_volume": 4.2, "placement_skill": 0.55}),
        PinnedPlayer("ply_0111", "Kenji", "Ito", "伊藤健二", "LW", 11, "right",
                     {"archetype": "placement", "placement_skill": 0.78}),
        PinnedPlayer("ply_0104", "Marco", "Silvestri", "マルコ・シルヴェストリ", "RW", 7, "left",
                     {}),
    ],
    "northgate": [
        PinnedPlayer("ply_0210", "Daniel", "Okafor", "ダニエル・オカフォー", "ST", 10, "right",
                     {"header_skill": 0.85, "shot_volume": 3.8}),
        PinnedPlayer("ply_0208", "Lukas", "Brandt", "ルーカス・ブラント", "CM", 8, "right",
                     {"long_range_tendency": 0.6, "shot_volume": 1.6}),
    ],
}

# Hand edits to generated first names, applied after generation so the random
# sequence (and every other name and profile) stays the same.
FIRST_NAME_OVERRIDES = {
    "ply_0414": ("Edward", "エドワード"),
    "ply_0612": ("Edward", "エドワード"),
    "ply_0411": ("Charles", "チャールズ"),
    "ply_0617": ("Charles", "チャールズ"),
}

FIRST_NAMES = [
    ("Elias", "エリアス"), ("Mateo", "マテオ"), ("Noah", "ノア"), ("Oskar", "オスカー"),
    ("Rafael", "ラファエル"), ("Idris", "イドリス"), ("Jonah", "ジョナ"), ("Felix", "フェリックス"),
    ("Arlo", "アーロ"), ("Bastian", "バスティアン"), ("Caio", "カイオ"), ("Dario", "ダリオ"),
    ("Emil", "エミル"), ("Finn", "フィン"), ("Gael", "ガエル"), ("Hugo", "ウーゴ"),
    ("Ilan", "イラン"), ("Jasper", "ジャスパー"), ("Kofi", "コフィ"), ("Leon", "レオン"),
    ("Milan", "ミラン"), ("Nico", "ニコ"), ("Otto", "オットー"), ("Pablo", "パブロ"),
    ("Quentin", "カンタン"), ("Rui", "ルイ"), ("Samir", "サミール"), ("Teo", "テオ"),
    ("Umar", "ウマル"), ("Viktor", "ヴィクトル"), ("Wes", "ウェス"), ("Yusuf", "ユスフ"),
    ("Zane", "ゼイン"), ("Aiden", "エイデン"), ("Bram", "ブラム"), ("Cyril", "シリル"),
    ("Dmitri", "ドミトリ"), ("Ezra", "エズラ"), ("Haruto", "ハルト"), ("Ren", "レン"),
    ("Sota", "ソウタ"), ("Tiago", "チアゴ"), ("Anders", "アンデシュ"), ("Malik", "マリク"),
]

LAST_NAMES = [
    ("Albescu", "アルベスク"), ("Barrowe", "バロウ"), ("Castellan", "カステラン"),
    ("Delacorte", "デラコルト"), ("Eskeland", "エスケランド"), ("Fairholm", "フェアホルム"),
    ("Halvorsen", "ハルヴォルセン"), ("Ingleby", "イングルビー"), ("Jessop", "ジェソップ"),
    ("Kerrigan", "ケリガン"), ("Lindahl", "リンダール"), ("Marchetti", "マルケッティ"),
    ("Orrin", "オリン"), ("Pellard", "ペラール"), ("Quayle", "クエール"), ("Rossiter", "ロシター"),
    ("Sandor", "シャンドル"), ("Thorne", "ソーン"), ("Varga", "ヴァルガ"),
    ("Whitcombe", "ウィットコム"), ("Achterberg", "アハテルベルフ"), ("Brannock", "ブラノック"),
    ("Cardell", "カーデル"), ("Dunmore", "ダンモア"), ("Ellery", "エラリー"),
    ("Ferrante", "フェランテ"), ("Garrow", "ギャロウ"), ("Hollis", "ホリス"), ("Ivers", "アイヴァース"),
    ("Jankov", "ヤンコフ"), ("Kessler", "ケスラー"), ("Lacombe", "ラコンブ"), ("Mbatha", "ムバタ"),
    ("Nakashima", "ナカシマ"), ("Oduya", "オドゥヤ"), ("Petrakis", "ペトラキス"),
    ("Radovan", "ラドヴァン"), ("Solberg", "ソルベルグ"), ("Tavener", "タヴナー"),
    ("Uchenna", "ウチェナ"), ("Vellacott", "ヴェラコット"), ("Wexford", "ウェックスフォード"),
    ("Yilmazer", "ユルマゼル"), ("Zelenko", "ゼレンコ"), ("Abiodun", "アビオドゥン"),
    ("Calloway", "キャロウェイ"), ("Desrosiers", "デロジエ"), ("Engstrom", "エングストローム"),
    ("Hartigan", "ハーティガン"), ("Kovalenko", "コヴァレンコ"), ("Moravec", "モラヴェツ"),
    ("Okonjo", "オコンジョ"), ("Pinheiro", "ピニェイロ"), ("Santangelo", "サンタンジェロ"),
    ("Takeda", "タケダ"), ("Lowther", "ラウザー"), ("Mercer", "マーサー"),
]


@dataclass
class LatentProfile:
    """GEN-ONLY hidden tendencies that drive event generation."""

    player_id: str
    archetype: str  # power, placement, balanced, defender, keeper
    shot_power_mean_kmh: float  # foot shot from ~16 m, unpressured, strong foot
    shot_power_sd_kmh: float
    placement_skill: float  # 0–1: how close to the corners on-target shots go
    shot_volume: float  # relative weight for being the shooter
    long_range_tendency: float  # 0–1
    header_skill: float  # 0–1: weight for winning headers, adds header speed
    pressure_sensitivity: float  # fraction of shot speed lost under pressure
    weak_foot_factor: float  # speed multiplier when shooting with the weaker foot
    pass_skill: float  # completion probability delta


POWER_BY_GROUP = {"GK": 72.0, "DEF": 79.0, "MID": 82.0, "FWD": 85.0}
PLACEMENT_BY_GROUP = {"GK": 0.2, "DEF": 0.35, "MID": 0.48, "FWD": 0.55}
VOLUME_BY_POSITION = {
    "GK": 0.0, "CB": 0.35, "LB": 0.4, "RB": 0.4, "DM": 0.5, "CM": 1.0, "AM": 2.0,
    "LW": 2.2, "RW": 2.2, "ST": 3.2,
}
HEADER_BY_POSITION = {"CB": 0.55, "ST": 0.5}


def _clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _make_profile(rng: random.Random, player: Player, overrides: dict) -> LatentProfile:
    group = player.position_group
    if group == "GK":
        archetype = "keeper"
    elif group == "DEF":
        archetype = "defender"
    else:
        archetype = rng.choices(["power", "placement", "balanced"], [0.3, 0.3, 0.4])[0]
    archetype = overrides.get("archetype", archetype)
    power = POWER_BY_GROUP[group] + rng.gauss(0, 3)
    placement = PLACEMENT_BY_GROUP[group] + rng.gauss(0, 0.08)
    if archetype == "power":
        power += 7
        placement -= 0.08
    elif archetype == "placement":
        power -= 4
        placement += 0.18
    profile = LatentProfile(
        player_id=player.player_id,
        archetype=archetype,
        shot_power_mean_kmh=round(power, 1),
        shot_power_sd_kmh=round(rng.uniform(6.0, 9.0), 1),
        placement_skill=round(_clip(placement, 0.05, 0.95), 3),
        shot_volume=round(VOLUME_BY_POSITION[player.position] * rng.lognormvariate(0, 0.3), 3),
        long_range_tendency=round(
            _clip(rng.uniform(0.1, 0.4) + (0.1 if group == "MID" else 0), 0, 1), 3
        ),
        header_skill=round(_clip(HEADER_BY_POSITION.get(player.position, 0.15)
                                 + rng.gauss(0, 0.08), 0.02, 0.95), 3),
        pressure_sensitivity=round(rng.uniform(0.02, 0.12), 3),
        weak_foot_factor=round(rng.uniform(0.86, 0.97), 3),
        pass_skill=round(rng.gauss(0.01 if group == "MID" else 0.0, 0.025), 3),
    )
    for key, value in overrides.items():
        setattr(profile, key, value)
    return profile


@dataclass
class League:
    clubs: list[Club]
    venues: dict[str, str]
    players: list[Player]
    starters: dict[str, list[str]]  # club_id -> starting XI player ids
    profiles: dict[str, LatentProfile]

    def squad(self, club_id: str) -> list[Player]:
        return [p for p in self.players if p.club_id == club_id]

    def profiles_json(self) -> list[dict]:
        return [asdict(p) for p in self.profiles.values()]


def build_league(seed: int) -> League:
    rng = random.Random(f"{seed}:league")
    used_names: set[str] = {f"{p.first} {p.last}" for ps in PINNED.values() for p in ps}
    clubs, players, profiles, starters, venues = [], [], {}, {}, {}

    for club_no, spec in enumerate(CLUB_SPECS, start=1):
        club_id = f"clb_{spec.slug}"
        clubs.append(Club(club_id=club_id, name=spec.name, short_name=spec.short_name,
                          colors=ClubColors(primary=spec.primary, secondary=spec.secondary)))
        venues[club_id] = spec.venue
        pinned = list(PINNED.get(spec.slug, []))
        pinned_ids = {p.player_id for p in pinned}
        free_ids = (f"ply_{club_no:02d}{n:02d}" for n in range(1, 19)
                    if f"ply_{club_no:02d}{n:02d}" not in pinned_ids)

        # Pinned players take the first template slot with their position; shirt numbers swap.
        slots = [list(s) + [None] for s in SQUAD_TEMPLATE]
        for pin in pinned:
            slot = next(s for s in slots if s[0] == pin.position and s[3] is None)
            clash = next((s for s in slots if s[1] == pin.shirt_number and s is not slot), None)
            if clash:
                clash[1] = slot[1]
            slot[1] = pin.shirt_number
            slot[3] = pin

        starters[club_id] = []
        club_surnames = {pin.last for pin in pinned}  # no two players in a squad share a surname
        for position, number, starter, pin in slots:
            if pin:
                pid, name, ja, foot, overrides = (pin.player_id, f"{pin.first} {pin.last}",
                                                  pin.ja, pin.foot, pin.profile)
            else:
                pid = next(free_ids)
                while True:
                    (first, first_ja), (last, last_ja) = (rng.choice(FIRST_NAMES),
                                                          rng.choice(LAST_NAMES))
                    name = f"{first} {last}"
                    if name not in used_names and last not in club_surnames:
                        break
                club_surnames.add(last)
                if pid in FIRST_NAME_OVERRIDES:
                    first, first_ja = FIRST_NAME_OVERRIDES[pid]
                    name = f"{first} {last}"
                ja = f"{first_ja}・{last_ja}"
                foot = "left" if (position in ("LB", "LW") and rng.random() < 0.7) or (
                    rng.random() < 0.18) else "right"
                overrides = {}
            used_names.add(name)
            player = Player(player_id=pid, display_name=name, display_name_ja=ja,
                            club_id=club_id, shirt_number=number, position=position,
                            position_group=POSITION_GROUPS[position], preferred_foot=foot,
                            **synthetic_biography(pid))
            players.append(player)
            profiles[pid] = _make_profile(rng, player, overrides)
            if starter:
                starters[club_id].append(pid)

    return League(clubs=clubs, venues=venues, players=players, starters=starters,
                  profiles=profiles)
