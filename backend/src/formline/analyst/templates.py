"""Template answers: the fallback when the model fails verification three times.

Built only from the facts pack, so they always verify; plain but never wrong.
"""

from formline.analyst.facts import FactsPack

JA_OUTCOME = {"scored": "ゴール", "saved by the goalkeeper": "キーパーがセーブ", "off target": "枠外",
              "hit the post": "ポスト直撃", "blocked by a defender": "ディフェンダーがブロック"}


def _fill(text: str, names: dict[str, str]) -> str:
    for role, name in names.items():
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
    else:  # var
        head = f"{names['SHOOTER']}'s goal ruled out"
        parts = [f["decision"], f["score_now"]]
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


def _ja(q: str, f: dict, names: dict[str, str]) -> dict:
    nums = _nums
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
