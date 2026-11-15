"""Shared data types, normalization and input resolution for media generation.

[OUTPUT]
- types: ModeCapabilities, ProviderModeCapabilities, NormalizationRecord, SizeSpec
- normalization: resolve_closest_ratio, resolve_closest_size, resolve_closest_duration, normalize_params
- input_resolver: MediaInputPolicy, MediaInputError, MediaLoader, resolve_media_inputs

[POS]
Provider mode-capability types and the normalization engine that video generation uses to fit requested parameters to
the values a provider supports, plus the single resolver that turns image and video references into validated bytes.
"""
