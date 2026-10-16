"""
Finished-product preview image generation via a local ComfyUI server.

The project ships no image model of its own; instead it talks to a running
ComfyUI instance (default http://127.0.0.1:8188) and runs a standard
FLUX.1-dev text-to-image workflow to render a "what it will look like"
photo of the finished amigurumi, which is then embedded in the PDF.

Everything degrades gracefully: if ComfyUI is not reachable the caller simply
skips the image.

Public API:
    available() -> bool
    build_product_prompt(pattern_data, title) -> str
    generate(prompt, out_path, **overrides) -> str | None
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

COMFY_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188")

# Model files present in the portable ComfyUI install (override via env).
UNET_NAME = os.environ.get("COMFY_UNET", "flux1-dev-fp8.safetensors")
CLIP_L = os.environ.get("COMFY_CLIP_L", "clip_l.safetensors")
CLIP_T5 = os.environ.get("COMFY_CLIP_T5", "t5xxl_fp8_e4m3fn.safetensors")
VAE_NAME = os.environ.get("COMFY_VAE", "ae.safetensors")

STYLE = (
    "professional product photo of a handmade crochet amigurumi toy, "
    "soft wool yarn texture, visible single-crochet stitches, "
    "cute kawaii style, standing on a plain light grey surface, "
    "soft even studio lighting, shallow depth of field, sharp focus, "
    "high detail, 4k"
)

# Rendering size. 1024 is FLUX-native but 6 GB of VRAM needs the smaller
# default; override with COMFY_SIZE (square) or COMFY_WIDTH/COMFY_HEIGHT.
DEFAULT_SIZE = int(os.environ.get("COMFY_SIZE", "768"))
DEFAULT_WIDTH = int(os.environ.get("COMFY_WIDTH", str(DEFAULT_SIZE)))
DEFAULT_HEIGHT = int(os.environ.get("COMFY_HEIGHT", str(DEFAULT_SIZE)))


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


def build_flux_workflow(prompt, negative="", width=1024, height=1024,
                        steps=20, guidance=3.5, seed=None):
    """FLUX.1-dev txt2img in ComfyUI API format.

    Mirrors the known-good workflow already saved in this machine's ComfyUI
    (image_flux.json): UNETLoader + DualCLIPLoader + VAELoader, FluxGuidance,
    ConditioningZeroOut as the negative, plain KSampler (cfg 1, euler, simple).
    """
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
    subject = animal
    # A head + body + ears/tail usually means an animal; keep the title as the subject.
    parts = ", ".join(dict.fromkeys(names))[:200]
    col = ", ".join(dict.fromkeys(colors))[:120]

    prompt = f"A crochet amigurumi {subject}, made of yarn"
    if col:
        prompt += f", colors: {col}"
    if parts:
        prompt += f" (parts: {parts})"
    prompt += f". {STYLE}"
    return prompt


def generate(prompt, out_path, negative="", width=None, height=None,
             steps=20, guidance=3.5, seed=None, timeout=1800):
    """Run the workflow and save the first output image to out_path.

    Returns out_path on success, or None if ComfyUI is unavailable / failed.
    """
    width = DEFAULT_WIDTH if width is None else width
    height = DEFAULT_HEIGHT if height is None else height
    if not available():
        print("[image] ComfyUI not reachable at", COMFY_URL)
        return None

    wf = build_flux_workflow(prompt, negative=negative, width=width,
                             height=height, steps=steps, guidance=guidance, seed=seed)
    try:
        resp = _post("/prompt", {"prompt": wf})
    except urllib.error.HTTPError as e:
        print("[image] /prompt rejected:", e.read().decode("utf-8", "replace")[:2000])
        return None

    pid = resp.get("prompt_id")
    if not pid:
        print("[image] no prompt_id in response:", resp)
        return None
    print(f"[image] queued prompt {pid}, generating…")

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
        # surface execution errors
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
    p = sys.argv[1] if len(sys.argv) > 1 else "a cute crochet amigurumi cat"
    generate(p, r"C:\Users\MSII\AppData\Local\Temp\opencode\cr-vision\flux_test.png")
