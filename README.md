# SB3 → Python Converter

Convert `.sb3` files (Scratch / PenguinMod projects) into readable Python code.

---

## 🚀 Quick Start (No Installation)

Run the converter directly from GitHub without downloading anything:

    curl -fsSL https://raw.githubusercontent.com/masai2k/sb3_to_python/main/convertitore.py | python3 - yourfile.sb3

**Example**

    curl -fsSL https://raw.githubusercontent.com/masai2k/sb3_to_python/main/convertitore.py | python3 - samuelchesparalemeleremix.sb3

This will generate:

    samuelchesparalemeleremix.py

---

## 📦 Output

The generated Python file is created in the same folder as the input `.sb3` file.

    project.sb3 → project.py

---

## ⚙️ Alternative Usage (Local)

If you prefer to run it locally:

    git clone https://github.com/masai2k/sb3_to_python.git
    cd sb3_to_python
    python3 convertitore.py yourfile.sb3

### Custom output file

    python3 convertitore.py input.sb3 -o output.py

### Convert only one script/target

    python3 convertitore.py input.sb3 --single-target --target-index 0
