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

# ---- prompts ---------------------------------------------------------------
# Shared look-and-feel of the subject.
SUBJECT_STYLE = (
    "handmade crochet amigurumi toy made of yarn, "
    "soft wool yarn texture, visible single crochet stitches, "
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


def build_product_prompt(pattern_data, title="amigurumi"):
    """Turn the analysed pattern into a concrete image prompt."""
    names, colors = [], []
    for p in pattern_data or []:
        if not isinstance(p, dict):
            continue
        n = str(p.get("name") or "").strip()
        c = str(p.get("color") or "").strip()
        if n:
            names.append(n)
        if c:
            colors.append(c)

    animal = title.replace("_", " ").strip() or "cute animal"
    parts = ", ".join(dict.fromkeys(names))[:200]
    col = ", ".join(dict.fromkeys(colors))[:120]

    prompt = f"A crochet amigurumi {animal} made of yarn"
    if col:
        prompt += f", colors: {col}"
    if parts:
        prompt += f" (parts: {parts})"
    return f"{prompt}. {SD_STYLE}"


# --------------------------------------------------------------------------- #
# Workflows (ComfyUI API format)
# --------------------------------------------------------------------------- #
def build_sd_workflow(prompt, negative, ckpt_name, width=512, height=640,
                      steps=25, cfg=7.0, seed=None,
                      sampler="dpmpp_2m", scheduler="karras"):
    """Standard Stable Diffusion txt2img (SD 1.5 / SD 2.x / SDXL checkpoints)."""
    seed = int(seed if seed is not None else time.time() * 1000) % (2 ** 31)
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": ckpt_name}},
        "2": {"class_type": "CLIPTextEncode",
              "inputs": {"text": prompt, "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode",
              "inputs": {"text": negative, "clip": ["1", 1]}},
        "4": {"class_type": "EmptyLatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "5": {"class_type": "KSampler",
              "inputs": {"model": ["1", 0], "positive": ["2", 0], "negative": ["3", 0],
                         "latent_image": ["4", 0], "seed": seed, "steps": steps,
                         "cfg": cfg, "sampler_name": sampler,
                         "scheduler": scheduler, "denoise": 1.0}},
        "6": {"class_type": "VAEDecode",
              "inputs": {"samples": ["5", 0], "vae": ["1", 2]}},
        "7": {"class_type": "SaveImage",
              "inputs": {"filename_prefix": "crochet_preview", "images": ["6", 0]}},
    }


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
             steps=None, guidance=None, seed=None, timeout=1800):
    """Render one image and save it to out_path.

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
        wf = build_sd_workflow(prompt, neg, name, width=w, height=h,
                               steps=st, cfg=cfg, seed=seed)
        print(f"[image] backend=sd checkpoint={name} {w}x{h} steps={st} cfg={cfg}")
    else:
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


if __name__ == "__main__":
    import sys

    print("ComfyUI reachable:", available())
    print("backend:", backend())
    p = sys.argv[1] if len(sys.argv) > 1 else (
        "A crochet amigurumi cat made of yarn, white and grey. " + SD_STYLE)
    out = sys.argv[2] if len(sys.argv) > 2 else (
        r"C:\Users\MSII\AppData\Local\Temp\opencode\cr-vision\sd_test.png")
    generate(p, out)
