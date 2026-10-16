"""
Chinese localisation for the pattern document produced by pattern_engine.

The engine emits a small, very regular vocabulary, so a set of ordered
line/token rules can translate the whole document into readable Chinese.
Everything falls back to the original English if a term is unknown, so the
output never breaks — it just stays partly English.

Public API:
    to_chinese(text) -> str
"""

import re

# ──────────────────────────────────────────────────────────────
#  Structural lines
# ──────────────────────────────────────────────────────────────

TITLES = {
    "# YOUR CUSTOM CROCHET PATTERN": "# 你的专属钩针图解",
    "*Terminology: US Standard*": "*术语：美式钩针（US）*",
    "## BEGINNER TIPS": "## 新手提示",
    "## ABBREVIATIONS": "## 缩写对照",
    "## MATERIALS": "## 材料",
    "## ASSEMBLY": "## 组装",
}

BULLETS = {
    "- **Mark your rounds:** Use a stitch marker (or safety pin) in the first stitch of every round so you don't lose count.":
        "- **做记号：** 每圈的第一针都别上记号扣（或安全别针），就不容易数错。",
    "- **Counting:** The number in (parentheses) at the end of each line is how many stitches you should have. Count them!":
        "- **数针数：** 每行末尾括号里的数字，是这一圈钩完后的总针数，记得核对。",
    "- **Magic ring:** If the magic ring is too hard, you can 'Chain 2' and make 6 sc into the second chain from the hook.":
        "- **环形起针：** 如果觉得太难，可改成「锁 2 针，在倒数第 2 个锁针里钩 6 个短针」。",
    "- **Hook:** 3.5mm (E/4) crochet hook": "- **钩针：** 3.5mm（E/4）",
    "- **Yarn:** Worsted weight (Medium #4) in the following colors:":
        "- **毛线：** 中粗线（Worsted／4 号），颜色如下：",
    "- **Safety eyes:** 6-9mm (size to your preference)": "- **安全眼睛：** 6–9mm（大小按喜好选）",
    "- **Stuffing:** Polyester fiberfill": "- **填充棉：** 聚酯纤维填充棉",
    "- **Extras:** Yarn needle, stitch markers, scissors": "- **工具：** 毛线缝针、记号扣、剪刀",
}

ABBREVIATIONS = {
    "single crochet (US term)": "短针（美式术语）",
    "increase (2 sc in one stitch)": "加针（同一针里钩 2 个短针）",
    "decrease (sc 2 stitches together)": "减针（2 针并 1 针）",
    "chain": "锁针／辫子针",
    "slip stitch": "引拔针",
    "half double crochet (US term)": "中长针（美式术语）",
    "double crochet (US term)": "长针（美式术语）",
    "adjustable ring to start rounds (or ch 2, sc 6 in 2nd ch from hook)":
        "环形起针（或：锁 2 针，在倒数第 2 针里钩 6 个短针）",
}

BODY_LINES = {
    "This piece is worked in continuous rounds. Do not join at the end of rounds.":
        "本片为**连续圈钩**，每圈结尾不引拔、不断线。",
    "This piece is worked in continuous rounds.": "本片为连续圈钩。",
    "This piece is worked in continuous rounds (oval/egg shape).": "本片为连续圈钩（椭圆形／蛋形）。",
    "This piece is worked in continuous rounds from the tip down.": "本片从尖端开始，连续圈钩。",
    "This piece is worked in continuous rounds (dome/half-sphere, flat on the bottom).":
        "本片为连续圈钩（半球形，底面是平的）。",
    "*This part is worked in rows, not rounds. Turn your work at the end of each row.*":
        "*本片是「行钩」（不是圈钩），每行结尾要翻面。*",
    "*This leaf is worked in rows with chain spaces to create the heart shape.*":
        "*叶片用行钩，靠锁针的空格做出心形。*",
    "*Wings are worked in rows. Ch 1 and turn at the end of each row.*":
        "*翅膀用行钩，每行结尾锁 1 针翻面。*",
    "*Each spike is a tiny triangle.*": "*每个尖刺都是一个小三角。*",
    "*This piece stays flat — do not stuff.*": "*本片保持扁平，不要塞棉。*",
    "*This piece starts wide and tapers to a point.*": "*本片从宽处起针，逐渐收到尖。*",
    "*This piece is worked in rows and fans out from narrow to wide.*":
        "*本片用行钩，由窄到宽呈扇形展开。*",
    "*Each foot has 3 toes made from chains.*": "*每只脚有 3 个用锁针做的脚趾。*",
    "*Small rounded bump — stuff lightly for a 3D effect.*": "*小圆凸起，少量塞棉做出立体感。*",
    "*Use a yarn needle and the long tails you left on each piece.*":
        "*用毛线缝针，配合每片留的长线头进行缝合。*",
}

TIPS = {
    "Pull the tail tight to close the hole!": "拉紧起针线头，把中间的洞收小！",
    "Just go round and round!": "不加不减，一圈一圈钩就好。",
    "These extra even rounds create the oval/egg shape!": "这些不加不减的圈，让形状拉长成椭圆／蛋形。",
    "The chain-3 spaces create the heart indent at top.": "锁 3 针形成的空隙，就是心形顶部的凹口。",
    "The increases on both edges create the fan/spread shape.": "两侧加针，做出扇形张开的效果。",
    "All 3 toes branch out from the same point at the bottom of the leg.":
        "3 个脚趾都从腿底部的同一点分出去。",
    "This creates ONE petal.": "这样就是一片花瓣。",
    "Stuff the piece firmly with stuffing now!": "现在把这一片塞满填充棉！",
    "Pin pieces in place with sewing pins before stitching to check the look!":
        "缝之前先用珠针固定位置，确认效果再缝。",
}

FINISH = {
    "Fasten off leaving a long tail. Thread a needle with the tail, then pull the yarn through the front loops of each remaining stitch. Pull tight to close.":
        "收针，留一段长线。把线穿进缝针，依次穿过剩余每一针的外半针，拉紧收口。",
    "Fasten off leaving a long tail for sewing.": "收针，留一段长线用于缝合。",
    "Fasten off leaving a long tail for sewing. Stuff gently.": "收针，留长线用于缝合。轻轻塞棉。",
    "Fasten off leaving a long tail for sewing. Stuff before attaching.": "收针，留长线用于缝合。缝合前先塞棉。",
    "Fasten off leaving a long tail for sewing. Stuff the wide end lightly.":
        "收针，留长线用于缝合。宽的一头少量塞棉。",
    "Fasten off leaving a long tail for sewing. Stuff lightly.": "收针，留长线用于缝合。少量塞棉。",
    "Fasten off leaving a long tail. Sew spikes evenly along the back.": "收针，留长线。把尖刺均匀缝到背上。",
    "Fasten off and weave in ends.": "收针，藏好线头。",
    "Fasten off leaving a long tail. Stuff lightly before sewing.": "收针，留长线。缝合前少量塞棉。",
}

PETAL_STEPS = {
    "Sl st join into an edge stitch.": "引拔针连接到边缘的 1 针上。",
    "Ch 1, hdc in same stitch.": "锁 1 针，在同一针里钩中长针。",
    "Hdc in next stitch.": "在下一针钩中长针。",
    "Ch 1, sl st in same stitch as Step 3.": "锁 1 针，在第 3 步的同一针里钩引拔针。",
}

# ──────────────────────────────────────────────────────────────
#  Part names / colors / positions (from the AI)
# ──────────────────────────────────────────────────────────────

PART_NAMES = {
    "head": "头", "body": "身体", "torso": "身体", "ear": "耳朵", "ears": "耳朵",
    "eye": "眼睛", "eyes": "眼睛", "tail": "尾巴", "leg": "腿", "legs": "腿",
    "arm": "手臂", "arms": "手臂", "wing": "翅膀", "wings": "翅膀", "nose": "鼻子",
    "beak": "鸟嘴", "mouth": "嘴巴", "foot": "脚", "feet": "脚", "paw pads": "脚垫",
    "paw pad": "脚垫", "spike": "尖刺", "spikes": "尖刺", "petal": "花瓣", "petals": "花瓣",
    "shell": "外壳", "cap": "帽盖", "hat": "帽子", "horn": "犄角", "horns": "犄角",
    "antenna": "触角", "fin": "鱼鳍", "fins": "鱼鳍", "spot": "斑点", "spots": "斑点",
    "cheek": "脸颊", "cheeks": "脸颊", "belly": "肚皮", "head & body": "头连身体",
    "head and body": "头连身体", "stem": "花茎", "leaf": "叶子", "leaves": "叶子",
    "flower": "花朵", "center": "花心", "neck": "脖子", "mane": "鬃毛", "hair": "头发",
    "tentacle": "触手", "tentacles": "触手", "face": "脸", "hand": "手", "hands": "手",
}

COLORS = {
    "white": "白色", "black": "黑色", "grey": "灰色", "gray": "灰色", "blue": "蓝色",
    "red": "红色", "green": "绿色", "yellow": "黄色", "orange": "橙色", "brown": "棕色",
    "pink": "粉色", "purple": "紫色", "beige": "米色", "cream": "米白色", "navy": "藏青色",
    "teal": "蓝绿色", "gold": "金色", "golden": "金色", "silver": "银色", "tan": "浅棕色",
    "dark": "深", "light": "浅", "stripes": "条纹", "striped": "条纹", "spots": "圆点",
    "spotted": "圆点",
}

POSITIONS = {
    "top of body": "身体顶部", "sides of body": "身体两侧", "front of head": "头部前面",
    "back of body": "背部", "back of figure": "背部", "center": "正中间",
    "bottom center": "底部中间", "top of head": "头顶", "front of face": "脸部前面",
    "bottom of body": "身体底部", "sides of head": "头部两侧", "top": "顶部",
    "front": "前面", "back": "后面", "bottom": "底部", "sides": "两侧",
    "body": "身体", "head": "头部", "face": "脸部", "top of head.": "头顶",
}

# ──────────────────────────────────────────────────────────────
#  Instruction translation
# ──────────────────────────────────────────────────────────────

def _sc(seg: str) -> str:
    """Translate a single crochet segment like 'sc', '3 sc', 'inc', 'dec'."""
    seg = seg.strip()
    if seg == "sc":
        return "短针"
    m = re.fullmatch(r"(\d+) sc", seg)
    if m:
        return f"{m.group(1)} 短针"
    if seg == "inc":
        return "加针"
    m = re.fullmatch(r"(\d+) inc", seg)
    if m:
        return f"{m.group(1)} 加针"
    if seg == "dec":
        return "减针"
    m = re.fullmatch(r"(\d+) dec", seg)
    if m:
        return f"{m.group(1)} 减针"
    return seg


def _translate_instruction(s: str) -> str:
    s = s.strip()

    # [X, inc/dec] x N  and  [X, inc/dec] x N, ... 
    m = re.fullmatch(r"\[(.+?), (inc|dec)\] x (\d+)(, (.*))?", s)
    if m:
        left = _sc(m.group(1))
        mid = "加针" if m.group(2) == "inc" else "减针"
        tail = f"，{_sc(m.group(5))}" if m.group(5) else ""
        return f"[{left}，{mid}] × {m.group(3)}{tail}"

    m = re.fullmatch(r"\[sc, inc\] x (\d+), 2 sc", s)
    if m:
        return f"[短针，加针] × {m.group(1)}，2 短针"

    m = re.fullmatch(r"(\d+) sc in a magic ring", s)
    if m:
        return f"环形起针，钩 {m.group(1)} 个短针"

    m = re.fullmatch(r"(\d+) inc, (\d+) sc", s)
    if m:
        return f"{m.group(1)} 加针，{m.group(2)} 短针"

    m = re.fullmatch(r"Ch (\d+)", s)
    if m:
        return f"锁 {m.group(1)} 针"

    m = re.fullmatch(r"Sc in 2nd ch from hook, (.+), ch 1 and turn", s)
    if m:
        return f"在倒数第 2 个锁针里钩短针，{_sc(m.group(1))}，锁 1 针翻面"

    m = re.fullmatch(r"Inc, (.+), inc, ch 1 and turn", s)
    if m:
        return f"加针，{_sc(m.group(1))}，加针，锁 1 针翻面"

    m = re.fullmatch(r"Dec, (.+), dec, ch 1 and turn", s)
    if m:
        return f"减针，{_sc(m.group(1))}，减针，锁 1 针翻面"

    m = re.fullmatch(r"Inc, (.+), inc", s)
    if m:
        return f"加针，{_sc(m.group(1))}，加针"

    if s == "Inc in 2nd ch from hook, ch 1 and turn":
        return "在倒数第 2 个锁针里加针，锁 1 针翻面"
    if s == "2 inc, ch 1 and turn":
        return "2 加针，锁 1 针翻面"
    if s == "Inc, 2 sc, inc, ch 3 and turn":
        return "加针，2 短针，加针，锁 3 针翻面"
    if s == "Sk 2 sts, 2 sc, ch 3, sk 1 st, sl st, ch 1 and turn":
        return "空 2 针，2 短针，锁 3 针，空 1 针，引拔针，锁 1 针翻面"
    if s == "Sk 1 st, 3 sc in ch-3 space, 2 sc, 3 sc in ch-3 space, ch 1 and turn":
        return "空 1 针，在锁 3 针的空格里钩 3 短针，2 短针，在锁 3 针的空格里钩 3 短针，锁 1 针翻面"
    if s == "Sc, hdc, dc, dc, hdc, sc around the edge":
        return "沿边缘依次钩：短针、中长针、长针、长针、中长针、短针"
    if s == "Sk 1-2 sts, repeat Steps 1-4 for the next petal.":
        return "空 1–2 针，重复第 1–4 步钩下一片花瓣。"

    # catch-all: trailing "ch N and turn" + remaining stitch tokens
    tail = ""
    m = re.search(r",?\s*ch (\d+) and turn\.?$", s)
    if m:
        tail = f"，锁 {m.group(1)} 针翻面"
        s = s[:m.start()].strip()
    segs = [seg.strip() for seg in s.split(",") if seg.strip()]
    out = "，".join(_sc(seg) for seg in segs)
    return (out + tail) if (out or tail) else s


def _translate_name(name: str) -> str:
    """Translate a part name (case-insensitive), keeping a '(Make N)' suffix."""
    name = name.strip()
    m = re.fullmatch(r"(.+?)\s*\(Make (\d+)\)", name, re.IGNORECASE)
    base, n = (m.group(1).strip(), m.group(2)) if m else (name, None)

    low = base.lower()
    if low in PART_NAMES:
        zh = PART_NAMES[low]
    else:
        tokens = re.findall(r"[A-Za-z]+", base)
        if len(tokens) > 1:
            zh = "".join(PART_NAMES.get(t.lower(), t) for t in tokens)
        else:
            zh = base
    return f"{zh}（钩 {n} 个）" if n else zh


def _translate_color(color: str) -> str:
    color = color.strip()
    low = color.lower()
    if low in COLORS:
        return COLORS[low]
    # sentence-ish: translate known words, join with Chinese punctuation
    out = color
    for en, zh in sorted(COLORS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(en)}\b", zh, out, flags=re.IGNORECASE)
    out = re.sub(r"\bwith\b", "，带", out, flags=re.IGNORECASE)
    # tidy spacing so "灰色 ，带 粉色" -> "灰色，带粉色"
    out = re.sub(r"\s+([，、])", r"\1", out)
    out = re.sub(r"([，、])\s+", r"\1", out)
    out = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", out)
    out = re.sub(r"\s{2,}", " ", out)
    return out.strip()


def _translate_position(pos: str) -> str:
    p = pos.strip()
    if p.lower() in POSITIONS:
        return POSITIONS[p.lower()]
    out = p
    for en, zh in sorted(POSITIONS.items(), key=lambda kv: -len(kv[0])):
        out = re.sub(rf"\b{re.escape(en)}\b", zh, out, flags=re.IGNORECASE)
    return out


# ──────────────────────────────────────────────────────────────
#  Line dispatcher
# ──────────────────────────────────────────────────────────────

def _line(line: str) -> str:
    raw = line
    stripped = line.strip()

    if raw in TITLES:
        return TITLES[raw]
    if stripped in BULLETS:
        return BULLETS[stripped] if not raw.startswith("  ") else raw
    if stripped in BODY_LINES:
        return BODY_LINES[stripped]

    # dynamic "Make N petals ..." note
    m = re.fullmatch(r"\*Make (\d+) petals, worked directly onto the edge\.\*", stripped)
    if m:
        return f"*共钩 {m.group(1)} 片花瓣，直接钩在边缘上。*"

    # "**Finish:** ..." closing line
    m = re.fullmatch(r"\*\*Finish:\*\* (.+)", stripped)
    if m:
        return f"**收针：** {FINISH.get(m.group(1), m.group(1))}"

    # "### NAME (Use COLOR yarn)" / "(Use COLOR yarn, make N)"
    m = re.fullmatch(r"### (.+?) \(Use (.+?) yarn(, make (\d+))?\)", stripped)
    if m:
        name_raw = m.group(1)
        color = _translate_color(m.group(2))
        count = m.group(4)
        nm = re.fullmatch(r"(.+?)\s*\(Make (\d+)\)", name_raw, re.IGNORECASE)
        if nm:
            name_raw, count = nm.group(1), count or nm.group(2)
        name = _translate_name(name_raw)
        if count:
            return f"### {name}（用{color}毛线，共 {count} 个）"
        return f"### {name}（用{color}毛线）"

    # abbreviation bullets: "- **sc**: single crochet (US term)"
    m = re.fullmatch(r"- \*\*(.+?)\*\*: (.+)", stripped)
    if m:
        key = m.group(1)
        desc = ABBREVIATIONS.get(m.group(2), m.group(2))
        return f"- **{key}**：{desc}"

    # remaining bullets: the materials colour list ("  - White")
    if stripped.startswith("- "):
        indent = raw[:len(raw) - len(raw.lstrip())]
        return f"{indent}- {_translate_color(stripped[2:])}"

    # round / row label
    m = re.fullmatch(r"\*\*(Rnds?|Row|Rows) (.+?):\*\* (.*)", stripped)
    if m:
        kind, num, rest = m.group(1), m.group(2), m.group(3)
        label = "圈" if kind.startswith("Rnd") else "行"
        cnt = ""
        mm = re.fullmatch(r"(.*) \((\d+)\)", rest)
        if mm:
            rest, cnt = mm.group(1), f"（{mm.group(2)}）"
        return f"**第 {num} {label}：** {_translate_instruction(rest)}{cnt}"

    # TIP / aside lines: "   *TIP: ...*" and "   *...*"
    m = re.fullmatch(r"\*TIP: (.*)\*", stripped)
    if m:
        body = TIPS.get(m.group(1), m.group(1))
        return f"   *小贴士：{body}*"
    if stripped.startswith("*") and stripped.endswith("*") and len(stripped) > 2:
        body = stripped[1:-1]
        return "*" + TIPS.get(body, BODY_LINES.get(stripped, body)) + "*"

    # STOP safety-eyes reminder
    m = re.fullmatch(r"\*\*STOP!\*\* If you are using safety eyes, attach them now between Rnds (\d+) and (\d+)\.", stripped)
    if m:
        return (f"**注意！** 如果用安全眼睛，请在**第 {m.group(1)} 圈和第 {m.group(2)} 圈之间**装上眼睛。")

    # petal steps
    m = re.fullmatch(r"\*\*Step (\d+):\*\* (.+)", stripped)
    if m:
        body = m.group(2)
        if body.startswith("Sew the "):
            mm = re.fullmatch(r"Sew the \*\*(.+?)\*\* to the (.+)\.", body)
            if mm:
                return f"**第 {m.group(1)} 步：** 把 **{_translate_name(mm.group(1))}** 缝到{_translate_position(mm.group(2))}。"
        if body.startswith("Weave in all remaining yarn tails"):
            return f"**第 {m.group(1)} 步：** 把所有剩余的线头藏好。"
        if body.startswith("Repeat until you have"):
            n = re.search(r"(\d+)", body).group(1)
            return f"**第 {m.group(1)} 步：** 重复，直到钩出 {n} 片均匀分布的花瓣。"
        zh = PETAL_STEPS.get(body)
        if zh:
            return f"**第 {m.group(1)} 步：** {zh}"
        return f"**第 {m.group(1)} 步：** {_translate_instruction(body)}"

    # bird feet leg / toes
    m = re.fullmatch(r"\*\*Leg:\*\* Ch (\d+), sc in 2nd ch from hook, (.+)\. Do not turn\.", stripped)
    if m:
        return f"**腿：** 锁 {m.group(1)} 针，在倒数第 2 个锁针里钩短针，{_sc(m.group(2))}。不翻面。"
    m = re.fullmatch(r"\*\*Toe (\d+):\*\* Ch (\d+), sl st in 2nd ch from hook, (\d+) sl st back to leg\.", stripped)
    if m:
        return f"**脚趾 {m.group(1)}：** 锁 {m.group(2)} 针，在倒数第 2 个锁针里钩引拔针，再引拔 {m.group(3)} 针回到腿部。"

    # "## TITLE" from the caller (pattern name) → keep as-is
    return line


def to_chinese(text: str) -> str:
    """Translate an engine-generated pattern document into Chinese."""
    return "\n".join(_line(l) for l in text.split("\n"))
