# SmartHome VA Simulator (Plan-to-Code Scaffold)

## Quick Start

```bash
python run.py --config configs/default.json
```

Output Excel will be saved to `data/output/simulation_output.xlsx`.

## Config
See `configs/default.json` for editable settings:
- `num_users`
- `interaction_iteration` (default 20)
- `utterance_threshold`
- `backup` settings
- `environment` generation options

## Notes
- All interaction outputs are generated in Korean.
- Persona and schedule are generated using the full environment JSON (no summarization).
- Memory is continuously referenced during avatar-related generations.
