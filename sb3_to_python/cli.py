#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
import threading
import time
import zipfile


def py_literal(value):
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, (int, float)):
        return str(value)

    s = str(value)

    # numero scritto come stringa
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
    lines = text.splitlines()
    if not lines:
        return pad + "pass"
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
            # [name, value]
            if isinstance(var_data, list) and var_data:
                vars_by_id[var_id] = sanitize_name(var_data[0])
            else:
                vars_by_id[var_id] = sanitize_name(var_id)
        return vars_by_id

    def collect_lists(self, target):
        lists_by_id = {}
        for list_id, list_data in target.get("lists", {}).items():
            if isinstance(list_data, list) and list_data:
                lists_by_id[list_id] = sanitize_name(list_data[0])
            else:
                lists_by_id[list_id] = sanitize_name(list_id)
        return lists_by_id

    def get_variable_name_from_field(self, field_value, variables_by_id):
        if not field_value or not isinstance(field_value, list):
            return "scratch_var"

        # Scratch di solito mette [visible_name, id]
        if len(field_value) >= 2:
            visible_name = field_value[0]
            var_id = field_value[1]
            if var_id in variables_by_id:
                return variables_by_id[var_id]
            return sanitize_name(visible_name)

        return sanitize_name(field_value[0])

    def get_list_name_from_field(self, field_value, lists_by_id):
        if not field_value or not isinstance(field_value, list):
            return "scratch_list"

        if len(field_value) >= 2:
            visible_name = field_value[0]
            list_id = field_value[1]
            if list_id in lists_by_id:
                return lists_by_id[list_id]
            return sanitize_name(visible_name)

        return sanitize_name(field_value[0])

    def is_block_ref(self, value, blocks):
        return isinstance(value, str) and value in blocks

    def parse_input_literal(self, value):
        # Esempi tipici Scratch:
        # [4, "10"]
        # [10, "ciao"]
        # [12, "variableName"]
        if isinstance(value, list):
            if len(value) >= 2:
                return py_literal(value[1])
            if len(value) == 1:
                return py_literal(value[0])

        return py_literal(value)

    def get_input_expr(self, block, input_name, blocks, variables_by_id, lists_by_id):
        inputs = block.get("inputs", {})
        inp = inputs.get(input_name)
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
        if isinstance(inp[1], str):
            return inp[1]
        return None

    def convert_expr(self, block, blocks, variables_by_id, lists_by_id):
        if not block:
            return "None"

        op = block.get("opcode", "")

        # Operators
        if op == "operator_add":
            return f"({self.get_input_expr(block, 'NUM1', blocks, variables_by_id, lists_by_id)} + {self.get_input_expr(block, 'NUM2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_subtract":
            return f"({self.get_input_expr(block, 'NUM1', blocks, variables_by_id, lists_by_id)} - {self.get_input_expr(block, 'NUM2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_multiply":
            return f"({self.get_input_expr(block, 'NUM1', blocks, variables_by_id, lists_by_id)} * {self.get_input_expr(block, 'NUM2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_divide":
            return f"({self.get_input_expr(block, 'NUM1', blocks, variables_by_id, lists_by_id)} / {self.get_input_expr(block, 'NUM2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_equals":
            return f"({self.get_input_expr(block, 'OPERAND1', blocks, variables_by_id, lists_by_id)} == {self.get_input_expr(block, 'OPERAND2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_gt":
            return f"({self.get_input_expr(block, 'OPERAND1', blocks, variables_by_id, lists_by_id)} > {self.get_input_expr(block, 'OPERAND2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_lt":
            return f"({self.get_input_expr(block, 'OPERAND1', blocks, variables_by_id, lists_by_id)} < {self.get_input_expr(block, 'OPERAND2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_and":
            return f"({self.get_input_expr(block, 'OPERAND1', blocks, variables_by_id, lists_by_id)} and {self.get_input_expr(block, 'OPERAND2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_or":
            return f"({self.get_input_expr(block, 'OPERAND1', blocks, variables_by_id, lists_by_id)} or {self.get_input_expr(block, 'OPERAND2', blocks, variables_by_id, lists_by_id)})"

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

        if op == "operator_mod":
            return f"({self.get_input_expr(block, 'NUM1', blocks, variables_by_id, lists_by_id)} % {self.get_input_expr(block, 'NUM2', blocks, variables_by_id, lists_by_id)})"

        if op == "operator_round":
            return f"(round({self.get_input_expr(block, 'NUM', blocks, variables_by_id, lists_by_id)}))"

        # Data / sensing reporters
        if op == "data_variable":
            field = block.get("fields", {}).get("VARIABLE")
            return self.get_variable_name_from_field(field, variables_by_id)

        if op == "sensing_answer":
            return "answer"

        if op == "sensing_username":
            return "username"

        # Looks / costume reporter fallback
        if op in ("looks_costume", "looks_backdrops"):
            self.unsupported_exprs.add(op)
            return "None"

        self.unsupported_exprs.add(op)
        return "None"

    def convert_block(self, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")

        # Events
        if op == "event_whenflagclicked":
            return None

        # Looks
        if op == "looks_say":
            msg = self.get_input_expr(block, "MESSAGE", blocks, variables_by_id, lists_by_id)
            return f"print({msg})"

        if op == "looks_sayforsecs":
            msg = self.get_input_expr(block, "MESSAGE", blocks, variables_by_id, lists_by_id)
            secs = self.get_input_expr(block, "SECS", blocks, variables_by_id, lists_by_id)
            return f"print({msg})\ntime.sleep({secs})"

        if op == "looks_switchcostumeto":
            costume = self.get_input_expr(block, "COSTUME", blocks, variables_by_id, lists_by_id)
            return f"set_costume({costume})"

        if op == "looks_switchbackdropto":
            backdrop = self.get_input_expr(block, "BACKDROP", blocks, variables_by_id, lists_by_id)
            return f"set_backdrop({backdrop})"

        # Sensing
        if op == "sensing_askandwait":
            question = self.get_input_expr(block, "QUESTION", blocks, variables_by_id, lists_by_id)
            return f"answer = input(str({question}) + ' ')"

        # Data
        if op == "data_setvariableto":
            var_name = self.get_variable_name_from_field(block.get("fields", {}).get("VARIABLE"), variables_by_id)
            value = self.get_input_expr(block, "VALUE", blocks, variables_by_id, lists_by_id)
            return f"{var_name} = {value}"

        if op == "data_changevariableby":
            var_name = self.get_variable_name_from_field(block.get("fields", {}).get("VARIABLE"), variables_by_id)
            value = self.get_input_expr(block, "VALUE", blocks, variables_by_id, lists_by_id)
            return f"{var_name} += {value}"

        # Lists
        if op == "data_addtolist":
            list_name = self.get_list_name_from_field(block.get("fields", {}).get("LIST"), lists_by_id)
            item = self.get_input_expr(block, "ITEM", blocks, variables_by_id, lists_by_id)
            return f"{list_name}.append({item})"

        if op == "data_deleteoflist":
            list_name = self.get_list_name_from_field(block.get("fields", {}).get("LIST"), lists_by_id)
            index_expr = self.get_input_expr(block, "INDEX", blocks, variables_by_id, lists_by_id)
            return f"delete_list_item({list_name}, {index_expr})"

        if op == "data_deletealloflist":
            list_name = self.get_list_name_from_field(block.get("fields", {}).get("LIST"), lists_by_id)
            return f"{list_name}.clear()"

        if op == "data_insertatlist":
            list_name = self.get_list_name_from_field(block.get("fields", {}).get("LIST"), lists_by_id)
            item = self.get_input_expr(block, "ITEM", blocks, variables_by_id, lists_by_id)
            index_expr = self.get_input_expr(block, "INDEX", blocks, variables_by_id, lists_by_id)
            return f"insert_list_item({list_name}, {index_expr}, {item})"

        if op == "data_replaceitemoflist":
            list_name = self.get_list_name_from_field(block.get("fields", {}).get("LIST"), lists_by_id)
            index_expr = self.get_input_expr(block, "INDEX", blocks, variables_by_id, lists_by_id)
            item = self.get_input_expr(block, "ITEM", blocks, variables_by_id, lists_by_id)
            return f"replace_list_item({list_name}, {index_expr}, {item})"

        # Control
        if op == "control_wait":
            duration = self.get_input_expr(block, "DURATION", blocks, variables_by_id, lists_by_id)
            return f"time.sleep({duration})"

        if op == "control_forever":
            substack_id = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(substack_id, blocks, variables_by_id, lists_by_id) if substack_id else "pass"
            return f"while True:\n{indent(body)}"

        if op == "control_repeat":
            times_expr = self.get_input_expr(block, "TIMES", blocks, variables_by_id, lists_by_id)
            substack_id = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(substack_id, blocks, variables_by_id, lists_by_id) if substack_id else "pass"
            return f"for _ in range(int({times_expr})):\n{indent(body)}"

        if op == "control_repeat_until":
            condition_expr = self.get_input_expr(block, "CONDITION", blocks, variables_by_id, lists_by_id)
            substack_id = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(substack_id, blocks, variables_by_id, lists_by_id) if substack_id else "pass"
            return f"while not ({condition_expr}):\n{indent(body)}"

        if op == "control_if":
            condition_expr = self.get_input_expr(block, "CONDITION", blocks, variables_by_id, lists_by_id)
            substack_id = self.get_substack_id(block, "SUBSTACK")
            body = self.convert_stack(substack_id, blocks, variables_by_id, lists_by_id) if substack_id else "pass"
            return f"if {condition_expr}:\n{indent(body)}"

        if op == "control_if_else":
            condition_expr = self.get_input_expr(block, "CONDITION", blocks, variables_by_id, lists_by_id)
            substack1_id = self.get_substack_id(block, "SUBSTACK")
            substack2_id = self.get_substack_id(block, "SUBSTACK2")

            body1 = self.convert_stack(substack1_id, blocks, variables_by_id, lists_by_id) if substack1_id else "pass"
            body2 = self.convert_stack(substack2_id, blocks, variables_by_id, lists_by_id) if substack2_id else "pass"

            return f"if {condition_expr}:\n{indent(body1)}\nelse:\n{indent(body2)}"

        if op == "control_wait_until":
            condition_expr = self.get_input_expr(block, "CONDITION", blocks, variables_by_id, lists_by_id)
            return f"while not ({condition_expr}):\n    time.sleep(0.01)"

        if op == "control_stop":
            stop_option = block.get("fields", {}).get("STOP_OPTION", [""])[0]
            if stop_option == "all":
                return "raise SystemExit"
            return "return"

        # Motion (base)
        if op == "motion_movesteps":
            steps = self.get_input_expr(block, "STEPS", blocks, variables_by_id, lists_by_id)
            return f"move_steps({steps})"

        if op == "motion_turnright":
            degrees = self.get_input_expr(block, "DEGREES", blocks, variables_by_id, lists_by_id)
            return f"turn_right({degrees})"

        if op == "motion_turnleft":
            degrees = self.get_input_expr(block, "DEGREES", blocks, variables_by_id, lists_by_id)
            return f"turn_left({degrees})"

        if op == "motion_gotoxy":
            x = self.get_input_expr(block, "X", blocks, variables_by_id, lists_by_id)
            y = self.get_input_expr(block, "Y", blocks, variables_by_id, lists_by_id)
            return f"go_to_xy({x}, {y})"

        # PenguinMod localstorage
        if op == "localstorage_setProjectId":
            value = self.get_input_expr(block, "TEXT", blocks, variables_by_id, lists_by_id)
            return f"localstorage_set_project_id({value})"

        if op == "localstorage_set":
            key = self.get_input_expr(block, "KEY", blocks, variables_by_id, lists_by_id)
            value = self.get_input_expr(block, "VALUE", blocks, variables_by_id, lists_by_id)
            return f"localstorage_set({key}, {value})"

        if op == "localstorage_get":
            key = self.get_input_expr(block, "KEY", blocks, variables_by_id, lists_by_id)
            return f"localstorage_get({key})"

        self.unsupported_blocks.add(op)
        return f"# TODO block: {op}"

    def convert_stack(self, start_block_id, blocks, variables_by_id, lists_by_id):
        out = []
        current_id = start_block_id

        visited = set()
        while current_id and current_id in blocks:
            if current_id in visited:
                out.append("# TODO block cycle detected")
                break
            visited.add(current_id)

            block = blocks[current_id]
            code = self.convert_block(block, blocks, variables_by_id, lists_by_id)
            if code:
                out.append(code)
            current_id = block.get("next")

        return "\n".join(out) if out else "pass"

    def convert_target(self, target, target_index):
        blocks = target.get("blocks", {})
        variables_by_id = self.collect_variables(target)
        lists_by_id = self.collect_lists(target)

        target_name = target.get("name", f"target_{target_index}")
        safe_target_name = sanitize_name(target_name)
        scripts = []

        for block_id, block in blocks.items():
            if not block.get("topLevel"):
                continue

            if block.get("opcode") != "event_whenflagclicked":
                continue

            next_id = block.get("next")
            body = self.convert_stack(next_id, blocks, variables_by_id, lists_by_id) if next_id else "pass"

            function_name = f"{safe_target_name}_when_green_flag_{len(scripts) + 1}"
            scripts.append((function_name, body))

        var_lines = []
        for var_id, var_data in target.get("variables", {}).items():
            name = variables_by_id[var_id]
            initial = var_data[1] if isinstance(var_data, list) and len(var_data) > 1 else 0
            var_lines.append(f"{name} = {py_literal(initial)}")

        list_lines = []
        for list_id, list_data in target.get("lists", {}).items():
            name = lists_by_id[list_id]
            initial = list_data[1] if isinstance(list_data, list) and len(list_data) > 1 else []
            if not isinstance(initial, list):
                initial = []
            list_lines.append(f"{name} = {repr(initial)}")

        parts = []
        parts.append(f"# ===== Target: {target_name} =====")

        if var_lines:
            parts.append("\n".join(var_lines))

        if list_lines:
            parts.append("\n".join(list_lines))

        if var_lines or list_lines:
            parts.append("")

        for function_name, body in scripts:
            parts.append(f"def {function_name}():")
            parts.append(indent(body))
            parts.append("")

        return "\n".join(parts).rstrip(), [name for name, _ in scripts]

    def convert_project(self):
        targets = self.extract_targets()

        output_parts = [
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
            "def localstorage_get(key):",
            "    return None",
            "",
            "def delete_list_item(lst, index_1_based):",
            "    try:",
            "        i = int(index_1_based) - 1",
            "        if 0 <= i < len(lst):",
            "            del lst[i]",
            "    except Exception:",
            "        pass",
            "",
            "def insert_list_item(lst, index_1_based, value):",
            "    try:",
            "        i = max(0, int(index_1_based) - 1)",
            "        if i > len(lst):",
            "            i = len(lst)",
            "        lst.insert(i, value)",
            "    except Exception:",
            "        lst.append(value)",
            "",
            "def replace_list_item(lst, index_1_based, value):",
            "    try:",
            "        i = int(index_1_based) - 1",
            "        if 0 <= i < len(lst):",
            "            lst[i] = value",
            "    except Exception:",
            "        pass",
            "",
        ]

        all_function_names = []

        for i, target in enumerate(targets):
            target_code, function_names = self.convert_target(target, i)
            output_parts.append(target_code)
            output_parts.append("")
            all_function_names.extend(function_names)

        output_parts.append("if __name__ == '__main__':")
        if all_function_names:
            output_parts.append("    threads = []")
            for fn in all_function_names:
                output_parts.append(f"    t = threading.Thread(target={fn}, daemon=True)")
                output_parts.append("    threads.append(t)")
                output_parts.append("    t.start()")
            output_parts.append("    try:")
            output_parts.append("        while True:")
            output_parts.append("            time.sleep(0.1)")
            output_parts.append("    except KeyboardInterrupt:")
            output_parts.append("        pass")
        else:
            output_parts.append("    pass")

        if self.unsupported_blocks or self.unsupported_exprs:
            output_parts.append("")
            output_parts.append("# Unsupported elements detected during conversion:")
            for op in sorted(self.unsupported_blocks):
                output_parts.append(f"# unsupported block: {op}")
            for op in sorted(self.unsupported_exprs):
                output_parts.append(f"# unsupported expr: {op}")

        return "\n".join(output_parts)


def load_project_json_from_sb3(sb3_path):
    with zipfile.ZipFile(sb3_path, "r") as zf:
        with zf.open("project.json") as f:
            return json.load(f)


def build_output_path(input_path, output_path=None):
    if output_path:
        return output_path
    base, _ = os.path.splitext(input_path)
    return base + ".py"


def parse_args():
    parser = argparse.ArgumentParser(description="Convert .sb3 files to Python.")
    parser.add_argument("input", help="Input .sb3 file")
    parser.add_argument("-o", "--output", help="Output .py file")
    parser.add_argument("--single-target", action="store_true", help="Convert only one target")
    parser.add_argument("--target-index", type=int, default=0, help="Target index to convert when using --single-target")
    return parser.parse_args()


def main():
    args = parse_args()

    if not os.path.exists(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    try:
        project_data = load_project_json_from_sb3(args.input)
        converter = SB3ToPythonConverter(
            project_data,
            single_target=args.single_target,
            target_index=args.target_index
        )
        python_code = converter.convert_project()
        output_path = build_output_path(args.input, args.output)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(python_code)

        print(f"Generated: {output_path}")

    except Exception as e:
        print(f"Conversion error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
