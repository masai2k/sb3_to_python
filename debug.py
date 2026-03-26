#!/usr/bin/env python3
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

BASE_RAW = "https://raw.githubusercontent.com/masai2k/sb3_to_python/main"


CPP_DEBUGGER_SOURCE = r"""
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <regex>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

namespace fs = std::filesystem;

struct CompileError {
    int line = -1;
    int column = -1;
    std::string message;
    std::string raw;
};

static std::string trim(const std::string& s) {
    size_t a = 0;
    while (a < s.size() && std::isspace(static_cast<unsigned char>(s[a]))) ++a;
    size_t b = s.size();
    while (b > a && std::isspace(static_cast<unsigned char>(s[b - 1]))) --b;
    return s.substr(a, b - a);
}

static std::string shellQuote(const std::string& s) {
    std::string out = "'";
    for (char c : s) {
        if (c == '\'') out += "'\\''";
        else out += c;
    }
    out += "'";
    return out;
}

static std::string runCommand(const std::string& cmd) {
    std::array<char, 4096> buffer{};
    std::string result;
    FILE* pipe = popen(cmd.c_str(), "r");
    if (!pipe) throw std::runtime_error("Failed to run command: " + cmd);
    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe)) {
        result += buffer.data();
    }
    pclose(pipe);
    return result;
}

static std::optional<CompileError> compilePythonFile(const fs::path& filePath) {
    std::string cmd = "python3 -m py_compile " + shellQuote(filePath.string()) + " 2>&1";
    std::string output = runCommand(cmd);
    if (output.empty()) return std::nullopt;

    CompileError err;
    err.raw = output;

    std::smatch m;
    std::regex lineRe(R"(line\s+(\d+))");
    if (std::regex_search(output, m, lineRe)) err.line = std::stoi(m[1]);

    std::regex colRe(R"((column|colonna)\s+(\d+))", std::regex::icase);
    if (std::regex_search(output, m, colRe)) err.column = std::stoi(m[2]);

    std::istringstream iss(output);
    std::string line, lastNonEmpty;
    while (std::getline(iss, line)) {
        if (!trim(line).empty()) lastNonEmpty = trim(line);
    }
    err.message = lastNonEmpty;
    return err;
}

static int countUnclosedBeforeComment(const std::string& line) {
    bool inSingle = false, inDouble = false, escape = false;
    int depth = 0;
    for (char c : line) {
        if (escape) { escape = false; continue; }
        if (c == '\\') { escape = true; continue; }
        if (!inDouble && c == '\'') { inSingle = !inSingle; continue; }
        if (!inSingle && c == '"') { inDouble = !inDouble; continue; }
        if (inSingle || inDouble) continue;
        if (c == '#') break;
        if (c == '(') ++depth;
        else if (c == ')' && depth > 0) --depth;
    }
    return depth;
}

static bool stripInlineTodoInsideCall(std::string& line) {
    auto pos = line.find("# TODO");
    if (pos == std::string::npos) pos = line.find("# unsupported");
    if (pos == std::string::npos) return false;

    int depth = countUnclosedBeforeComment(line);
    if (depth <= 0) return false;

    std::string before = trim(line.substr(0, pos));
    line = before + std::string(depth, ')');
    return true;
}

static bool fixTrailingColon(std::string& line) {
    std::string t = trim(line);
    if ((t == "else" || t == "try" || t == "finally") && !t.empty() && t.back() != ':') {
        line += ":";
        return true;
    }
    if (std::regex_search(t, std::regex(R"(^(if|elif|while|for|def|class|with|except)\b)")) && !t.empty() && t.back() != ':') {
        line += ":";
        return true;
    }
    return false;
}

static bool fixUnclosedParens(std::string& line) {
    bool inSingle = false, inDouble = false, escape = false;
    int open = 0;
    for (char c : line) {
        if (escape) { escape = false; continue; }
        if (c == '\\') { escape = true; continue; }
        if (!inDouble && c == '\'') { inSingle = !inSingle; continue; }
        if (!inSingle && c == '"') { inDouble = !inDouble; continue; }
        if (inSingle || inDouble) continue;
        if (c == '#') break;
        if (c == '(') ++open;
        else if (c == ')' && open > 0) --open;
    }
    if (open > 0) {
        line += std::string(open, ')');
        return true;
    }
    return false;
}

static bool quoteBareSingleArgument(std::string& line) {
    std::smatch m;
    std::regex re(R"(^(\s*(?:print|input|set_costume|set_backdrop|localstorage_set_project_id)\s*\()([A-Za-z_][A-Za-z0-9_ ]*)(\)\s*)$)");
    if (std::regex_match(line, m, re)) {
        std::string arg = trim(m[2]);
        if (arg != "True" && arg != "False" && arg != "None") {
            line = m[1].str() + "\"" + arg + "\"" + m[3].str();
            return true;
        }
    }
    return false;
}

static bool applyHeuristicFix(std::vector<std::string>& lines, const CompileError& err) {
    bool changed = false;

    auto applyTo = [&](int idx) {
        if (idx < 0 || idx >= static_cast<int>(lines.size())) return;
        changed |= stripInlineTodoInsideCall(lines[idx]);
        changed |= fixTrailingColon(lines[idx]);
        changed |= quoteBareSingleArgument(lines[idx]);
        changed |= fixUnclosedParens(lines[idx]);
    };

    if (err.line > 0) {
        for (int off = -2; off <= 2; ++off) applyTo(err.line - 1 + off);
    }

    for (auto& line : lines) {
        if (line.find("# TODO expr") != std::string::npos || line.find("# unsupported") != std::string::npos) {
            changed |= stripInlineTodoInsideCall(line);
        }
    }

    return changed;
}

static std::vector<std::string> readLines(const fs::path& p) {
    std::ifstream in(p);
    if (!in) throw std::runtime_error("Cannot open input file: " + p.string());
    std::vector<std::string> lines;
    std::string line;
    while (std::getline(in, line)) lines.push_back(line);
    return lines;
}

static void writeLines(const fs::path& p, const std::vector<std::string>& lines) {
    std::ofstream out(p);
    if (!out) throw std::runtime_error("Cannot write output file: " + p.string());
    for (size_t i = 0; i < lines.size(); ++i) {
        out << lines[i];
        if (i + 1 < lines.size()) out << '\n';
    }
}

static fs::path buildDebuggedPath(const fs::path& inputPy) {
    return inputPy.parent_path() / (inputPy.stem().string() + "debuggato.py");
}

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cerr << "Usage: sb3_debugger yourfile.py [max_passes]\\n";
        return 1;
    }

    fs::path pyPath = argv[1];
    int maxPasses = 10;
    if (argc >= 3) {
        try {
            maxPasses = std::max(1, std::stoi(argv[2]));
        } catch (...) {
            std::cerr << "Invalid max_passes value.\\n";
            return 1;
        }
    }

    if (!fs::exists(pyPath)) {
        std::cerr << "Python file not found: " << pyPath << "\\n";
        return 1;
    }

    try {
        auto lines = readLines(pyPath);
        fs::path debuggedPath = buildDebuggedPath(pyPath);
        writeLines(debuggedPath, lines);

        bool fixedSomething = false;

        for (int pass = 1; pass <= maxPasses; ++pass) {
            auto err = compilePythonFile(debuggedPath);
            if (!err.has_value()) {
                std::cout << "Generated debugged file: " << debuggedPath << "\\n";
                if (!fixedSomething) std::cout << "No fixes were necessary.\\n";
                return 0;
            }

            auto before = lines;
            bool changed = applyHeuristicFix(lines, *err);

            if (!changed || lines == before) {
                std::cerr << "Could not safely auto-fix this error.\\n";
                std::cerr << err->raw << "\\n";
                return 2;
            }

            fixedSomething = true;
            writeLines(debuggedPath, lines);
        }

        std::cerr << "Reached max passes.\\n";
        return 3;
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << "\\n";
        return 1;
    }
}
"""


def write_cpp_debugger(base_dir: Path) -> Path:
    cpp_path = base_dir / "sb3_debugger.cpp"
    cpp_path.write_text(CPP_DEBUGGER_SOURCE, encoding="utf-8")
    return cpp_path


def compile_cpp_debugger(cpp_path: Path) -> Path:
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise RuntimeError("C++ compiler not found. Install g++ or clang++.")
    exe_path = cpp_path.with_suffix("")
    subprocess.run([compiler, "-std=c++17", "-O2", str(cpp_path), "-o", str(exe_path)], check=True)
    return exe_path


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 debug.py yourfile.py", file=sys.stderr)
        return 1

    py_path = Path(sys.argv[1]).expanduser().resolve()
    if not py_path.exists():
        print(f"File not found: {py_path}", file=sys.stderr)
        return 1
    if py_path.suffix.lower() != ".py":
        print("Input must be a .py file.", file=sys.stderr)
        return 1

    cpp_path = write_cpp_debugger(py_path.parent)
    exe_path = compile_cpp_debugger(cpp_path)
    subprocess.run([str(exe_path), str(py_path)], check=True)
    print(py_path.with_name(py_path.stem + "debuggato.py"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
