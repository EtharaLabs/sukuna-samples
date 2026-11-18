"""Render the Calderwick on-call response evidence media into the served task bytes.

Run from this file's parent directory (environment/):

    PYTHONDONTWRITEBYTECODE=1 python3 -m media.render --root .

The world generator owns the script. This module imports it, rebuilds the registry from the
same world seed and slot generation-input digest, and then draws or speaks each entry of
reg["media_plan"]: two photographed works order sheets and two engineer voice notes. Nothing
is invented here that the plan does not already state, and no private value is written beside
an artefact.

Every byte is a pure function of the plan. There is no use of the random module anywhere in
this file: all jitter, texture and placement wobble come from SHA-256 digests of the seed and
an index, so two runs of the same seed produce identical files.

The spoken leg needs one extra pin. The voice model carries two RandomNormalLike nodes with no
seed attribute of their own, so the speech runtime draws their seed from a process-wide value
it picks once at start-up, and a second process therefore speaks different bytes from the same
text. Each voice note here seeds that runtime from a digest of the world seed and the artefact
file name, and builds the inference session afterwards, because the nodes read the seed when the
session is built and not when it is run. Two processes then speak one artefact identically and
two artefacts still differ from each other.

Outputs, for each plan entry:

    <root>/light-servers/task_data/<drive_path>     the path the shared folder serves
    <root>/light-servers/drive_blobs/<file_name>    the flat name the file store serves
"""
from __future__ import annotations

import argparse
import hashlib
import io
import math
import os
import subprocess
import sys
import wave

ENV_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ENV_DIR not in sys.path:
    sys.path.insert(0, ENV_DIR)

OPERATOR = "CALDERWICK REGIONAL NETWORK OPERATIONS"
CONTRACTOR = "Thornby Field Services Ltd"
FORM_CODE = "TFS/WO-114"
FORM_TITLE = "WORKS ORDER SHEET"
FORM_SUBTITLE = "Attendance and hand-back record, completed at the site"

SHEET_W = 1400
SHEET_H = 1900

PAPER = (246, 243, 232)
INK_PRINT = (38, 42, 58)
INK_RULE = (176, 180, 190)
INK_HAND = (26, 38, 104)

WAV_RATE = 22050
LENGTH_SCALE = 1.0
NOISE_SCALE = 0.667
NOISE_W = 0.8

SPEECH_SEED_LIMIT = 2147483647

VOICE_ENV = "MEDIA_PIPER_VOICE"
SPEECH_MODE_ENV = "MEDIA_SPEECH_MODE"
SCREEN_ENVS = ("MEDIA_SCREEN_A", "MEDIA_SCREEN_B")



def _digest_int(parts, width=8) -> int:
    """A stable non-negative integer from the printable join of parts."""
    key = "|".join(str(p) for p in parts).encode("ascii", "replace")
    return int(hashlib.sha256(key).hexdigest()[:width], 16)


def jitter(parts, span) -> int:
    """A deterministic offset in [-span, span] for one drawing decision."""
    if span <= 0:
        return 0
    return _digest_int(parts) % (2 * span + 1) - span


def unit(parts) -> float:
    """A deterministic float in [0, 1) for one drawing decision."""
    return (_digest_int(parts, 12) % 1000000) / 1000000.0


def noise_bytes(parts, count) -> bytes:
    """A deterministic byte string of the requested length, built by chaining digests."""
    out = bytearray()
    block = 0
    while len(out) < count:
        out += hashlib.sha256(("%s|%d" % ("|".join(str(p) for p in parts), block)).encode("ascii")).digest()
        block += 1
    return bytes(out[:count])



def contains_any(haystacks, needles) -> list:
    """Every (needle, haystack index) pair where a needle sits inside a haystack.

    A plain substring test, kept small so the screen below and any later caller agree on
    exactly what counts as a hit.
    """
    hits = []
    for needle in needles:
        token = (needle or "").strip()
        if not token:
            continue
        for n, hay in enumerate(haystacks):
            if token in (hay or ""):
                hits.append((token, n))
    return hits


def screen_emitted(texts) -> int:
    """Refuse to finish if a screening token the caller named reached an emitted artefact.

    The tokens arrive through the environment and are never written into any emitted byte.
    With neither variable set the screen is skipped without a word.
    """
    needles = [os.environ.get(name, "").strip() for name in SCREEN_ENVS]
    needles = [n for n in needles if n]
    if not needles:
        return 0
    hits = contains_any(texts, needles)
    if hits:
        raise SystemExit("media.render: a screened token reached %d emitted text block(s)"
                         % len({n for _, n in hits}))
    return len(needles)



def load_plan(seed: str, input_digest: str) -> list:
    """Rebuild the registry through the generator and hand back its media plan."""
    from generator import __main__ as world

    reg = world.build(str(seed), str(input_digest))
    world.verify(reg)
    return reg["media_plan"]


def targets(root: str, item: dict) -> list:
    """Both served locations for one plan entry, deepest directory first."""
    task = os.path.join(root, "light-servers", "task_data",
                        *item["drive_path"].split("/"))
    blob = os.path.join(root, "light-servers", "drive_blobs", item["file_name"])
    return [task, blob]



def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    names = ("DejaVuSans-Bold.ttf", "DejaVuSerif-Bold.ttf") if bold else \
            ("DejaVuSans.ttf", "DejaVuSerif.ttf")
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def _hand_font(size: int):
    """The nearest thing to a pen stroke the bundled faces offer: an oblique serif."""
    from PIL import ImageFont

    for name in ("DejaVuSerif-Italic.ttf", "DejaVuSans-Oblique.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return _font(size)



def paper_texture(seed, tag):
    """A faint, blotchy fibre cast over the page, grown from a digest chain and smoothed."""
    from PIL import Image, ImageFilter

    small_w, small_h = SHEET_W // 8, SHEET_H // 8
    layer = Image.frombytes("L", (small_w, small_h),
                            noise_bytes([seed, tag, "fibre"], small_w * small_h))
    layer = layer.resize((SHEET_W, SHEET_H), Image.BILINEAR)
    return layer.filter(ImageFilter.GaussianBlur(3.0))


def write_by_hand(draw, origin, text, font, seed, tag, fill=INK_HAND, span=2):
    """Draw one line a character at a time, each glyph nudged off the baseline.

    The nudge is a digest of the seed, the field tag and the character index, so the same
    field always wobbles the same way and nothing is drawn from a live entropy source.
    """
    x, y = origin
    for n, ch in enumerate(text):
        if ch != " ":
            dx = jitter([seed, tag, n, "x"], span)
            dy = jitter([seed, tag, n, "y"], span + 1)
            draw.text((x + dx, y + dy), ch, fill=fill, font=font)
        x += draw.textlength(ch, font=font) + (1 if ch == " " else 0)
    return x


def signature_scrawl(draw, origin, width, seed, tag, fill=INK_HAND):
    """A looping pen line standing in for a countersignature."""
    x0, y0 = origin
    points = []
    steps = 64
    for n in range(steps + 1):
        t = n / float(steps)
        phase = 2.4 + 5.0 * unit([seed, tag, "phase"])
        swing = 16 + int(12 * unit([seed, tag, "swing"]))
        lift = math.sin(t * phase * math.pi) * swing
        drift = math.sin(t * math.pi) * 9
        points.append((x0 + int(t * width), y0 - int(lift) - int(drift)))
    draw.line(points, fill=fill, width=4, joint="curve")


def sheet_fields(item: dict) -> list:
    """The filled-in fields, read off the plan text and never computed here."""
    lines = [ln.strip() for ln in item["text"].splitlines() if ln.strip()]
    remark = ""
    for line in lines:
        if line.startswith("The paging terminal"):
            remark = "Paging terminal still open when I left site"
    stated = item["stated_handback_local"]
    clock = stated[11:16]
    day = stated[:10]
    fields = [
        ("Incident reference", item["incident_ref"]),
        ("Engineer", item["engineer_name"]),
        ("Engineer number", item["engineer_id"]),
        ("Attendance date", day),
        ("Service handed back at", clock),
        ("Hand-back witnessed by", "Site contact, in person"),
    ]
    if remark:
        fields.append(("Remarks", remark))
    return fields


def draw_sheet(item: dict, seed: str):
    """The flat page, before it is photographed."""
    from PIL import Image, ImageDraw

    sheet = Image.new("RGBA", (SHEET_W, SHEET_H), PAPER + (255,))
    tag = item["file_name"]
    cast = paper_texture(seed, tag).convert("RGB")
    sheet = Image.blend(sheet.convert("RGB"), cast, 0.055).convert("RGBA")
    d = ImageDraw.Draw(sheet)

    d.rectangle((48, 48, SHEET_W - 48, SHEET_H - 48), outline=INK_PRINT, width=3)
    d.rectangle((48, 48, SHEET_W - 48, 300), outline=INK_PRINT, width=2)
    d.text((80, 78), OPERATOR, fill=INK_PRINT, font=_font(34, True))
    d.text((80, 128), CONTRACTOR, fill=INK_PRINT, font=_font(26))
    d.text((80, 176), FORM_TITLE, fill=INK_PRINT, font=_font(40, True))
    d.text((80, 232), FORM_SUBTITLE, fill=INK_PRINT, font=_font(24))
    d.text((SHEET_W - 320, 78), "Form %s" % FORM_CODE, fill=INK_PRINT, font=_font(26, True))
    d.text((SHEET_W - 320, 118), "Times are depot local", fill=INK_PRINT, font=_font(22))
    d.text((SHEET_W - 320, 150), "Keep page with the job", fill=INK_PRINT, font=_font(22))

    label = _font(26)
    hand = _hand_font(40)
    y = 372
    for n, (name, value) in enumerate(sheet_fields(item)):
        d.text((80, y), name, fill=INK_PRINT, font=label)
        d.line((80, y + 112, SHEET_W - 80, y + 112), fill=INK_RULE, width=2)
        write_by_hand(d, (112, y + 44), value, hand, seed, "%s|%d" % (tag, n))
        y += 150

    foot = y + 40
    d.text((80, foot), "Countersignature at hand-back", fill=INK_PRINT, font=label)
    d.line((80, foot + 118, SHEET_W - 420, foot + 118), fill=INK_RULE, width=2)
    signature_scrawl(d, (130, foot + 104), SHEET_W - 620, seed, tag + "|sig")
    d.text((SHEET_W - 390, foot), "Engineer initials", fill=INK_PRINT, font=label)
    d.line((SHEET_W - 390, foot + 118, SHEET_W - 80, foot + 118), fill=INK_RULE, width=2)
    initials = "".join(part[0] for part in item["engineer_name"].split()[:2])
    write_by_hand(d, (SHEET_W - 360, foot + 52), initials, _hand_font(46), seed, tag + "|ini")

    note = ("Return the completed page to the response desk with the job pack. "
            "A hand-back time written here governs the job record.")
    d.text((80, SHEET_H - 150), note[:72], fill=(108, 112, 124), font=_font(22))
    d.text((80, SHEET_H - 116), note[72:], fill=(108, 112, 124), font=_font(22))
    return sheet


def photograph(sheet, seed: str, tag: str):
    """Tilt the page a degree or two, drop it on a desk, light it from one side."""
    from PIL import Image, ImageFilter

    angle = 1.0 + unit([seed, tag, "tilt"]) * 1.0
    if _digest_int([seed, tag, "hand"]) % 2:
        angle = -angle
    tilted = sheet.rotate(angle, expand=True, resample=Image.BICUBIC,
                          fillcolor=(0, 0, 0, 0))

    pad_x = 70 + jitter([seed, tag, "padx"], 18)
    pad_y = 70 + jitter([seed, tag, "pady"], 18)
    w, h = tilted.width + 2 * pad_x, tilted.height + 2 * pad_y
    desk_tone = 58 + _digest_int([seed, tag, "desk"]) % 26
    desk = Image.new("RGB", (w, h), (desk_tone, desk_tone - 4, desk_tone - 11))
    grain = Image.frombytes("L", (w // 6, h // 6),
                            noise_bytes([seed, tag, "desk-grain"], (w // 6) * (h // 6)))
    desk = Image.blend(desk, grain.resize((w, h), Image.BILINEAR).convert("RGB"), 0.10)

    shadow = Image.new("L", (w, h), 0)
    from PIL import ImageDraw as _Draw
    _Draw.Draw(shadow).rectangle((pad_x + 16, pad_y + 20,
                                  pad_x + tilted.width + 22, pad_y + tilted.height + 26),
                                 fill=120)
    shadow = shadow.filter(ImageFilter.GaussianBlur(22))
    desk = Image.composite(Image.new("RGB", (w, h), (18, 18, 22)), desk, shadow)
    desk.paste(tilted, (pad_x, pad_y), tilted)

    lamp = Image.linear_gradient("L").rotate(
        40 + int(240 * unit([seed, tag, "lamp"])), resample=Image.BICUBIC
    ).resize((w, h), Image.BILINEAR)
    desk = Image.composite(desk, Image.eval(desk, lambda v: int(v * 0.78)), lamp)

    vignette = Image.new("L", (w, h), 255)
    vd = _Draw.Draw(vignette)
    for n in range(26):
        shade = 255 - int(255 * (1 - n / 26.0))
        vd.rectangle((n * 5, n * 5, w - 1 - n * 5, h - 1 - n * 5), outline=shade)
    vignette = vignette.filter(ImageFilter.GaussianBlur(28))
    desk = Image.composite(desk, Image.eval(desk, lambda v: int(v * 0.6)), vignette)

    desk = desk.filter(ImageFilter.GaussianBlur(0.5))
    speck = Image.frombytes("L", (w // 3, h // 3),
                            noise_bytes([seed, tag, "sensor"], (w // 3) * (h // 3)))
    return Image.blend(desk, speck.resize((w, h), Image.BILINEAR).convert("RGB"), 0.035)


def render_jobsheet(item: dict, seed: str, paths: list) -> None:
    image = photograph(draw_sheet(item, seed), seed, item["file_name"])
    buf = io.BytesIO()
    image.save(buf, "PNG", optimize=False, compress_level=6)
    payload = buf.getvalue()
    for path in paths:
        _put(path, payload)



def speech_text(item: dict) -> str:
    """One paragraph, exactly the sentences the plan wrote for this engineer."""
    return " ".join(item["text"].split())


def _voice_path(explicit) -> str:
    path = explicit or os.environ.get(VOICE_ENV, "").strip()
    if not path:
        raise SystemExit("media.render: no voice model given; set %s or pass --voice" % VOICE_ENV)
    if not os.path.isfile(path):
        raise SystemExit("media.render: voice model not found at %s" % path)
    return path


def speech_seed(seed: str, item: dict) -> int:
    """The runtime seed one voice note speaks under, fixed by the plan and nothing else."""
    return _digest_int([seed, item["file_name"], "speech"]) % SPEECH_SEED_LIMIT


class Speech:
    """A single loaded voice, pinned to one thread and one set of synthesis parameters.

    The parameters are supplied explicitly on every call so that a change of library
    default cannot move a byte: length, noise and noise width are all fixed here.

    The model file is read once. The inference session is rebuilt for every voice note,
    immediately after the runtime seed for that note is set, because the two unseeded
    random nodes in the model read the process-wide seed while the session is being built.
    One thread and sequential execution keep the arithmetic order fixed as well.
    """

    def __init__(self, model: str) -> None:
        from piper import PiperVoice

        self.model = model
        self.voice = PiperVoice.load(model, use_cuda=False)
        self.voice.session = None

    def _session(self, seed_value: int):
        import onnxruntime

        onnxruntime.set_seed(int(seed_value))
        opts = onnxruntime.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        opts.execution_mode = onnxruntime.ExecutionMode.ORT_SEQUENTIAL
        opts.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        return onnxruntime.InferenceSession(
            self.model, sess_options=opts, providers=["CPUExecutionProvider"])

    def wav_bytes(self, text: str, seed_value: int) -> bytes:
        from piper import SynthesisConfig

        cfg = SynthesisConfig(length_scale=LENGTH_SCALE, noise_scale=NOISE_SCALE,
                              noise_w_scale=NOISE_W, normalize_audio=False)
        self.voice.session = self._session(seed_value)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as handle:
            self.voice.synthesize_wav(text, handle, syn_config=cfg)
        return buf.getvalue()


SEED_SHIM = """\
import onnxruntime
onnxruntime.set_seed(%d)
"""


def cli_wav_bytes(model: str, text: str, seed_value: int) -> bytes:
    """The command line path, for a library whose Python surface will not hold still.

    The speech command builds its own session, so the runtime seed is planted ahead of it
    by a start-up module on the import path rather than by an argument the command lacks.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "note.wav")
        shim = os.path.join(tmp, "shim")
        os.makedirs(shim, exist_ok=True)
        with open(os.path.join(shim, "sitecustomize.py"), "w") as handle:
            handle.write(SEED_SHIM % int(seed_value))
        env = dict(os.environ)
        env["PYTHONPATH"] = shim + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["OMP_NUM_THREADS"] = "1"
        cmd = [sys.executable, "-m", "piper", "--model", model, "--output-file", out,
               "--length-scale", repr(LENGTH_SCALE), "--noise-scale", repr(NOISE_SCALE),
               "--noise-w-scale", repr(NOISE_W)]
        proc = subprocess.run(cmd, input=text.encode("ascii", "replace"), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if proc.returncode != 0 or not os.path.isfile(out):
            raise SystemExit("media.render: speech command failed: %s"
                             % proc.stderr.decode("utf-8", "replace").strip()[:400])
        with open(out, "rb") as handle:
            return handle.read()


def normalise_wav(payload: bytes) -> bytes:
    """Re-pack the frames into a bare PCM container, so no library header drifts in."""
    with wave.open(io.BytesIO(payload), "rb") as src:
        channels, width, rate = src.getnchannels(), src.getsampwidth(), src.getframerate()
        frames = src.readframes(src.getnframes())
    out = io.BytesIO()
    with wave.open(out, "wb") as dst:
        dst.setnchannels(channels)
        dst.setsampwidth(width)
        dst.setframerate(rate)
        dst.writeframes(frames)
    return out.getvalue()


def render_handback(item: dict, speech, model: str, mode: str, seed: str, paths: list) -> None:
    text = speech_text(item)
    seed_value = speech_seed(seed, item)
    raw = cli_wav_bytes(model, text, seed_value) if mode == "cli" \
        else speech.wav_bytes(text, seed_value)
    payload = normalise_wav(raw)
    for path in paths:
        _put(path, payload)



def _put(path: str, payload: bytes) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(payload)


def build(root: str, seed: str, input_digest: str, voice, mode: str) -> dict:
    plan = load_plan(seed, input_digest)
    needs_voice = any(item["kind"] == "handback-wav" for item in plan)
    model = _voice_path(voice) if needs_voice else ""
    speech = Speech(model) if (needs_voice and mode == "api") else None

    written, spoken = [], []
    for item in plan:
        paths = targets(root, item)
        if item["kind"] == "jobsheet-png":
            render_jobsheet(item, str(seed), paths)
        elif item["kind"] == "handback-wav":
            render_handback(item, speech, model, mode, str(seed), paths)
            spoken.append(speech_text(item))
        else:
            raise SystemExit("media.render: unknown artefact kind %r" % item["kind"])
        written.append(item["drive_path"])

    drawn = [" ".join(v for _, v in sheet_fields(item))
             for item in plan if item["kind"] == "jobsheet-png"]
    screened = screen_emitted(drawn + spoken + [i["text"] for i in plan])
    return {"artefacts": len(written), "spoken": len(spoken),
            "screen_tokens": screened, "files": written}


def compare(root_a: str, root_b: str) -> list:
    """Paths whose bytes differ between two renders of the same plan."""
    differs = []
    for base, _dirs, names in os.walk(root_a):
        for name in sorted(names):
            left = os.path.join(base, name)
            right = os.path.join(root_b, os.path.relpath(left, root_a))
            if not os.path.isfile(right):
                differs.append(os.path.relpath(left, root_a))
                continue
            with open(left, "rb") as fa, open(right, "rb") as fb:
                if fa.read() != fb.read():
                    differs.append(os.path.relpath(left, root_a))
    return differs


def selfcheck(seed: str, input_digest: str, voice, mode: str) -> dict:
    """Render the whole plan twice into scratch trees and insist the bytes agree."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        first = os.path.join(tmp, "first")
        second = os.path.join(tmp, "second")
        build(first, seed, input_digest, voice, mode)
        build(second, seed, input_digest, voice, mode)
        differs = compare(first, second)
        if differs:
            raise SystemExit("media.render: %d artefact(s) not reproducible: %s"
                             % (len(differs), ", ".join(sorted(differs)[:4])))
        kept = sum(len(names) for _b, _d, names in os.walk(first))
    return {"reproducible": kept}


def resolve_inputs(argv):
    ap = argparse.ArgumentParser(prog="media.render", add_help=True)
    ap.add_argument("--root", default=".")
    ap.add_argument("--seed", default=os.environ.get("COMPLEXMCP_SEED", "4172"))
    ap.add_argument("--input-digest",
                    default=os.environ.get("SLOT_INPUT_DIGEST", "forge-slot-1"))
    ap.add_argument("--voice", default=None,
                    help="path to the speech model; falls back to the voice environment variable")
    ap.add_argument("--speech-mode", choices=("api", "cli"),
                    default=os.environ.get(SPEECH_MODE_ENV, "api"))
    ap.add_argument("--selfcheck", action="store_true",
                    help="render twice into scratch trees and fail on any byte difference")
    ap.add_argument("--sheets-only", action="store_true",
                    help="draw the paper artefacts and leave the spoken ones out")
    return ap.parse_args(argv)


def main(argv=None) -> int:
    import json

    args = resolve_inputs(sys.argv[1:] if argv is None else argv)
    if args.sheets_only:
        global load_plan
        full = load_plan

        def load_plan(seed, input_digest):  # noqa: F811 - narrows the run to the paper legs
            return [i for i in full(seed, input_digest) if i["kind"] == "jobsheet-png"]

    if args.selfcheck:
        print(json.dumps(selfcheck(str(args.seed), str(args.input_digest),
                                   args.voice, args.speech_mode)))
        return 0
    result = build(os.path.abspath(args.root), str(args.seed), str(args.input_digest),
                   args.voice, args.speech_mode)
    print("rendered %d artefact(s) into %s" % (result["artefacts"], args.root))
    for path in result["files"]:
        print("  %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
