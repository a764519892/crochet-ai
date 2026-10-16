"""
Full Pipeline: Image (and/or notes) to Crochet Pattern PDF.

This CLI mirrors the web app so both paths produce the same document:
  analyze (vision)  ->  materials + round-by-round parts + assembly  ->  PDF

Usage:
  python image_to_pattern.py <image_path> [output_name] [notes]

Examples:
  python image_to_pattern.py my_crochet.jpg
  python image_to_pattern.py my_crochet.jpg "Cute Dragon"
  python image_to_pattern.py my_crochet.jpg "Cute Dragon" "blue dragon, ignore the branch"
"""

import sys
import os
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


def build_pattern_text(engine, pattern_data, title, lang=None):
    """Assemble the full pattern document the same way the web app does."""
    return engine.build_document(pattern_data, title, lang=lang or os.environ.get("CROCHET_LANG", "zh"))


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
        print("        Try a clearer image, or add notes describing what to build.")
        raise SystemExit(1)

    pattern_data = result["pattern_data"]
    creature_type = result.get("creature_type", "unknown")

    print(f"\n  Detected: {creature_type}  ({len(pattern_data)} parts)")
    for part in pattern_data:
        print(f"    - {part['name']} ({part['type']}) - {part.get('color', 'Unknown')}")

    # ── Step 2: Generate the pattern text (materials + parts + assembly) ──
    print("\n[2/4] Writing materials, rounds, and assembly...")
    engine = BeginnerPatternGenerator()

    if output_name is None:
        output_name = Path(image_path).stem.replace(" ", "_").replace("-", "_")

    try:
        full_pattern = build_pattern_text(engine, pattern_data, output_name)
    except KeyError as key_err:
        print(f"\n[ERROR] Pattern data incomplete: missing {key_err}.")
        print("        Try a simpler image or clearer notes.")
        raise SystemExit(1)

    # ── Step 3: Render a finished-product preview image (local ComfyUI) ──
    image_path_out = None
    if os.environ.get("CROCHET_NO_IMAGE"):
        print("\n[3/4] Skipping preview image (CROCHET_NO_IMAGE set).")
    else:
        print("\n[3/4] Rendering finished-product preview image (ComfyUI)...")
        try:
            import image_generator
            if image_generator.available():
                prompt = image_generator.build_product_prompt(pattern_data, creature_type)
                print(f"      prompt: {prompt[:120]}...")
                image_path_out = f"{output_name}_preview.png"
                if not image_generator.generate(prompt, image_path_out):
                    image_path_out = None
                    print("      (image generation failed; continuing without it)")
            else:
                print("      ComfyUI not reachable at "
                      f"{image_generator.COMFY_URL} - skipping (start it, or set COMFYUI_URL).")
        except Exception as exc:
            print(f"      image generator unavailable ({exc}); continuing without an image.")
            image_path_out = None

    # ── Step 4: Save to PDF ──
    print("\n[4/4] Generating PDF...")
    pdf_filename = f"{output_name}_Pattern.pdf"
    engine.save_to_pdf(pdf_filename, full_pattern, image_path=image_path_out)

    pdf_path = Path(pdf_filename).resolve()
    print("\n" + "=" * 60)
    print(f"SUCCESS! Pattern saved as: {pdf_path}")
    print("=" * 60)

    return str(pdf_path)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python image_to_pattern.py <image_path> [output_name] [notes]")
        print("\nExamples:")
        print("  python image_to_pattern.py my_crochet.jpg")
        print('  python image_to_pattern.py my_crochet.jpg "Cute Dragon"')
        print('  python image_to_pattern.py my_crochet.jpg "Cute Dragon" "blue dragon, ignore the branch"')
        sys.exit(1)

    image_path = sys.argv[1]
    out_name = sys.argv[2] if len(sys.argv) > 2 else None
    user_notes = sys.argv[3] if len(sys.argv) > 3 else None

    if not Path(image_path).exists():
        print(f"[ERROR] Image not found: {image_path}")
        sys.exit(1)

    try:
        generate_pattern_from_image(image_path, out_name, user_notes)
    except SystemExit:
        raise
    except Exception:
        print("\n[ERROR] Unexpected error:")
        traceback.print_exc()
        sys.exit(1)
