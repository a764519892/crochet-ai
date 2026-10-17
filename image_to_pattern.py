"""
Full Pipeline: Image (and/or notes) to Crochet Pattern PDF.

This CLI mirrors the web app so both paths produce the same document:
  analyze (vision)  ->  materials + round-by-round parts + assembly  ->  PDF

Usage:
  python image_to_pattern.py <image_path> [output_name] [notes]
  python image_to_pattern.py --parts <parts.json> [output_name]

Examples:
  python image_to_pattern.py my_crochet.jpg
  python image_to_pattern.py my_crochet.jpg "Cute Dragon"
  python image_to_pattern.py my_crochet.jpg "Cute Dragon" "blue dragon, ignore the branch"
  python image_to_pattern.py --parts parts.json "Star Pillow"

The --parts form skips the vision model and builds the pattern straight from a
parts list you wrote yourself. This is the CLI equivalent of fixing the AI's
reading in the web app's review step, and it is the reliable path when the
local vision model misreads a photo. parts.json is either a JSON array of
parts, or an object {"creature_type": "...", "parts": [...]}.

Part fields (same vocabulary the vision model emits):
  type      sphere | oval | cylinder | cone | dome | flat_circle | flat_leaf |
            tapered_tube | fan | bird_feet | heart_leaf | wing | petals |
            spikes | bobble | star
  name      free text, e.g. "Star Piece"
  color     free text, e.g. "pink"
  size      tiny | small | medium | large
  count     how many to make
  position  where it attaches, e.g. "top of body"

Example parts.json:
  {
    "creature_type": "star cushion",
    "parts": [
      {"type": "star", "name": "Star Piece", "color": "pink",
       "size": "medium", "count": 2, "position": ""}
    ]
  }
"""

import sys
import os
import json
import traceback
from pathlib import Path

from vision_analyzer import VisionAnalyzer
from pattern_engine import BeginnerPatternGenerator

# Console output on Windows may use a legacy code page that cannot encode every
# character. Write UTF-8 and replace anything unencodable instead of crashing.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


def build_pattern_text(engine, pattern_data, title, lang=None, yarn=None):
    """Assemble the full pattern document the same way the web app does."""
    return engine.build_document(
        pattern_data, title,
        lang=lang or os.environ.get("CROCHET_LANG", "zh"),
        yarn=yarn or os.environ.get("CROCHET_YARN"),
    )


def generate_pattern(pattern_data, creature_type, output_name):
    """Steps 2-4: pattern text -> per-yarn preview images -> PDF.

    Shared by the image path and the hand-written parts path so both produce
    exactly the same document.

    Returns:
        Path to the generated PDF.
    """
    print(f"\n  Detected: {creature_type}  ({len(pattern_data)} parts)")
    for part in pattern_data:
        print(f"    - {part['name']} ({part['type']}) - {part.get('color', 'Unknown')}")

    # ── Step 2: Generate the pattern text (materials + parts + assembly) ──
    print("\n[2/4] Writing materials, rounds, and assembly...")
    engine = BeginnerPatternGenerator()

    try:
        full_pattern = build_pattern_text(engine, pattern_data, output_name)
    except KeyError as key_err:
        print(f"\n[ERROR] Pattern data incomplete: missing {key_err}.")
        print("        Try a simpler image or clearer notes.")
        raise SystemExit(1)

    # ── Step 3: Render finished-product images (one per yarn thickness) ──
    image_path_out = None
    compare_path_out = None
    if os.environ.get("CROCHET_NO_IMAGE"):
        print("\n[3/4] Skipping preview image (CROCHET_NO_IMAGE set).")
    else:
        print("\n[3/4] Rendering finished-product images (one per yarn thickness)...")
        try:
            import image_generator
            if image_generator.available():
                res = image_generator.render_yarn_variants(
                    pattern_data, creature_type, out_dir=".",
                    prefix=f"{output_name}_preview",
                    selected=os.environ.get("CROCHET_YARN"))
                image_path_out = res.get("hero")
                compare_path_out = res.get("compare")
                if not image_path_out:
                    print("      (image generation failed; continuing without it)")
            else:
                print("      ComfyUI not reachable at "
                      f"{image_generator.COMFY_URL} - skipping (start it, or set COMFYUI_URL).")
        except Exception as exc:
            print(f"      image generator unavailable ({exc}); continuing without an image.")
            image_path_out = None
            compare_path_out = None

    # ── Step 4: Save to PDF ──
    print("\n[4/4] Generating PDF...")
    pdf_filename = f"{output_name}_Pattern.pdf"
    engine.save_to_pdf(pdf_filename, full_pattern, image_path=image_path_out,
                       compare_image_path=compare_path_out)

    pdf_path = Path(pdf_filename).resolve()
    print("\n" + "=" * 60)
    print(f"SUCCESS! Pattern saved as: {pdf_path}")
    print("=" * 60)

    return str(pdf_path)


def generate_pattern_from_image(image_path, output_name=None, notes=None):
    """
    Complete pipeline: Image -> Analysis -> Pattern -> PDF.

    Args:
        image_path:  Path to the crochet image
        output_name: Optional name for the PDF (without .pdf). Defaults to the file stem.
        notes:       Optional text that overrides/steers the photo (same as the web "Notes" box).

    Returns:
        Path to the generated PDF.
    """
    print("=" * 60)
    print("CROCHET PATTERN GENERATOR")
    print("=" * 60)

    # ── Step 1: Analyze the image with the local vision model ──
    print("\n[1/4] Analyzing image with AI (two passes)...")
    analyzer = VisionAnalyzer()

    try:
        result = analyzer.analyze(image_path=image_path, user_text=notes)
    except Exception as exc:
        print("\n[ERROR] Could not reach Ollama or the vision model failed.")
        print(f"        {exc}")
        print('        Make sure "ollama serve" is running and the model is installed:')
        print("          ollama pull llava")
        raise SystemExit(1)

    if not result or not result.get("pattern_data"):
        print("\n[ERROR] AI could not identify any parts.")
        print("        Try a clearer image, add notes, or describe the parts in a")
        print("        JSON file and use: image_to_pattern.py --parts parts.json")
        raise SystemExit(1)

    pattern_data = result["pattern_data"]
    creature_type = result.get("creature_type", "unknown")

    if output_name is None:
        output_name = Path(image_path).stem.replace(" ", "_").replace("-", "_")

    return generate_pattern(pattern_data, creature_type, output_name)


def generate_pattern_from_parts_file(parts_file, output_name=None):
    """
    Build the pattern straight from a hand-written parts JSON file, skipping
    the vision model entirely. Same conversion as the AI path, so the output
    is identical in shape.

    Returns:
        Path to the generated PDF.
    """
    print("=" * 60)
    print("CROCHET PATTERN GENERATOR (hand-written parts)")
    print("=" * 60)

    print(f"\n[1/4] Reading parts from {parts_file}...")
    with open(parts_file, encoding="utf-8") as fh:
        data = json.load(fh)

    if isinstance(data, dict):
        parts = data.get("parts", [])
        creature_type = data.get("creature_type", "custom design")
    else:
        parts = data
        creature_type = "custom design"

    if not parts:
        print("\n[ERROR] No parts found in the JSON file.")
        print("        Expected a JSON array of parts, or {\"creature_type\": ..., \"parts\": [...]}")
        raise SystemExit(1)

    analyzer = VisionAnalyzer()
    pattern_data = analyzer.pattern_data_from_parts(parts)

    if output_name is None:
        output_name = Path(parts_file).stem.replace(" ", "_").replace("-", "_")

    return generate_pattern(pattern_data, creature_type, output_name)


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if args else 1)

    try:
        if args[0] == "--parts":
            if len(args) < 2:
                print("[ERROR] --parts needs a JSON file path.")
                sys.exit(1)
            parts_file = args[1]
            out_name = args[2] if len(args) > 2 else None
            if not Path(parts_file).exists():
                print(f"[ERROR] Parts file not found: {parts_file}")
                sys.exit(1)
            generate_pattern_from_parts_file(parts_file, out_name)
        else:
            image_path = args[0]
            out_name = args[1] if len(args) > 1 else None
            user_notes = args[2] if len(args) > 2 else None
            if not Path(image_path).exists():
                print(f"[ERROR] Image not found: {image_path}")
                sys.exit(1)
            generate_pattern_from_image(image_path, out_name, user_notes)
    except SystemExit:
        raise
    except Exception:
        print("\n[ERROR] Unexpected error:")
        traceback.print_exc()
        sys.exit(1)
