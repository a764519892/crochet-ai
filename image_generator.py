"""
Finished-product preview image generation via a local ComfyUI server.

The project ships no image model of its own; instead it talks to a running
ComfyUI instance (default http://127.0.0.1:8188) and renders a
"what it will look like" photo of the finished amigurumi, which is then
embedded in the PDF.

Two backends are supported and auto-detected from what the server has loaded:

  * "sd"   - a regular Stable Diffusion checkpoint (CheckpointLoaderSimple).
             Small (2-4 GB) and comfortable on a 16 GB / 6 GB-VRAM machine.
  * "flux" - FLUX.1-dev (UNETLoader + DualCLIPLoader + VAELoader). Needs a lot
             more memory (unet 11 GB + t5 4.5 GB), only for beefier machines.

Both render from the prompt alone, but when the caller has the original photo we
can do better: `init_image=` runs image-to-image instead, so the render keeps the
pose, proportions and colours of the real photo and only re-renders it as a
handmade crochet version. That is what makes the preview look like the user's own
piece rather than "a" bunny. Set the similarity with `COMFY_DENOISE` (default
0.35: low = very close to the photo, high = more creative).

Everything degrades gracefully: if ComfyUI is not reachable, or has no usable
model, the caller simply skips the image.

Public API:
    available() -> bool
    backend() -> ("sd", name) | ("flux", name) | None
    build_product_prompt(pattern_data, title) -> str
    negative_prompt() -> str
    generate(prompt, out_path, **overrides) -> str | None
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")

# ---- explicit overrides (all optional) -------------------------------------
COMFY_CKPT = os.environ.get("COMFY_CKPT", "")          # e.g. DreamShaper_8_pruned.safetensors
UNET_NAME = os.environ.get("COMFY_UNET", "flux1-dev-fp8.safetensors")
CLIP_L = os.environ.get("COMFY_CLIP_L", "clip_l.safetensors")
CLIP_T5 = os.environ.get("COMFY_CLIP_T5", "t5xxl_fp8_e4m3fn.safetensors")
VAE_NAME = os.environ.get("COMFY_VAE", "ae.safetensors")

# LoRA (SD backend only): "" = auto-pick a crochet-ish lora if one is installed,
# "none"/"off"/"0" = never use one, anything else = that exact file name.
COMFY_LORA = os.environ.get("COMFY_LORA", "")
COMFY_LORA_STRENGTH = float(os.environ.get("COMFY_LORA_STRENGTH", "0.35"))
LORA_HINTS = ("crochet", "amigurumi", "amigurami", "knit", "knitted", "yarn", "wool")

# ---- prompts ---------------------------------------------------------------
# Shared look-and-feel of the subject.
SUBJECT_STYLE = (
    "handmade crochet amigurumi toy made of yarn, "
    "soft fine yarn texture, neat even crochet stitches, "
    "cute kawaii design, standing on a plain light grey surface"
)

# SD checkpoints respond well to a positive quality tail plus a negative list.
SD_STYLE = (
    SUBJECT_STYLE + ", professional product photo, soft even studio lighting, "
    "shallow depth of field, sharp focus, highly detailed, 8k"
)
SD_NEGATIVE = (
    "blurry, lowres, low quality, worst quality, jpeg artifacts, deformed, "
    "disfigured, bad anatomy, extra limbs, extra fingers, fused fingers, "
    "watermark, text, signature, logo, ugly, mutated, cropped, out of frame"
)

# FLUX dev prefers a plain, descriptive sentence and no negative prompt.
FLUX_STYLE = (
    SUBJECT_STYLE + ", professional product photo, soft even studio lighting, "
    "shallow depth of field, sharp focus, high detail, 4k"
)

# Rendering size. SD 1.5 is native at 512; FLUX at 1024.
# Override with COMFY_SIZE (square) or COMFY_WIDTH/COMFY_HEIGHT.
SD_DEFAULT_WIDTH = int(os.environ.get("COMFY_WIDTH", os.environ.get("COMFY_SIZE", "512")))
SD_DEFAULT_HEIGHT = int(os.environ.get("COMFY_HEIGHT", os.environ.get("COMFY_SIZE", "640")))
FLUX_DEFAULT_WIDTH = int(os.environ.get("COMFY_WIDTH", os.environ.get("COMFY_SIZE", "768")))
FLUX_DEFAULT_HEIGHT = int(os.environ.get("COMFY_HEIGHT", os.environ.get("COMFY_SIZE", "768")))

# image-to-image strength when the original photo is available: how much of the
# photo is kept. 0.35 stays very close to the photo (same pose, proportions and
# colours, only the surface re-rendered as yarn); raise it for a freer
# interpretation, lower it and it stops looking handmade.
IMG2IMG_DENOISE = float(os.environ.get("COMFY_DENOISE", "0.35"))

# reference images already pushed to ComfyUI, keyed by (path, mtime, size)
_UPLOADED = {}


def _get(path, timeout=10):
    with urllib.request.urlopen(f"{COMFY_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _post(path, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{COMFY_URL}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _upload_image(path):
    """Copy a local image into ComfyUI's input folder; returns its server name.

    LoadImage can only read files that live inside ComfyUI's own input dir, so
    an image-to-image job has to upload the reference first. Uploads are cached
    per file (path + mtime + size) so rendering N yarn variants uploads once.
    Returns None if the upload fails (the caller then falls back to text-to-image).
    """
    name = os.path.basename(path)
    try:
        key = (os.path.abspath(path), os.path.getmtime(path), os.path.getsize(path))
    except OSError as exc:
        print("[image] cannot stat reference image:", exc)
        return None
    if key in _UPLOADED:
        return _UPLOADED[key]

    try:
        with open(path, "rb") as fh:
            blob = fh.read()
    except OSError as exc:
        print("[image] cannot read reference image:", exc)
        return None

    import mimetypes
    boundary = "----crochetai" + str(int(time.time() * 1000))
    ctype = mimetypes.guess_type(name)[0] or "image/png"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        blob,
        f"\r\n--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(
        f"{COMFY_URL}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode("utf-8"))
    except Exception as exc:
        print("[image] reference upload failed:", exc)
        return None

    server_name = resp.get("name") or name
    sub = resp.get("subfolder") or ""
    full = f"{sub}/{server_name}" if sub else server_name
    print(f"[image] uploaded reference {name} -> {full}")
    _UPLOADED[key] = full
    return full


def available(url=None):
    """True if a ComfyUI server answers."""
    global COMFY_URL
    if url:
        COMFY_URL = url
    try:
        _get("/system_stats", timeout=5)
        return True
    except Exception:
        return False


def _enum(node, field):
    """Pull the allowed values of a combo/COMBO input out of /object_info."""
    try:
        info = _get("/object_info", timeout=60)
        spec = info[node]["input"]["required"][field][0]
        return list(spec) if isinstance(spec, (list, tuple)) else []
    except Exception:
        return []


def backend():
    """Decide which workflow to use. Returns (kind, model_name) or None."""
    ckpts = _enum("CheckpointLoaderSimple", "ckpt_name")
    ckpts = [c for c in ckpts if c.lower().endswith((".safetensors", ".ckpt"))]

    if COMFY_CKPT and COMFY_CKPT in ckpts:
        return ("sd", COMFY_CKPT)
    if ckpts:
        return ("sd", ckpts[0])

    unets = _enum("UNETLoader", "unet_name")
    if unets:
        name = UNET_NAME if UNET_NAME in unets else unets[0]
        return ("flux", name)
    return None


def negative_prompt():
    """Negative prompt used by the SD backend (FLUX ignores it)."""
    return SD_NEGATIVE


def list_loras():
    """LoRA files the ComfyUI server can see."""
    return [l for l in _enum("LoraLoader", "lora_name")
            if l.lower().endswith((".safetensors", ".ckpt", ".pt"))]


def pick_lora():
    """Choose a LoRA for the SD backend, or None.

    Auto mode prefers a file whose name looks crochet/knit related, so dropping
    any amigurumi LoRA into models/loras is enough for it to be picked up.
    """
    if COMFY_LORA.lower() in ("none", "off", "0"):
        return None
    loras = list_loras()
    if COMFY_LORA:
        return COMFY_LORA if COMFY_LORA in loras else None
    for name in loras:
        if any(h in name.lower() for h in LORA_HINTS):
            return name
    return None


def yarn_phrase(key=None):
    """The yarn/hook description from pattern_engine's active preset.

    Kept here (rather than duplicating the hook sizes) so the image and the
    written materials section always describe the same yarn.
    """
    try:
        from pattern_engine import active_yarn
        return active_yarn(key).get("image", "")
    except Exception:
        return ""


def build_product_prompt(pattern_data, title="amigurumi", yarn=None):
    """Turn the analysed pattern into a concrete image prompt.

    `yarn` is a pattern_engine YARN_PRESETS key (None = the configured default),
    which pins the yarn thickness the render should show.
    """
    names, colors, types = [], [], []
    for p in pattern_data or []:
        if not isinstance(p, dict):
            continue
        n = str(p.get("name") or "").strip()
        c = str(p.get("color") or "").strip()
        t = str(p.get("type") or "").strip()
        if n:
            names.append(n)
        if c:
            colors.append(c)
        if t:
            types.append(t)

    animal = title.replace("_", " ").strip() or "cute animal"
    parts = ", ".join(dict.fromkeys(names))[:200]
    col = ", ".join(dict.fromkeys(colors))[:120]

    # A star cushion / blanket / coaster is a flat piece, not a standing toy:
    # saying "amigurumi ... standing" made the model render the wrong thing.
    blob = (f"{animal} {' '.join(names)}").lower()
    is_star = "star" in types or "star" in blob
    is_flat = is_star or any(w in blob for w in (
        "cushion", "pillow", "coaster", "blanket", "potholder", "placemat",
        "garland", "doily"))
    if is_star:
        subject = "A crochet five-pointed star cushion made of yarn"
    elif is_flat:
        subject = f"A crochet {animal} made of yarn"
    else:
        subject = f"A crochet amigurumi {animal} made of yarn"

    prompt = subject
    if col:
        prompt += f", colors: {col}"
    if parts:
        prompt += f" (parts: {parts})"
    phrase = yarn_phrase(yarn)
    if phrase:
        prompt += f", {phrase}"

    style = SD_STYLE
    if is_flat:
        style = (style
                 .replace("standing on a plain light grey surface",
                          "lying flat on a plain light grey surface")
                 .replace("handmade crochet amigurumi toy made of yarn",
                          "handmade crochet item made of yarn")
                 .replace("cute kawaii design", "cute design"))
    return f"{prompt}. {style}"


# --------------------------------------------------------------------------- #
# Workflows (ComfyUI API format)
# --------------------------------------------------------------------------- #
def build_sd_workflow(prompt, negative, ckpt_name, width=512, height=640,
                      steps=25, cfg=7.0, seed=None,
                      sampler="dpmpp_2m", scheduler="karras",
                      lora=None, lora_strength=0.35):
    """Standard Stable Diffusion txt2img (SD 1.5 / SD 2.x / SDXL checkpoints).

    When `lora` is given, a LoraLoader is inserted between the checkpoint and
    everything downstream (prompt encoding and sampling), so both the text
    encoder and the unet see the LoRA.
    """
    seed = int(seed if seed is not None else time.time() * 1000) % (2 ** 31)

    wf = {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
    }

    if lora:
        wf["8"] = {"class_type": "LoraLoader",
                   "inputs": {"lora_name": lora,
                              "strength_model": lora_strength,
                              "strength_clip": lora_strength,
                              "model": ["1", 0], "clip": ["1", 1]}}
        model_ref, clip_ref = ["8", 0], ["8", 1]
    else:
        model_ref, clip_ref = ["1", 0], ["1", 1]

    wf.update({
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": prompt, "clip": clip_ref}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": clip_ref}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": model_ref, "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": steps,
                         "cfg": cfg, "sampler_name": sampler,
                         "scheduler": scheduler, "denoise": 1.0}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "crochet_preview", "images": ["6", 0]}},
    })
    return wf


def build_sd_img2img_workflow(prompt, negative, ckpt_name, image_name,
                              width=512, height=640, steps=25, cfg=7.0,
                              seed=None, denoise=None, sampler="dpmpp_2m",
                              scheduler="karras", lora=None, lora_strength=0.35):
    """Stable Diffusion image-to-image from a reference photo.

    Same graph as build_sd_workflow, but the empty latent is replaced by the
    reference photo: LoadImage -> ImageScale -> VAEEncode -> KSampler(denoise).
    A low denoise keeps the photo's composition and colours.
    """
    dn = IMG2IMG_DENOISE if denoise is None else float(denoise)
    wf = build_sd_workflow(prompt, negative, ckpt_name, width=width, height=height,
                           steps=steps, cfg=cfg, seed=seed, sampler=sampler,
                           scheduler=scheduler, lora=lora, lora_strength=lora_strength)
    wf["9"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf["10"] = {"class_type": "ImageScale",
                "inputs": {"image": ["9", 0], "upscale_method": "lanczos",
                           "width": width, "height": height, "crop": "center"}}
    wf["4"] = {"class_type": "VAEEncode",
               "inputs": {"pixels": ["10", 0], "vae": ["1", 2]}}
    wf["5"]["inputs"]["denoise"] = dn
    return wf


def build_flux_workflow(prompt, negative="", width=768, height=768,
                        steps=20, guidance=3.5, seed=None):
    """FLUX.1-dev txt2img (UNETLoader + DualCLIPLoader + FluxGuidance)."""
    seed = int(seed if seed is not None else time.time() * 1000) % (2 ** 31)
    return {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET_NAME, "weight_dtype": "default"}},
        "2": {"class_type": "DualCLIPLoader",
              "inputs": {"clip_name1": CLIP_T5, "clip_name2": CLIP_L, "type": "flux"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_NAME}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["2", 0]}},
        "5": {"class_type": "FluxGuidance",
              "inputs": {"guidance": guidance, "conditioning": ["4", 0]}},
        "6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "7": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "8": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["5", 0], "negative": ["6", 0],
                         "latent_image": ["7", 0], "seed": seed, "steps": steps,
                         "cfg": 1.0, "sampler_name": "euler",
                         "scheduler": "simple", "denoise": 1.0}},
        "9": {"class_type": "VAEDecode",
              "inputs": {"samples": ["8", 0], "vae": ["3", 0]}},
        "10": {"class_type": "SaveImage",
               "inputs": {"filename_prefix": "crochet_preview", "images": ["9", 0]}},
    }


def generate(prompt, out_path, negative=None, width=None, height=None,
             steps=None, guidance=None, seed=None, timeout=1800,
             init_image=None, denoise=None):
    """Render one image and save it to out_path.

    Pass `init_image` (a local file) to run image-to-image instead of
    text-to-image, so the result follows that reference photo.

    Returns out_path on success, or None if ComfyUI is unavailable / failed.
    """
    if not available():
        print("[image] ComfyUI not reachable at", COMFY_URL)
        return None

    be = backend()
    if be is None:
        print("[image] no usable model found on the ComfyUI server "
              "(no checkpoint and no unet)")
        return None
    kind, name = be

    if kind == "sd":
        neg = negative if negative is not None else SD_NEGATIVE
        w = width or SD_DEFAULT_WIDTH
        h = height or SD_DEFAULT_HEIGHT
        st = steps or 25
        cfg = guidance or 7.0
        lora = pick_lora()
        ref = _upload_image(init_image) if init_image else None
        if ref:
            dn = IMG2IMG_DENOISE if denoise is None else float(denoise)
            wf = build_sd_img2img_workflow(prompt, neg, name, ref, width=w, height=h,
                                           steps=st, cfg=cfg, seed=seed, denoise=dn,
                                           lora=lora, lora_strength=COMFY_LORA_STRENGTH)
            print(f"[image] backend=sd img2img ref={os.path.basename(init_image)} "
                  f"denoise={dn} {w}x{h} steps={st} cfg={cfg}"
                  + (f" lora={lora}@{COMFY_LORA_STRENGTH}" if lora else " lora=none"))
        else:
            wf = build_sd_workflow(prompt, neg, name, width=w, height=h,
                                   steps=st, cfg=cfg, seed=seed,
                                   lora=lora, lora_strength=COMFY_LORA_STRENGTH)
            print(f"[image] backend=sd checkpoint={name} {w}x{h} steps={st} cfg={cfg}"
                  + (f" lora={lora}@{COMFY_LORA_STRENGTH}" if lora else " lora=none"))
    else:
        if init_image:
            print("[image] img2img is only wired up for the SD backend; "
                  "rendering from the prompt instead")
        w = width or FLUX_DEFAULT_WIDTH
        h = height or FLUX_DEFAULT_HEIGHT
        st = steps or 20
        g = guidance or 3.5
        wf = build_flux_workflow(prompt, negative or "", width=w, height=h,
                                 steps=st, guidance=g, seed=seed)
        print(f"[image] backend=flux unet={name} {w}x{h} steps={st} guidance={g}")

    try:
        resp = _post("/prompt", {"prompt": wf})
    except urllib.error.HTTPError as e:
        print("[image] /prompt rejected:", e.read().decode("utf-8", "replace")[:2000])
        return None

    pid = resp.get("prompt_id")
    if not pid:
        print("[image] no prompt_id in response:", resp)
        return None
    print(f"[image] queued prompt {pid}, generating...")

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(2)
        try:
            hist = _get(f"/history/{pid}", timeout=15)
        except Exception:
            continue
        if pid not in hist:
            continue
        entry = hist[pid]
        status = entry.get("status", {})
        if status.get("status_str") == "error":
            print("[image] execution error:", json.dumps(status)[:2000])
            return None
        images = []
        for node_out in entry.get("outputs", {}).values():
            images.extend(node_out.get("images", []))
        if not images:
            print("[image] finished but produced no image")
            return None
        img = images[0]
        q = urllib.parse.urlencode({
            "filename": img["filename"],
            "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output"),
        })
        with urllib.request.urlopen(f"{COMFY_URL}/view?{q}", timeout=60) as r:
            data = r.read()
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"[image] saved {out_path} ({len(data)//1024} KB)")
        return out_path

    print("[image] timed out waiting for ComfyUI")
    return None


# --------------------------------------------------------------------------- #
# Yarn-thickness comparison
# --------------------------------------------------------------------------- #
def _montage(paths, out_path, labels):
    """Lay per-yarn renders side by side with a Chinese label bar on top."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[image] Pillow not available; skipping the comparison strip")
        return None

    items = [(k, p) for k, p in paths.items() if os.path.exists(p)]
    if len(items) < 2:
        return None

    ims = [(k, Image.open(p).convert("RGB")) for k, p in items]
    w, h = ims[0][1].size
    bar = max(36, h // 13)
    fs = int(bar * 0.52)

    sheet = Image.new("RGB", (w * len(ims), h + bar), (250, 246, 240))
    draw = ImageDraw.Draw(sheet)

    font = None
    try:
        from pattern_engine import BeginnerPatternGenerator
        fp = BeginnerPatternGenerator._find_cjk_font()
        if fp:
            font = ImageFont.truetype(fp, fs)
    except Exception:
        pass
    if font is None:
        font = ImageFont.load_default()

    for i, (key, im) in enumerate(ims):
        sheet.paste(im, (i * w, bar))
        label = labels.get(key, key)
        try:
            tw = draw.textlength(label, font=font)
        except Exception:
            tw = draw.textlength(label)
        draw.text((i * w + (w - tw) / 2, (bar - fs) / 2 - 1),
                  label, fill=(60, 50, 45), font=font)
        if i:
            draw.line([(i * w, 0), (i * w, h + bar)], fill=(222, 213, 203), width=2)

    sheet.save(out_path)
    print(f"[image] saved comparison strip {out_path} ({sheet.size[0]}x{sheet.size[1]})")
    return out_path


def render_yarn_variants(pattern_data, title="amigurumi", out_dir="generated_patterns",
                         prefix="preview", yarns=None, selected=None, seed=None,
                         reference=None, denoise=None):
    """Render the same finished product once per yarn thickness.

    Every render shares one seed, so the only difference between them is the
    yarn thickness described in the prompt - which is what makes the resulting
    strip a fair "choose your yarn" comparison.

    `reference` is the user's own photo: when given, each render runs
    image-to-image from it, so the preview looks like *their* piece (same pose,
    proportions and colours) instead of a generic one.

    Returns {"by_yarn": {key: path}, "compare": path|None, "hero": path|None}.
    `hero` is the render of the selected yarn (that is the one embedded as the
    main preview image).
    """
    try:
        from pattern_engine import YARN_PRESETS, DEFAULT_YARN
    except Exception as exc:
        print("[image] cannot import yarn presets:", exc)
        return {"by_yarn": {}, "compare": None, "hero": None}

    keys = list(yarns) if yarns else list(YARN_PRESETS.keys())
    if seed is None:
        seed = int(time.time() * 1000) % (2 ** 31)

    if reference and not os.path.exists(reference):
        print(f"[image] reference photo not found ({reference}); "
              "rendering from the prompt only")
        reference = None

    try:
        from pattern_i18n import yarn_label
    except Exception:
        yarn_label = lambda k: k  # noqa: E731

    mode = "image-to-image from your photo" if reference else "text-to-image"
    print(f"[image] rendering {len(keys)} yarn variants ({mode}) at seed {seed}...")
    paths = {}
    for key in keys:
        prompt = build_product_prompt(pattern_data, title, yarn=key)
        path = os.path.join(out_dir, f"{prefix}_{key}.png")
        if generate(prompt, path, seed=seed, init_image=reference, denoise=denoise):
            paths[key] = path

    if not paths:
        return {"by_yarn": {}, "compare": None, "hero": None}

    labels = {k: yarn_label(k) for k in paths}
    compare = _montage(paths, os.path.join(out_dir, f"{prefix}_yarn_compare.png"),
                       labels) if len(paths) > 1 else None

    hero_key = selected if selected in paths else None
    if hero_key is None:
        hero_key = DEFAULT_YARN if DEFAULT_YARN in paths else next(iter(paths))

    return {"by_yarn": paths, "compare": compare, "hero": paths[hero_key]}


if __name__ == "__main__":
    import sys

    print("ComfyUI reachable:", available())
    print("backend:", backend())
    p = sys.argv[1] if len(sys.argv) > 1 else (
        "A crochet amigurumi cat made of yarn, white and grey. " + SD_STYLE)
    out = sys.argv[2] if len(sys.argv) > 2 else (
        r"C:\Users\MSII\AppData\Local\Temp\opencode\cr-vision\sd_test.png")
    generate(p, out)
