# Persona Voice Extraction SOP

## 1. Sample Ingestion & Gating
- Ensure sample input text is >= 300 words.
- If input text is insufficient, prompt the user with 3 style calibration questions.

## 2. Matrix Extraction
- Analyze sample text against the 5 dimensions: Syntactic, Lexical, Tonal, Formatting, Negative.
- Compile into `personal_voice.md`.

## 3. Persistence & Adaptation
- Save extracted profile into memory via `memory_save_tool`.
- On user diff feedback, adjust tone matrix parameters dynamically.
