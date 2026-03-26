# Add-ons pack for sb3_to_python

This pack adds:
- broad coverage for standard Scratch 3 block categories
- separate official extension addon support
- generic custom-extension fallback for manually-created extensions

## Important
A converter can be made syntax-safe for **all** projects, but it cannot infer the full runtime semantics of every custom extension automatically.
For unknown/manual extensions, this pack emits:
- `custom_call(opcode, args)` for command blocks
- `custom_expr(opcode, args)` for reporter/boolean blocks

That means:
- the generated Python stays valid
- you can then implement each custom extension incrementally

## Files
- `sb3_to_python/addons/official.py`
- `sb3_to_python/addons/custom_generic.py`

## Usage
```bash
python3 convertitore.py your_project.sb3
```
