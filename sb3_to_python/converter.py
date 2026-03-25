from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .runtime import RUNTIME_HEADER


@dataclass
class LoadedProject:
    project_json: dict[str, Any]
    source_path: Path


class ScratchToPythonConverter:
    def __init__(self, project_data: dict[str, Any]):
        self.project_data = project_data
        self.target: dict[str, Any] | None = None
        self.blocks: dict[str, dict[str, Any]] = {}
        self.variables: dict[str, list[Any]] = {}
        self.lists: dict[str, list[Any]] = {}
        self.used_names: set[str] = set()
        self.target_name_map: dict[int, str] = {}

    @staticmethod
    def load_sb3(path: str | Path) -> LoadedProject:
        source = Path(path)
        with zipfile.ZipFile(source, "r") as zf:
            with zf.open("project.json") as fp:
                project_json = json.load(fp)
        return LoadedProject(project_json=project_json, source_path=source)

    def init_target(self, target_index: int = 0) -> None:
        target = self.project_data["targets"][target_index]
        self.target = target
        self.blocks = target.get("blocks", {})
        self.variables = target.get("variables", {})
        self.lists = target.get("lists", {})

    def sanitize_name(self, name: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", str(name).strip())
        if not cleaned:
            cleaned = "var_scratch"
        if cleaned[0].isdigit():
            cleaned = f"_{cleaned}"
        cleaned = re.sub(r"_+", "_", cleaned).strip("_") or "var_scratch"
        base = cleaned
        i = 2
        while cleaned in self.used_names:
            cleaned = f"{base}_{i}"
            i += 1
        self.used_names.add(cleaned)
        return cleaned

    def get_block(self, block_id: str | None) -> dict[str, Any] | None:
        if not block_id:
            return None
        return self.blocks.get(block_id)

    def get_substack_id(self, input_entry: Any) -> str | None:
        if not isinstance(input_entry, list) or len(input_entry) < 2:
            return None
        return input_entry[1] if isinstance(input_entry[1], str) else None

    def quote_string(self, value: Any) -> str:
        return json.dumps(str(value), ensure_ascii=False)

    def convert_literal(self, value: Any) -> str:
        if isinstance(value, bool):
            return "True" if value else "False"
        if value is None:
            return "None"
        if isinstance(value, (int, float)):
            return repr(value)
        if isinstance(value, str):
            try:
                n = float(value)
                if value.strip() != "":
                    return str(int(n)) if n.is_integer() else repr(n)
            except Exception:
                pass
            return self.quote_string(value)
        return self.quote_string(value)

    def variable_name_from_id(self, variable_id: str) -> str:
        if variable_id in self.variables:
            raw_name = self.variables[variable_id][0]
            if len(self.variables[variable_id]) < 3:
                self.variables[variable_id].append(self.sanitize_name(raw_name))
            return self.variables[variable_id][2]
        return self.sanitize_name(variable_id)

    def list_name_from_id(self, list_id: str) -> str:
        if list_id in self.lists:
            raw_name = self.lists[list_id][0]
            if len(self.lists[list_id]) < 3:
                self.lists[list_id].append(self.sanitize_name(raw_name))
            return self.lists[list_id][2]
        return self.sanitize_name(list_id)

    def get_variable_name(self, variable_field: Any) -> str:
        if not variable_field or not isinstance(variable_field, list):
            return "unknown_variable"
        if len(variable_field) > 1 and isinstance(variable_field[1], str):
            return self.variable_name_from_id(variable_field[1])
        return self.sanitize_name(str(variable_field[0]))

    def get_list_name(self, list_field: Any) -> str:
        if not list_field or not isinstance(list_field, list):
            return "unknown_list"
        if len(list_field) > 1 and isinstance(list_field[1], str):
            return self.list_name_from_id(list_field[1])
        return self.sanitize_name(str(list_field[0]))

    def convert_input(self, input_entry: Any) -> str:
        if not input_entry:
            return "None"

        if isinstance(input_entry, list):
            if len(input_entry) >= 2 and isinstance(input_entry[1], str) and input_entry[1] in self.blocks:
                return self.convert_expression_block(input_entry[1])
            if len(input_entry) >= 2 and isinstance(input_entry[1], list) and len(input_entry[1]) >= 2:
                return self.convert_literal(input_entry[1][1])
            if len(input_entry) >= 2 and isinstance(input_entry[1], (str, int, float, bool)):
                return self.convert_literal(input_entry[1])

        return self.convert_literal(input_entry)

    def convert_expression_block(self, block_id: str) -> str:
        block = self.get_block(block_id)
        if not block:
            return "None"
        inputs = block.get("inputs", {})
        fields = block.get("fields", {})
        opcode = block.get("opcode", "")

        binary_ops = {
            "operator_add": "+",
            "operator_subtract": "-",
            "operator_multiply": "*",
            "operator_divide": "/",
            "operator_equals": "==",
            "operator_lt": "<",
            "operator_gt": ">",
            "operator_and": "and",
            "operator_or": "or",
            "operator_mod": "%",
        }
        if opcode in binary_ops:
            left_key = "NUM1" if "NUM1" in inputs else "OPERAND1"
            right_key = "NUM2" if "NUM2" in inputs else "OPERAND2"
            return f"({self.convert_input(inputs.get(left_key))} {binary_ops[opcode]} {self.convert_input(inputs.get(right_key))})"

        if opcode == "operator_not":
            return f"(not {self.convert_input(inputs.get('OPERAND'))})"
        if opcode == "operator_join":
            return f"(str({self.convert_input(inputs.get('STRING1'))}) + str({self.convert_input(inputs.get('STRING2'))}))"
        if opcode == "operator_length":
            return f"(len(str({self.convert_input(inputs.get('STRING'))})))"
        if opcode == "operator_contains":
            return f"(str({self.convert_input(inputs.get('STRING2'))}) in str({self.convert_input(inputs.get('STRING1'))}))"
        if opcode == "operator_letter_of":
            return f"(str({self.convert_input(inputs.get('STRING'))})[max(0, int({self.convert_input(inputs.get('LETTER'))}) - 1)])"
        if opcode == "operator_round":
            return f"(round({self.convert_input(inputs.get('NUM'))}))"
        if opcode == "operator_mathop":
            op = str(fields.get("OPERATOR", ["", ""])[0]).lower()
            num = self.convert_input(inputs.get("NUM"))
            mapping = {
                "abs": f"abs({num})",
                "floor": f"math.floor({num})",
                "ceiling": f"math.ceil({num})",
                "sqrt": f"math.sqrt({num})",
                "sin": f"math.sin(math.radians({num}))",
                "cos": f"math.cos(math.radians({num}))",
                "tan": f"math.tan(math.radians({num}))",
                "asin": f"math.degrees(math.asin({num}))",
                "acos": f"math.degrees(math.acos({num}))",
                "atan": f"math.degrees(math.atan({num}))",
                "ln": f"math.log({num})",
                "log": f"math.log10({num})",
                "e ^": f"math.exp({num})",
                "10 ^": f"(10 ** ({num}))",
            }
            return mapping.get(op, f"({num})  # TODO math op {op}")
        if opcode == "data_variable":
            return self.get_variable_name(fields.get("VARIABLE"))
        if opcode == "data_itemoflist":
            lst = self.get_list_name(fields.get("LIST"))
            idx = self.convert_input(inputs.get("INDEX"))
            return f"{lst}[max(0, int({idx}) - 1)]"
        if opcode == "data_lengthoflist":
            return f"len({self.get_list_name(fields.get('LIST'))})"
        if opcode == "data_listcontainsitem":
            lst = self.get_list_name(fields.get("LIST"))
            item = self.convert_input(inputs.get("ITEM"))
            return f"({item} in {lst})"
        if opcode == "sensing_answer":
            return "answer"
        if opcode == "sensing_timer":
            return "timer()"
        if opcode == "looks_costumenumbername":
            return "current_costume"
        if opcode == "looks_backdropnumbername":
            return "current_backdrop"
        if opcode == "motion_xposition":
            return "sprite_x"
        if opcode == "motion_yposition":
            return "sprite_y"
        if opcode == "motion_direction":
            return "sprite_direction"
        if opcode == "argument_reporter_string_number":
            return self.sanitize_name(str(fields.get("VALUE", ["arg", None])[0]))
        if opcode == "argument_reporter_boolean":
            return self.sanitize_name(str(fields.get("VALUE", ["arg", None])[0]))
        if opcode.endswith("get"):
            vals = list(inputs.values())
            a = self.convert_input(vals[0]) if len(vals) > 0 else "None"
            return f"localstorage.get({a})"

        return f"None  # TODO expr {opcode}"

    def block_to_comment(self, opcode: str, fields: dict[str, Any]) -> str:
        parts = [opcode]
        for key, value in fields.items():
            if isinstance(value, list) and value:
                parts.append(f"{key}={value[0]}")
        return " ".join(parts)

    def convert_block(self, block_id: str, indent: int = 0) -> str:
        block = self.get_block(block_id)
        if not block:
            return ""
        pad = "    " * indent
        opcode = block.get("opcode", "")
        inputs = block.get("inputs", {})
        fields = block.get("fields", {})

        if opcode == "event_whenflagclicked":
            return f"{pad}# when green flag clicked"
        if opcode == "event_whenbroadcastreceived":
            name = fields.get("BROADCAST_OPTION", ["message", None])[0]
            return f"{pad}# when I receive {name}"

        if opcode == "data_hidevariable":
            return f"{pad}# hide variable {self.get_variable_name(fields.get('VARIABLE'))}"
        if opcode == "data_showvariable":
            return f"{pad}# show variable {self.get_variable_name(fields.get('VARIABLE'))}"
        if opcode == "data_setvariableto":
            var_name = self.get_variable_name(fields.get("VARIABLE"))
            value = self.convert_input(inputs.get("VALUE"))
            return f"{pad}global {var_name}\n{pad}{var_name} = {value}"
        if opcode == "data_changevariableby":
            var_name = self.get_variable_name(fields.get("VARIABLE"))
            value = self.convert_input(inputs.get("VALUE"))
            return f"{pad}global {var_name}\n{pad}{var_name} += {value}"
        if opcode == "data_addtolist":
            lst = self.get_list_name(fields.get("LIST"))
            item = self.convert_input(inputs.get("ITEM"))
            return f"{pad}{lst}.append({item})"
        if opcode == "data_deleteoflist":
            lst = self.get_list_name(fields.get("LIST"))
            idx = self.convert_input(inputs.get("INDEX"))
            return f"{pad}del {lst}[max(0, int({idx}) - 1)]"
        if opcode == "data_deletealloflist":
            lst = self.get_list_name(fields.get("LIST"))
            return f"{pad}{lst}.clear()"
        if opcode == "data_insertatlist":
            lst = self.get_list_name(fields.get("LIST"))
            idx = self.convert_input(inputs.get("INDEX"))
            item = self.convert_input(inputs.get("ITEM"))
            return f"{pad}{lst}.insert(max(0, int({idx}) - 1), {item})"
        if opcode == "data_replaceitemoflist":
            lst = self.get_list_name(fields.get("LIST"))
            idx = self.convert_input(inputs.get("INDEX"))
            item = self.convert_input(inputs.get("ITEM"))
            return f"{pad}{lst}[max(0, int({idx}) - 1)] = {item}"
        if opcode == "data_showlist":
            return f"{pad}# show list {self.get_list_name(fields.get('LIST'))}"
        if opcode == "data_hidelist":
            return f"{pad}# hide list {self.get_list_name(fields.get('LIST'))}"

        if opcode == "looks_say":
            return f"{pad}print({self.convert_input(inputs.get('MESSAGE'))})"
        if opcode == "looks_sayforsecs":
            return (
                f"{pad}print({self.convert_input(inputs.get('MESSAGE'))})\n"
                f"{pad}time.sleep({self.convert_input(inputs.get('SECS'))})"
            )
        if opcode == "looks_think":
            return f"{pad}print('think:', {self.convert_input(inputs.get('MESSAGE'))})"
        if opcode == "looks_switchcostumeto":
            return f"{pad}set_costume({self.convert_input(inputs.get('COSTUME'))})"
        if opcode == "looks_switchbackdropto":
            return f"{pad}set_backdrop({self.convert_input(inputs.get('BACKDROP'))})"

        if opcode == "sensing_askandwait":
            return f"{pad}global answer\n{pad}answer = ask({self.convert_input(inputs.get('QUESTION'))})"
        if opcode == "control_wait":
            return f"{pad}time.sleep({self.convert_input(inputs.get('DURATION'))})"
        if opcode == "control_stop":
            opt = fields.get("STOP_OPTION", ["all", None])[0]
            return f"{pad}return  # stop {opt}"
        if opcode == "control_forever":
            sub_id = self.get_substack_id(inputs.get("SUBSTACK"))
            body = self.convert_stack(sub_id, indent + 1) if sub_id else f"{'    ' * (indent + 1)}pass"
            return f"{pad}while True:\n{body}"
        if opcode == "control_repeat":
            times = self.convert_input(inputs.get("TIMES"))
            sub_id = self.get_substack_id(inputs.get("SUBSTACK"))
            body = self.convert_stack(sub_id, indent + 1) if sub_id else f"{'    ' * (indent + 1)}pass"
            return f"{pad}for _ in range(int({times})):\n{body}"
        if opcode == "control_repeat_until":
            cond = self.convert_input(inputs.get("CONDITION"))
            sub_id = self.get_substack_id(inputs.get("SUBSTACK"))
            body = self.convert_stack(sub_id, indent + 1) if sub_id else f"{'    ' * (indent + 1)}pass"
            return f"{pad}while not ({cond}):\n{body}"
        if opcode == "control_wait_until":
            cond = self.convert_input(inputs.get("CONDITION"))
            return f"{pad}while not ({cond}):\n{pad}    time.sleep(0.01)"
        if opcode == "control_if":
            cond = self.convert_input(inputs.get("CONDITION"))
            sub_id = self.get_substack_id(inputs.get("SUBSTACK"))
            body = self.convert_stack(sub_id, indent + 1) if sub_id else f"{'    ' * (indent + 1)}pass"
            return f"{pad}if {cond}:\n{body}"
        if opcode == "control_if_else":
            cond = self.convert_input(inputs.get("CONDITION"))
            then_id = self.get_substack_id(inputs.get("SUBSTACK"))
            else_id = self.get_substack_id(inputs.get("SUBSTACK2"))
            then_body = self.convert_stack(then_id, indent + 1) if then_id else f"{'    ' * (indent + 1)}pass"
            else_body = self.convert_stack(else_id, indent + 1) if else_id else f"{'    ' * (indent + 1)}pass"
            return f"{pad}if {cond}:\n{then_body}\n{pad}else:\n{else_body}"

        if opcode.startswith("motion_"):
            mapping = {
                "motion_movesteps": f"move_steps({self.convert_input(inputs.get('STEPS'))})",
                "motion_turnright": f"turn_right({self.convert_input(inputs.get('DEGREES'))})",
                "motion_turnleft": f"turn_left({self.convert_input(inputs.get('DEGREES'))})",
                "motion_gotoxy": f"go_to_xy({self.convert_input(inputs.get('X'))}, {self.convert_input(inputs.get('Y'))})",
                "motion_glidesecstoxy": f"glide_to_xy({self.convert_input(inputs.get('SECS'))}, {self.convert_input(inputs.get('X'))}, {self.convert_input(inputs.get('Y'))})",
                "motion_pointindirection": f"point_in_direction({self.convert_input(inputs.get('DIRECTION'))})",
                "motion_changexby": f"change_x_by({self.convert_input(inputs.get('DX'))})",
                "motion_setx": f"set_x({self.convert_input(inputs.get('X'))})",
                "motion_changeyby": f"change_y_by({self.convert_input(inputs.get('DY'))})",
                "motion_sety": f"set_y({self.convert_input(inputs.get('Y'))})",
            }
            if opcode in mapping:
                return f"{pad}{mapping[opcode]}"

        if opcode.startswith("sound_"):
            return f"{pad}# TODO sound block: {opcode}"
        if opcode.startswith("pen_"):
            return f"{pad}# TODO pen block: {opcode}"
        if opcode.startswith("music_"):
            return f"{pad}# TODO music block: {opcode}"
        if opcode == "event_broadcast":
            return f"{pad}broadcast({self.convert_input(inputs.get('BROADCAST_INPUT'))})"
        if opcode == "event_broadcastandwait":
            return f"{pad}broadcast_and_wait({self.convert_input(inputs.get('BROADCAST_INPUT'))})"
        if opcode.startswith("procedures_call"):
            proc = fields.get("proccode", ["custom_block", None])[0] if isinstance(fields.get("proccode"), list) else "custom_block"
            return f"{pad}# TODO custom block call {proc}"

        if opcode.endswith("setProjectId"):
            return f"{pad}localstorage.setProjectId({self.convert_input(next(iter(inputs.values()), None))})"
        if opcode.endswith("set"):
            vals = list(inputs.values())
            a = self.convert_input(vals[0]) if len(vals) > 0 else "None"
            b = self.convert_input(vals[1]) if len(vals) > 1 else "None"
            return f"{pad}localstorage.set({a}, {b})"
        if opcode.endswith("get"):
            vals = list(inputs.values())
            a = self.convert_input(vals[0]) if len(vals) > 0 else "None"
            return f"{pad}localstorage.get({a})"

        return f"{pad}# TODO block {self.block_to_comment(opcode, fields)}"

    def convert_stack(self, start_block_id: str | None, indent: int = 0) -> str:
        current_id = start_block_id
        out: list[str] = []
        while current_id:
            block = self.get_block(current_id)
            if not block:
                break
            converted = self.convert_block(current_id, indent)
            if converted:
                out.append(converted)
            current_id = block.get("next")
        return "\n".join(out)

    def find_top_level_scripts(self) -> list[str]:
        return [block_id for block_id, block in self.blocks.items() if block.get("topLevel")]

    def declare_globals(self) -> str:
        lines: list[str] = []
        for var_id, meta in self.variables.items():
            name = self.variable_name_from_id(var_id)
            value = meta[1] if len(meta) > 1 else 0
            lines.append(f"{name} = {self.convert_literal(value)}")
        for list_id, meta in self.lists.items():
            name = self.list_name_from_id(list_id)
            value = meta[1] if len(meta) > 1 else []
            lines.append(f"{name} = {repr(value)}")
        return "\n".join(lines)

    def function_name_for_top(self, top: dict[str, Any], index: int) -> str:
        opcode = top.get("opcode")
        if opcode == "event_whenflagclicked":
            return f"when_green_flag_{index}"
        if opcode == "event_whenbroadcastreceived":
            name = top.get("fields", {}).get("BROADCAST_OPTION", ["message", None])[0]
            return self.sanitize_name(f"when_receive_{name}_{index}")
        return f"script_{index}"

    def convert_current_target(self, target_index: int = 0) -> str:
        self.init_target(target_index)
        target_label = self.target.get("name") if self.target else f"target_{target_index}"
        tops = self.find_top_level_scripts()
        scripts: list[str] = [f"# Target: {target_label}"]

        for index, top_id in enumerate(tops, start=1):
            top = self.get_block(top_id)
            if not top:
                continue
            function_name = self.function_name_for_top(top, index)
            body = self.convert_stack(top.get("next"), 1) if top.get("next") else "    pass"
            scripts.append(f"def {function_name}():\n{body}")

        launcher_lines = ["if __name__ == '__main__':"]
        if tops:
            for index, top_id in enumerate(tops, start=1):
                top = self.get_block(top_id)
                if not top:
                    continue
                fname = self.function_name_for_top(top, index)
                launcher_lines.append(f"    threading.Thread(target={fname}, daemon=True).start()")
            launcher_lines.append("    while True:")
            launcher_lines.append("        time.sleep(1)")
        else:
            launcher_lines.append("    pass")

        parts = [RUNTIME_HEADER, self.declare_globals(), "", "\n\n".join(scripts), "", "\n".join(launcher_lines)]
        return "\n".join(part for part in parts if part is not None)

    def convert_project(self) -> str:
        targets = self.project_data.get("targets", [])
        outputs: list[str] = [RUNTIME_HEADER]
        main_launchers: list[str] = []

        for target_index, target in enumerate(targets):
            self.init_target(target_index)
            target_name = self.sanitize_name(target.get("name") or f"target_{target_index}")
            outputs.append(f"# ===== Target: {target.get('name', target_name)} =====")
            globals_block = self.declare_globals()
            if globals_block:
                outputs.append(globals_block)
                outputs.append("")

            tops = self.find_top_level_scripts()
            function_names: list[str] = []
            for index, top_id in enumerate(tops, start=1):
                top = self.get_block(top_id)
                if not top:
                    continue
                local_name = self.function_name_for_top(top, index)
                function_name = self.sanitize_name(f"{target_name}_{local_name}")
                function_names.append(function_name)
                body = self.convert_stack(top.get("next"), 1) if top.get("next") else "    pass"
                outputs.append(f"def {function_name}():\n{body}\n")
            if function_names:
                main_launchers.extend(function_names)

        outputs.append("if __name__ == '__main__':")
        if main_launchers:
            for fname in main_launchers:
                outputs.append(f"    threading.Thread(target={fname}, daemon=True).start()")
            outputs.append("    while True:")
            outputs.append("        time.sleep(1)")
        else:
            outputs.append("    pass")
        return "\n".join(outputs)
