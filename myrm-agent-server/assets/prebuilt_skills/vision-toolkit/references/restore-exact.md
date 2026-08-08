# restore-exact

Use only when the user explicitly needs pixel-accurate reproduction.

1. Establish diff regions with `vision_geometry_tool` mode=`pixel_diff`.
2. Crop/read each region with `vision_semantic_tool` mode=`region`.
3. Prefer numeric values from geometry output over VLM guesses.
4. Converge: repeat pixel_diff until no meaningful change or user accepts result.

HiDPI: double-check coordinates before desktop clicks.
