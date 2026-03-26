#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path


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
        std::cerr << "Usage: sb3_debugger yourfile.py [max_passes]\n";
        return 1;
    }

    fs::path pyPath = argv[1];
    int maxPasses = 10;
    if (argc >= 3) {
        try {
            maxPasses = std::max(1, std::stoi(argv[2]));
        } catch (...) {
            std::cerr << "Invalid max_passes value.\n";
            return 1;
        }
    }

    if (!fs::exists(pyPath)) {
        std::cerr << "Python file not found: " << pyPath << "\n";
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
                std::cout << "Generated debugged file: " << debuggedPath << "\n";
                if (!fixedSomething) std::cout << "No fixes were necessary.\n";
                return 0;
            }

            auto before = lines;
            bool changed = applyHeuristicFix(lines, *err);

            if (!changed || lines == before) {
                std::cerr << "Could not safely auto-fix this error.\n";
                std::cerr << err->raw << "\n";
                return 2;
            }

            fixedSomething = true;
            writeLines(debuggedPath, lines);
        }

        std::cerr << "Reached max passes.\n";
        return 3;
    } catch (const std::exception& ex) {
        std::cerr << "Error: " << ex.what() << "\n";
        return 1;
    }
}
"""


def py_literal(value):
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return str(value)

    s = str(value)
    try:
        float(s)
        return s
    except ValueError:
        return repr(s)


def sanitize_name(name):
    s = str(name or "").strip()
    if not s:
        return "scratch_var"
    s = re.sub(r"[^a-zA-Z0-9_]", "_", s)
    if re.match(r"^[0-9]", s):
        s = "_" + s
    return s


def indent(text, level=1):
    pad = "    " * level
    lines = text.splitlines() or ["pass"]
    return "\n".join((pad + line) if line.strip() else line for line in lines)


class SB3ToPythonConverter:
    def __init__(self, project_data, single_target=False, target_index=0):
        self.project_data = project_data
        self.single_target = single_target
        self.target_index = target_index
        self.unsupported_exprs = set()
        self.unsupported_blocks = set()

    def extract_targets(self):
        targets = self.project_data.get("targets", [])
        if self.single_target:
            if self.target_index < 0 or self.target_index >= len(targets):
                raise IndexError(f"Target index {self.target_index} out of range.")
            return [targets[self.target_index]]
        return targets

    def collect_variables(self, target):
        vars_by_id = {}
        for var_id, var_data in target.get("variables", {}).items():
            vars_by_id[var_id] = sanitize_name(var_data[0] if isinstance(var_data, list) and var_data else var_id)
        return vars_by_id

    def collect_lists(self, target):
        lists_by_id = {}
        for list_id, list_data in target.get("lists", {}).items():
            lists_by_id[list_id] = sanitize_name(list_data[0] if isinstance(list_data, list) and list_data else list_id)
        return lists_by_id

    def get_variable_name_from_field(self, field_value, variables_by_id):
        if not field_value or not isinstance(field_value, list):
            return "scratch_var"
        if len(field_value) >= 2 and field_value[1] in variables_by_id:
            return variables_by_id[field_value[1]]
        return sanitize_name(field_value[0])

    def get_list_name_from_field(self, field_value, lists_by_id):
        if not field_value or not isinstance(field_value, list):
            return "scratch_list"
        if len(field_value) >= 2 and field_value[1] in lists_by_id:
            return lists_by_id[field_value[1]]
        return sanitize_name(field_value[0])

    def is_block_ref(self, value, blocks):
        return isinstance(value, str) and value in blocks

    def parse_input_literal(self, value):
        if isinstance(value, list):
            if len(value) >= 2:
                return py_literal(value[1])
            if len(value) == 1:
                return py_literal(value[0])
        return py_literal(value)

    def get_input_expr(self, block, input_name, blocks, variables_by_id, lists_by_id):
        inp = block.get("inputs", {}).get(input_name)
        if not inp or not isinstance(inp, list) or len(inp) < 2:
            return "None"
        raw = inp[1]
        if self.is_block_ref(raw, blocks):
            return self.convert_expr(blocks[raw], blocks, variables_by_id, lists_by_id)
        return self.parse_input_literal(raw)

    def get_substack_id(self, block, input_name):
        inp = block.get("inputs", {}).get(input_name)
        if not inp or not isinstance(inp, list) or len(inp) < 2:
            return None
        return inp[1] if isinstance(inp[1], str) else None

    def convert_expr(self, block, blocks, variables_by_id, lists_by_id):
        if not block:
            return "None"
        op = block.get("opcode", "")

        binary = {
            "operator_add": "+",
            "operator_subtract": "-",
            "operator_multiply": "*",
            "operator_divide": "/",
            "operator_equals": "==",
            "operator_gt": ">",
            "operator_lt": "<",
            "operator_and": "and",
            "operator_or": "or",
            "operator_mod": "%",
        }
        if op in binary:
            left_name = "NUM1" if "NUM1" in block.get("inputs", {}) else "OPERAND1"
            right_name = "NUM2" if "NUM2" in block.get("inputs", {}) else "OPERAND2"
            return f"({self.get_input_expr(block, left_name, blocks, variables_by_id, lists_by_id)} {binary[op]} {self.get_input_expr(block, right_name, blocks, variables_by_id, lists_by_id)})"

        if op == "operator_not":
            return f"(not {self.get_input_expr(block, 'OPERAND', blocks, variables_by_id, lists_by_id)})"
        if op == "operator_join":
            return f"(str({self.get_input_expr(block, 'STRING1', blocks, variables_by_id, lists_by_id)}) + str({self.get_input_expr(block, 'STRING2', blocks, variables_by_id, lists_by_id)}))"
        if op == "operator_length":
            return f"(len(str({self.get_input_expr(block, 'STRING', blocks, variables_by_id, lists_by_id)})))"
        if op == "operator_contains":
            return f"(str({self.get_input_expr(block, 'STRING2', blocks, variables_by_id, lists_by_id)}) in str({self.get_input_expr(block, 'STRING1', blocks, variables_by_id, lists_by_id)}))"
        if op == "operator_letter_of":
            return f"(str({self.get_input_expr(block, 'STRING', blocks, variables_by_id, lists_by_id)})[max(0, int({self.get_input_expr(block, 'LETTER', blocks, variables_by_id, lists_by_id)}) - 1)])"
        if op == "operator_round":
            return f"(round({self.get_input_expr(block, 'NUM', blocks, variables_by_id, lists_by_id)}))"

        if op == "data_variable":
            return self.get_variable_name_from_field(block.get("fields", {}).get("VARIABLE"), variables_by_id)
        if op == "sensing_answer":
            return "answer"
        if op == "sensing_username":
            return "username"

        self.unsupported_exprs.add(op)
        return "None"

    def convert_block(self, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")
        if op == "event_whenflagclicked":
            return None

        if op == "looks_say":
            return f"print({self.get_input_expr(block, 'MESSAGE', blocks, variables_by_id, lists_by_id)})"
        if op == "looks_sayforsecs":
            return f"print({self.get_input_expr(block, 'MESSAGE', blocks, variables_by_id, lists_by_id)})\ntime.sleep({self.get_input_expr(block, 'SECS', blocks, variables_by_id, lists_by_id)})"
        if op == "looks_switchcostumeto":
            return f"set_costume({self.get_input_expr(block, 'COSTUME', blocks, variables_by_id, lists_by_id)})"
        if op == "looks_switchbackdropto":
            return f"set_backdrop({self.get_input_expr(block, 'BACKDROP', blocks, variables_by_id, lists_by_id)})"

        if op == "sensing_askandwait":
            return f"answer = input(str({self.get_input_expr(block, 'QUESTION', blocks, variables_by_id, lists_by_id)}) + ' ')"

        if op == "data_setvariableto":
            return f"{self.get_variable_name_from_field(block.get('fields', {}).get('VARIABLE'), variables_by_id)} = {self.get_input_expr(block, 'VALUE', blocks, variables_by_id, lists_by_id)}"
        if op == "data_changevariableby":
            return f"{self.get_variable_name_from_field(block.get('fields', {}).get('VARIABLE'), variables_by_id)} += {self.get_input_expr(block, 'VALUE', blocks, variables_by_id, lists_by_id)}"

        if op == "data_addtolist":
            return f"{self.get_list_name_from_field(block.get('fields', {}).get('LIST'), lists_by_id)}.append({self.get_input_expr(block, 'ITEM', blocks, variables_by_id, lists_by_id)})"

        if op == "control_wait":
            return f"time.sleep({self.get_input_expr(block, 'DURATION', blocks, variables_by_id, lists_by_id)})"
        if op == "control_forever":
            sub = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else "pass"
            return f"while True:\n{indent(body)}"
        if op == "control_repeat":
            sub = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else "pass"
            return f"for _ in range(int({self.get_input_expr(block, 'TIMES', blocks, variables_by_id, lists_by_id)})):\n{indent(body)}"
        if op == "control_repeat_until":
            sub = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else "pass"
            return f"while not ({self.get_input_expr(block, 'CONDITION', blocks, variables_by_id, lists_by_id)}):\n{indent(body)}"
        if op == "control_if":
            sub = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else "pass"
            return f"if {self.get_input_expr(block, 'CONDITION', blocks, variables_by_id, lists_by_id)}:\n{indent(body)}"
        if op == "control_if_else":
            s1 = self.get_substack_id(block, "SUBSTACK")
            s2 = self.get_substack_id(block, "SUBSTACK2")
            b1 = self.convert_stack(s1, blocks, variables_by_id, lists_by_id) if s1 else "pass"
            b2 = self.convert_stack(s2, blocks, variables_by_id, lists_by_id) if s2 else "pass"
            return f"if {self.get_input_expr(block, 'CONDITION', blocks, variables_by_id, lists_by_id)}:\n{indent(b1)}\nelse:\n{indent(b2)}"

        if op == "motion_movesteps":
            return f"move_steps({self.get_input_expr(block, 'STEPS', blocks, variables_by_id, lists_by_id)})"
        if op == "motion_turnright":
            return f"turn_right({self.get_input_expr(block, 'DEGREES', blocks, variables_by_id, lists_by_id)})"
        if op == "motion_turnleft":
            return f"turn_left({self.get_input_expr(block, 'DEGREES', blocks, variables_by_id, lists_by_id)})"
        if op == "motion_gotoxy":
            return f"go_to_xy({self.get_input_expr(block, 'X', blocks, variables_by_id, lists_by_id)}, {self.get_input_expr(block, 'Y', blocks, variables_by_id, lists_by_id)})"

        if op == "localstorage_setProjectId":
            return f"localstorage_set_project_id({self.get_input_expr(block, 'TEXT', blocks, variables_by_id, lists_by_id)})"
        if op == "localstorage_set":
            return f"localstorage_set({self.get_input_expr(block, 'KEY', blocks, variables_by_id, lists_by_id)}, {self.get_input_expr(block, 'VALUE', blocks, variables_by_id, lists_by_id)})"

        self.unsupported_blocks.add(op)
        return f"# TODO block: {op}"

    def convert_stack(self, start_id, blocks, variables_by_id, lists_by_id):
        out = []
        current = start_id
        visited = set()
        while current and current in blocks:
            if current in visited:
                out.append("# TODO block cycle detected")
                break
            visited.add(current)
            code = self.convert_block(blocks[current], blocks, variables_by_id, lists_by_id)
            if code:
                out.append(code)
            current = blocks[current].get("next")
        return "\n".join(out) if out else "pass"

    def convert_target(self, target, target_index):
        blocks = target.get("blocks", {})
        variables_by_id = self.collect_variables(target)
        lists_by_id = self.collect_lists(target)

        target_name = target.get("name", f"target_{target_index}")
        safe_target_name = sanitize_name(target_name)
        scripts = []

        for block_id, block in blocks.items():
            if block.get("topLevel") and block.get("opcode") == "event_whenflagclicked":
                body = self.convert_stack(block.get("next"), blocks, variables_by_id, lists_by_id) if block.get("next") else "pass"
                scripts.append((f"{safe_target_name}_when_green_flag_{len(scripts)+1}", body))

        parts = [f"# ===== Target: {target_name} ====="]

        for var_id, var_data in target.get("variables", {}).items():
            initial = var_data[1] if isinstance(var_data, list) and len(var_data) > 1 else 0
            parts.append(f"{variables_by_id[var_id]} = {py_literal(initial)}")

        for list_id, list_data in target.get("lists", {}).items():
            initial = list_data[1] if isinstance(list_data, list) and len(list_data) > 1 and isinstance(list_data[1], list) else []
            parts.append(f"{lists_by_id[list_id]} = {repr(initial)}")

        if len(parts) > 1:
            parts.append("")

        for name, body in scripts:
            parts.append(f"def {name}():")
            parts.append(indent(body))
            parts.append("")

        return "\n".join(parts).rstrip(), [name for name, _ in scripts]

    def convert_project(self):
        targets = self.extract_targets()
        out = [
            "# Auto-generated from .sb3",
            "import time",
            "import threading",
            "",
            "answer = ''",
            "username = 'user'",
            "",
            "def set_costume(value):",
            "    pass",
            "",
            "def set_backdrop(value):",
            "    pass",
            "",
            "def move_steps(value):",
            "    pass",
            "",
            "def turn_right(value):",
            "    pass",
            "",
            "def turn_left(value):",
            "    pass",
            "",
            "def go_to_xy(x, y):",
            "    pass",
            "",
            "def localstorage_set_project_id(value):",
            "    pass",
            "",
            "def localstorage_set(key, value):",
            "    pass",
            "",
        ]

        functions = []
        for i, target in enumerate(targets):
            code, names = self.convert_target(target, i)
            out.extend([code, ""])
            functions.extend(names)

        out.append("if __name__ == '__main__':")
        if functions:
            out.append("    threads = []")
            for fn in functions:
                out.append(f"    t = threading.Thread(target={fn}, daemon=True)")
                out.append("    threads.append(t)")
                out.append("    t.start()")
            out.append("    try:")
            out.append("        while True:")
            out.append("            time.sleep(0.1)")
            out.append("    except KeyboardInterrupt:")
            out.append("        pass")
        else:
            out.append("    pass")

        if self.unsupported_blocks or self.unsupported_exprs:
            out.append("")
            out.append("# Unsupported elements detected during conversion:")
            for op in sorted(self.unsupported_blocks):
                out.append(f"# unsupported block: {op}")
            for op in sorted(self.unsupported_exprs):
                out.append(f"# unsupported expr: {op}")

        return "\n".join(out)


def load_project_json_from_sb3(sb3_path):
    with zipfile.ZipFile(sb3_path, "r") as zf:
        with zf.open("project.json") as f:
            return json.load(f)


def build_output_path(input_path, output_path=None):
    return Path(output_path) if output_path else Path(input_path).with_suffix(".py")


def build_debugged_output_path(py_path):
    py_path = Path(py_path)
    return py_path.with_name(py_path.stem + "debuggato.py")


def write_cpp_debugger(base_dir):
    cpp_path = Path(base_dir) / "sb3_debugger.cpp"
    cpp_path.write_text(CPP_DEBUGGER_SOURCE, encoding="utf-8")
    return cpp_path


def compile_cpp_debugger(cpp_path):
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler:
        raise RuntimeError("C++ compiler not found. Install g++ or clang++.")
    exe_path = cpp_path.with_suffix("")
    cmd = [compiler, "-std=c++17", "-O2", str(cpp_path), "-o", str(exe_path)]
    subprocess.run(cmd, check=True)
    return exe_path


def run_cpp_debugger(exe_path, py_path, max_passes=10):
    subprocess.run([str(exe_path), str(py_path), str(max_passes)], check=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Convert .sb3 files to Python and generate a debugged Python file using C++.")
    parser.add_argument("input", help="Input .sb3 file")
    parser.add_argument("-o", "--output", help="Output .py file")
    parser.add_argument("--single-target", action="store_true", help="Convert only one target")
    parser.add_argument("--target-index", type=int, default=0, help="Target index to convert when using --single-target")
    parser.add_argument("--no-cpp-debug", action="store_true", help="Skip the C++ debugger stage")
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        print(f"Error: file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        project_data = load_project_json_from_sb3(input_path)
        converter = SB3ToPythonConverter(
            project_data,
            single_target=args.single_target,
            target_index=args.target_index
        )
        python_code = converter.convert_project()
        py_path = build_output_path(input_path, args.output)
        py_path.write_text(python_code, encoding="utf-8")
        print(f"Generated Python: {py_path}")

        if not args.no_cpp_debug:
            cpp_path = write_cpp_debugger(py_path.parent)
            print(f"Generated C++ debugger: {cpp_path}")
            exe_path = compile_cpp_debugger(cpp_path)
            print(f"Compiled debugger: {exe_path}")
            run_cpp_debugger(exe_path, py_path)
            debugged_path = build_debugged_output_path(py_path)
            print(f"Generated debugged file: {debugged_path}")

        return 0

    except subprocess.CalledProcessError as e:
        print(f"Process error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Conversion error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
