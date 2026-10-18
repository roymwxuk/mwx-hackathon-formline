"""Template answers: the fallback when the model fails verification three times.

Built only from the facts pack, so they always verify; plain but never wrong.
"""

import re

from formline.analyst.facts import FactsPack

NUMBER = re.compile(r"\d+(?:\.\d+)?")

JA_OUTCOME = {"scored": "ゴール", "saved by the goalkeeper": "キーパーがセーブ", "off target": "枠外",
              "hit the post": "ポスト直撃", "blocked by a defender": "ディフェンダーがブロック"}


def _fill(text: str, names: dict[str, str]) -> str:
    for role, name in sorted(names.items(), key=lambda kv: -len(kv[0])):
        text = text.replace(role, name)
    return text


def template_answer(pack: FactsPack, lang: str, names: dict[str, str]) -> dict:
    """{headline, body} from the facts; `names`: role -> display name in this language."""
    f = pack.facts
    q = pack.question
    if lang == "ja":
        return _ja(q, f, names)
    if q == "shot_outcome":
        head = f"{names['SHOOTER']}: {f['outcome']}"
        parts = [f["distance"], f["body_part"], f.get("pressure"), f["chance_quality"],
                 f.get("placement"), f.get("score_now")]
    elif q == "corner":
        result = "a shot" if "shot by" in f["what_followed"] else "no shot"
        head = f"{names['TAKER']}'s corner: {result}"
        parts = [f["side"], f.get("delivery"), f["what_followed"], f["corners_tonight"]]
    elif q == "card":
        head = f"{names['PLAYER']}: {f['card']}"
        parts = [f["his_fouls_tonight"], f.get("where"), f.get("first_yellow"), f.get("consequence"),
                 f["not_in_the_data"]]
    elif q == "var":
        head = f"{names['SHOOTER']}'s goal ruled out"
        parts = [f["decision"], f["score_now"]]
    elif q == "situation":
        head = f["score_now"]
        parts = [f["minute"], "goals: " + f["goals"], f["shots"], f["recent"], f.get("cards"),
                 f.get("down_to_ten_home"), f.get("down_to_ten_away")]
    elif q == "score":
        head = f["score_now"]
        parts = ["goals: " + f["goals"], f.get("best_missed_chances"), f["chance_quality_total"],
                 f["goalkeeper_saves"]]
    elif q == "team_stats":
        head = "The two teams side by side"
        parts = [f["shots"], f["on_target"], f["chance_quality_total"], f["corners"], f["cards"],
                 f["passes_completed"]]
    else:  # player_tonight
        head = f"{names['PLAYER']} tonight"
        parts = [f["shots_tonight"], f.get("speed_vs_norm"), f["best_chance"], f["fastest_shot"]]
    parts = [_fill(p, names) for p in parts if p]
    while len(parts) > 1 and len("; ".join(parts)) + 1 > 260:  # drop optional facts, never cut one
        parts.pop(-2 if len(parts) > 2 else -1)
    body = "; ".join(parts) + "."
    head = _fill(head, names)
    if len(head) > 70:
        head = head.split(":")[0]
    return {"headline": head, "body": body[0].upper() + body[1:]}


def _nums(s: str) -> str:
    return "".join(ch for ch in s if ch.isdigit() or ch in ".%")


def _two(s: str) -> tuple[str, str]:
    """The two per-side numbers of a 'label: Home n, Away m' fact (home first)."""
    found = NUMBER.findall(s)
    return found[-2], found[-1]


def _ja(q: str, f: dict, names: dict[str, str]) -> dict:
    nums = _nums
    if q in ("situation", "score", "team_stats", "player_tonight"):
        return _ja_followup(q, f, names)
    if q == "shot_outcome":
        head = f"{names['SHOOTER']}のシュートは{JA_OUTCOME[f['outcome']]}"
        body = f"ゴールまで{nums(f['distance'])}m、{nums(f['shot_speed'])} km/h。得点期待値は約{nums(f['chance_quality'])}（推定）。"
    elif q == "corner":
        head = f"{names['TAKER']}のコーナーキック"
        body = "シュートにつながった。" if "SHOOTER" in names and "shot" in f["what_followed"] else "シュートには至らず。"
    elif q == "card":
        head = f"{names['PLAYER']}に{'退場処分' if 'sent off' in f['card'] else 'イエローカード'}"
        body = f"今夜{nums(f['his_fouls_tonight'])}回目のファウル。データにはファウルの相手や理由は記録されていない。"
    else:
        head = f"{names['SHOOTER']}のゴールは取り消し"
        body = "VARの判定でゴールは認められなかった。"
    return {"headline": head[:36], "body": body[:130]}


def _ja_followup(q: str, f: dict, names: dict[str, str]) -> dict:
    h, a = _two(f.get("score_now", "0 0"))
    if q == "situation":
        sh, sa = _two(f["shots"])
        head = f"{NUMBER.findall(f['minute'])[0]}分時点の試合状況"
        body = (f"スコアは{h}–{a}（ホーム対アウェイ）。シュート数は{sh}対{sa}、"
                f"直近10分で{NUMBER.findall(f['recent'])[0]}本。")
        if "down_to_ten_home" in f or "down_to_ten_away" in f:
            body += "退場者が出ている。"
    elif q == "score":
        xh, xa = _two(f["chance_quality_total"])
        vh, va = _two(f["goalkeeper_saves"])
        head = f"スコア{h}–{a}の理由"
        body = f"得点期待値の合計は{xh}対{xa}（推定）。キーパーのセーブ数は{vh}対{va}。"
    elif q == "team_stats":
        parts = [("シュート", "shots"), ("枠内", "on_target"), ("コーナー", "corners"),
                 ("カード", "cards")]
        head = "両チームの比較（ホーム対アウェイ）"
        xh, xa = _two(f["chance_quality_total"])
        body = "、".join(f"{ja}{_two(f[k])[0]}対{_two(f[k])[1]}" for ja, k in parts)
        body += f"、得点期待値{xh}対{xa}（推定）。"
    else:  # player_tonight
        n, on, goals = NUMBER.findall(f["shots_tonight"])[:3]
        head = f"今夜の{names['PLAYER']}"
        body = (f"今夜のシュートは{n}本、枠内{on}本、ゴール{goals}。"
                f"最速は{NUMBER.findall(f['fastest_shot'])[0]} km/h。")
        if "speed_vs_norm" in f:
            tonight, norm = NUMBER.findall(f["speed_vs_norm"])[:2]
            body += f"利き足の平均{tonight} km/h（今季平均{norm} km/h）。"
    return {"headline": head[:36], "body": body[:130]}
