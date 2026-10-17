# Crochet

Turn a photo — or a short description — into a beginner crochet pattern.

Local vision model, local engine, PDF out. No cloud API. Product page: **[gumygam.github.io/crochet-ai](https://gumygam.github.io/crochet-ai/)**

The generator itself is not hosted. Clone this repo and run it on your machine.

## What you get

- Image and/or text in
- Review UI so you can edit detected parts before writing
- Eight+ shape families (sphere, cylinder, cone, leaves, wings, petals, spikes, …)
- Beginner PDF with **Chinese** terms (short/inc/dec, round counts) and assembly
- **Finished-product preview image** (optional, rendered locally with ComfyUI + SD/FLUX)
- CLI for batch use

The pattern document is Chinese by default (`zh`). Set `CROCHET_LANG=en` for the original
English wording.

## Quick start

### 1. Ollama (the local model)

```bash
# https://ollama.com  or:
brew install ollama
ollama pull llava
```

Keep `ollama serve` running in the background if it is not already.

### 2. Install this repo

```bash
git clone https://github.com/GumyGam/crochet-ai.git
cd crochet-ai
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.10+ is enough.

### 3. Web app (recommended)

```bash
source venv/bin/activate
python3 app.py
```

Open **http://localhost:5001**

1. Drop a photo, or type what you want (or both)
2. Click **Analyze** (15–30s typical)
3. Review parts — edit / remove / add
4. **Generate pattern**
5. Download the PDF

### 4. Command line

Same pipeline as the web app — analysis, materials, rounds, assembly, PDF — without the browser.

```bash
source venv/bin/activate
python3 image_to_pattern.py path/to/image.jpg "Cute Dragon"

# optional third argument adds notes (same as the web "Notes" box)
python3 image_to_pattern.py path/to/image.jpg "Cute Dragon" "blue dragon, ignore the branch"
```

Writes `<Name>_Pattern.pdf` next to where you run it. Needs the same local model as the web app
(`ollama serve` running and `llava` installed).

### 5. Finished-product image (optional — needs ComfyUI)

Besides the text pattern, the app can render a **what-it-will-look-like photo** of the
finished amigurumi and drop it into the PDF. This uses a local **ComfyUI** server;
there is no cloud call. If ComfyUI is not running the step is simply skipped.

`image_generator.py` auto-detects what the server has loaded:

| Backend | Detected when | Model size | Notes |
| --- | --- | --- | --- |
| `sd` | a checkpoint exists in `models/checkpoints` | 2–4 GB | Works on a 16 GB RAM / 6 GB VRAM laptop. Used first. |
| `flux` | no checkpoint, but a unet in `models/unet` | ~16 GB | Needs a lot of memory (unet 11 GB + t5 4.5 GB). Only for beefier machines. |

For the `sd` backend a **LoRA** makes the render look like real crochet. Drop any
SD 1.5 amigurumi/crochet LoRA into `models/loras` and it is picked up automatically
(the file name is matched against crochet/amigurumi/knit/yarn/wool). For example
`WorldOfCrochet.safetensors`; set `COMFY_LORA=none` to turn it off or
`COMFY_LORA=<file>` to force one. `COMFY_LORA_STRENGTH` (default `0.35`) sets how
strong the crochet texture is — lower is subtler.

**Yarn thickness** is a single setting shared by the written pattern and the image,
so the two always agree. Pick it in the web UI (*Yarn / hook*), or with the
`CROCHET_YARN` environment variable / the `yarn` request field:

| Key | Yarn | Hook |
| --- | --- | --- |
| `milk_cotton` (default) | 4-ply milk cotton (fine) | 2.0–2.5 mm |
| `sport` | Sport / DK (Fine #2-3) | 2.5–3.0 mm |
| `worsted` | Worsted (Medium #4) | 3.5 mm (E/4) |
| `bulky` | Bulky (Chunky #5) | 4.0–5.0 mm |

The chosen yarn is written into the PDF materials section *and* added to the image
prompt, so a "4-ply milk cotton" pattern is previewed with fine, tight stitches
rather than chunky ones.

Start ComfyUI (the portable build works well), then run the app normally:

```bash
# in the ComfyUI portable folder (low-VRAM cards need --lowvram)
python_embeded\python.exe -s ComfyUI\main.py --lowvram --disable-all-custom-nodes
```

Relevant settings (all optional, environment variables):

| Variable | Default | Meaning |
| --- | --- | --- |
| `COMFYUI_URL` | `http://127.0.0.1:8188` | ComfyUI server |
| `COMFY_CKPT` | first checkpoint found | force a specific checkpoint file |
| `COMFY_LORA` | auto (first crochet-ish file) | LoRA file name; `none` disables it |
| `COMFY_LORA_STRENGTH` | `0.35` | LoRA weight (lower = subtler crochet texture) |
| `CROCHET_YARN` | `milk_cotton` | yarn/hook preset (see the table above) |
| `COMFY_SIZE` | `512x640` (`sd`) / `768` (`flux`) | render size; lower = less memory |
| `COMFY_UNET` / `COMFY_CLIP_T5` / `COMFY_CLIP_L` / `COMFY_VAE` | FLUX dev fp8 names | FLUX model files |
| `CROCHET_NO_IMAGE` | unset | set to `1` to skip image generation entirely |

In the web UI there is a checkbox next to **Generate pattern**. On the CLI the image is
produced automatically; `<Name>_preview.png` appears next to the PDF.

### 6. Chinese pattern output

`pattern_engine.BeginnerPatternGenerator(lang="zh")` builds the document in Chinese;
`pattern_i18n.py` does the translation (part names, colours, positions, stitches, tips,
assembly). The PDF embeds a CJK font automatically — override the font path with
`CROCHET_CJK_FONT` (defaults to `C:\Windows\Fonts\simhei.ttf` on Windows, Noto/WenQuanYi on
Linux, PingFang on macOS).

## How it is put together

```
photo and/or text
        │
        ▼
 Ollama (llava) — names parts and colors
        │
        ▼
 review UI — you correct the list
        │
        ▼
 pattern engine — rounds, counts, assembly
        │
        ▼
 PDF
```

Shape notes: [SHAPE_TYPES.md](SHAPE_TYPES.md)

## Project layout

```
app.py                 Flask app (localhost:5001)
pattern_engine.py      Round-by-round writing
pattern_i18n.py        English -> Chinese translation of the document
image_generator.py     Finished-product image via local ComfyUI (FLUX)
vision_analyzer.py     Ollama vision
image_to_pattern.py    CLI
templates/index.html   Desk UI
static/studio.css      Shared look
docs/                  GitHub Pages product page
requirements.txt
```

## Tips

Good photos: clear light, simple background, shapes readable from the front.

Useful notes: “blue octopus, eight legs”, “ignore the branch”, “small ears”.

## Troubleshooting

**Ollama not found** — install from [ollama.com](https://ollama.com) or `brew install ollama`.

**llava missing** — `ollama pull llava`.

**Port 5001 busy** — change `port=` at the bottom of `app.py`.

**Pattern is off** — try another angle, or add notes, then edit parts in the review step.

## License

MIT. Generated patterns are yours.

Pattern style is inspired by public beginner amigurumi teaching (including [The Woobles](https://thewoobles.com/)). This project is not affiliated with them.

Powered locally by [Ollama](https://ollama.com/) and llava.
