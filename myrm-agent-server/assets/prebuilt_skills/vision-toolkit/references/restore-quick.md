# restore-quick

Use for layout and content understanding, not pixel-perfect rebuild.

1. `vision_geometry_tool` pixel_diff only when you need changed areas.
2. `vision_semantic_tool` region mode on diff boxes or small controls.
3. Stop when the user-visible outcome matches the reference intent.

Do not iterate full-page VLM re-describes more than twice.
