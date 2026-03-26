
import argparse, json, os, re, sys, zipfile
from .addons import load_addons

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

class Converter:
    def __init__(self, project_data, single_target=False, target_index=0):
        self.project_data = project_data
        self.single_target = single_target
        self.target_index = target_index
        self.unsupported_blocks = set()
        self.unsupported_exprs = set()
        self.addons = load_addons()

    def extract_targets(self):
        targets = self.project_data.get("targets", [])
        if self.single_target:
            return [targets[self.target_index]]
        return targets

    def collect_variables(self, target):
        out = {}
        for var_id, var_data in target.get("variables", {}).items():
            out[var_id] = sanitize_name(var_data[0] if isinstance(var_data, list) and var_data else var_id)
        return out

    def collect_lists(self, target):
        out = {}
        for list_id, list_data in target.get("lists", {}).items():
            out[list_id] = sanitize_name(list_data[0] if isinstance(list_data, list) and list_data else list_id)
        return out

    def get_variable_name(self, field, variables_by_id):
        if not field or not isinstance(field, list):
            return "scratch_var"
        if len(field) >= 2 and field[1] in variables_by_id:
            return variables_by_id[field[1]]
        return sanitize_name(field[0])

    def get_list_name(self, field, lists_by_id):
        if not field or not isinstance(field, list):
            return "scratch_list"
        if len(field) >= 2 and field[1] in lists_by_id:
            return lists_by_id[field[1]]
        return sanitize_name(field[0])

    def get_input_expr(self, block, input_name, blocks, variables_by_id, lists_by_id):
        inp = (block.get("inputs") or {}).get(input_name)
        if not inp or not isinstance(inp, list) or len(inp) < 2:
            return "None"
        raw = inp[1]
        if isinstance(raw, str) and raw in blocks:
            return self.convert_expr(blocks[raw], blocks, variables_by_id, lists_by_id)
        if isinstance(raw, list) and len(raw) >= 2:
            return py_literal(raw[1])
        return py_literal(raw)

    def get_substack_id(self, block, input_name):
        inp = (block.get("inputs") or {}).get(input_name)
        if not inp or len(inp) < 2:
            return None
        return inp[1] if isinstance(inp[1], str) else None

    def convert_expr(self, block, blocks, variables_by_id, lists_by_id):
        if not block:
            return "None"
        op = block.get("opcode","")
        # addons first
        for addon in self.addons:
            value = addon.convert_expr(self, block, blocks, variables_by_id, lists_by_id)
            if value is not None:
                return value

        gi = self.get_input_expr
        if op == "operator_add": return f"({gi(block,'NUM1',blocks,variables_by_id,lists_by_id)} + {gi(block,'NUM2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_subtract": return f"({gi(block,'NUM1',blocks,variables_by_id,lists_by_id)} - {gi(block,'NUM2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_multiply": return f"({gi(block,'NUM1',blocks,variables_by_id,lists_by_id)} * {gi(block,'NUM2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_divide": return f"({gi(block,'NUM1',blocks,variables_by_id,lists_by_id)} / {gi(block,'NUM2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_equals": return f"({gi(block,'OPERAND1',blocks,variables_by_id,lists_by_id)} == {gi(block,'OPERAND2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_gt": return f"({gi(block,'OPERAND1',blocks,variables_by_id,lists_by_id)} > {gi(block,'OPERAND2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_lt": return f"({gi(block,'OPERAND1',blocks,variables_by_id,lists_by_id)} < {gi(block,'OPERAND2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_and": return f"({gi(block,'OPERAND1',blocks,variables_by_id,lists_by_id)} and {gi(block,'OPERAND2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_or": return f"({gi(block,'OPERAND1',blocks,variables_by_id,lists_by_id)} or {gi(block,'OPERAND2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_not": return f"(not {gi(block,'OPERAND',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_join": return f"(str({gi(block,'STRING1',blocks,variables_by_id,lists_by_id)}) + str({gi(block,'STRING2',blocks,variables_by_id,lists_by_id)}))"
        if op == "operator_letter_of": return f"(str({gi(block,'STRING',blocks,variables_by_id,lists_by_id)})[max(0,int({gi(block,'LETTER',blocks,variables_by_id,lists_by_id)})-1)])"
        if op == "operator_length": return f"(len(str({gi(block,'STRING',blocks,variables_by_id,lists_by_id)})))"
        if op == "operator_contains": return f"(str({gi(block,'STRING2',blocks,variables_by_id,lists_by_id)}) in str({gi(block,'STRING1',blocks,variables_by_id,lists_by_id)}))"
        if op == "operator_mod": return f"({gi(block,'NUM1',blocks,variables_by_id,lists_by_id)} % {gi(block,'NUM2',blocks,variables_by_id,lists_by_id)})"
        if op == "operator_round": return f"(round({gi(block,'NUM',blocks,variables_by_id,lists_by_id)}))"
        if op == "operator_mathop": return f"math_{gi(block,'OPERATOR',blocks,variables_by_id,lists_by_id)}({gi(block,'NUM',blocks,variables_by_id,lists_by_id)})"

        if op == "data_variable":
            return self.get_variable_name((block.get("fields") or {}).get("VARIABLE"), variables_by_id)
        if op == "data_itemoflist":
            list_name = self.get_list_name((block.get("fields") or {}).get("LIST"), lists_by_id)
            return f"list_item({list_name}, {gi(block,'INDEX',blocks,variables_by_id,lists_by_id)})"
        if op == "data_itemnumoflist":
            list_name = self.get_list_name((block.get("fields") or {}).get("LIST"), lists_by_id)
            return f"(({list_name}.index({gi(block,'ITEM',blocks,variables_by_id,lists_by_id)}) + 1) if {gi(block,'ITEM',blocks,variables_by_id,lists_by_id)} in {list_name} else 0)"
        if op == "data_lengthoflist":
            list_name = self.get_list_name((block.get("fields") or {}).get("LIST"), lists_by_id)
            return f"list_length({list_name})"
        if op == "data_listcontainsitem":
            list_name = self.get_list_name((block.get("fields") or {}).get("LIST"), lists_by_id)
            return f"list_contains({list_name}, {gi(block,'ITEM',blocks,variables_by_id,lists_by_id)})"

        # sensing reporters
        reporter_map = {
            "sensing_answer":"answer", "sensing_loudness":"0", "sensing_timer":"0",
            "sensing_dayssince2000":"0", "sensing_current":"0", "sensing_username":"username",
            "motion_xposition":"0", "motion_yposition":"0", "motion_direction":"90",
            "looks_size":"100", "sound_volume":"100", "music_getTempo":"120"
        }
        if op in reporter_map: return reporter_map[op]
        self.unsupported_exprs.add(op)
        return "None"

    def convert_block(self, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode","")
        for addon in self.addons:
            value = addon.convert_block(self, block, blocks, variables_by_id, lists_by_id)
            if value is not None:
                return value
        gi = self.get_input_expr

        # events
        if op.startswith("event_"):
            return f"# TODO event block: {op}" if op != "event_whenflagclicked" else None

        # motion
        if op == "motion_movesteps": return f"move_steps({gi(block,'STEPS',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_turnright": return f"turn_right({gi(block,'DEGREES',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_turnleft": return f"turn_left({gi(block,'DEGREES',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_goto": return f"go_to_xy({gi(block,'TO',blocks,variables_by_id,lists_by_id)}, None)"
        if op == "motion_gotoxy": return f"go_to_xy({gi(block,'X',blocks,variables_by_id,lists_by_id)}, {gi(block,'Y',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_glideto": return f"glide_to_xy({gi(block,'SECS',blocks,variables_by_id,lists_by_id)}, {gi(block,'TO',blocks,variables_by_id,lists_by_id)}, None)"
        if op == "motion_glidesecstoxy": return f"glide_to_xy({gi(block,'SECS',blocks,variables_by_id,lists_by_id)}, {gi(block,'X',blocks,variables_by_id,lists_by_id)}, {gi(block,'Y',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_pointindirection": return f"point_in_direction({gi(block,'DIRECTION',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_pointtowards": return f"point_towards({gi(block,'TOWARDS',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_changexby": return f"change_x_by({gi(block,'DX',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_setx": return f"set_x_to({gi(block,'X',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_changeyby": return f"change_y_by({gi(block,'DY',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_sety": return f"set_y_to({gi(block,'Y',blocks,variables_by_id,lists_by_id)})"
        if op == "motion_ifonedgebounce": return "if_on_edge_bounce()"
        if op == "motion_setrotationstyle": return f"set_rotation_style({py_literal((block.get('fields') or {}).get('STYLE',[''])[0])})"

        # looks
        if op == "looks_say": return f"say({gi(block,'MESSAGE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_sayforsecs": return f"say({gi(block,'MESSAGE',blocks,variables_by_id,lists_by_id)})\ntime.sleep({gi(block,'SECS',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_think": return f"think({gi(block,'MESSAGE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_thinkforsecs": return f"think({gi(block,'MESSAGE',blocks,variables_by_id,lists_by_id)})\ntime.sleep({gi(block,'SECS',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_switchcostumeto": return f"switch_costume_to({gi(block,'COSTUME',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_nextcostume": return "next_costume()"
        if op == "looks_switchbackdropto": return f"switch_backdrop_to({gi(block,'BACKDROP',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_switchbackdroptoandwait": return f"switch_backdrop_and_wait({gi(block,'BACKDROP',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_nextbackdrop": return "next_backdrop()"
        if op == "looks_changeeffectby": return f"change_effect_by({py_literal((block.get('fields') or {}).get('EFFECT',[''])[0])}, {gi(block,'CHANGE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_seteffectto": return f"set_effect_to({py_literal((block.get('fields') or {}).get('EFFECT',[''])[0])}, {gi(block,'VALUE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_cleargraphiceffects": return "clear_graphic_effects()"
        if op == "looks_changesizeby": return f"change_size_by({gi(block,'CHANGE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_setsizeto": return f"set_size_to({gi(block,'SIZE',blocks,variables_by_id,lists_by_id)})"
        if op == "looks_show": return "show()"
        if op == "looks_hide": return "hide()"
        if op == "looks_gotofrontback": return f"go_to_front_back({py_literal((block.get('fields') or {}).get('FRONT_BACK',[''])[0])})"
        if op == "looks_goforwardbackwardlayers": return f"go_forward_backward_layers({py_literal((block.get('fields') or {}).get('FORWARD_BACKWARD',[''])[0])}, {gi(block,'NUM',blocks,variables_by_id,lists_by_id)})"

        # sound
        if op == "sound_playuntildone": return f"play_sound_until_done({gi(block,'SOUND_MENU',blocks,variables_by_id,lists_by_id)})"
        if op == "sound_play": return f"start_sound({gi(block,'SOUND_MENU',blocks,variables_by_id,lists_by_id)})"
        if op == "sound_stopallsounds": return "stop_all_sounds()"
        if op == "sound_changeeffectby": return f"change_sound_effect_by({py_literal((block.get('fields') or {}).get('EFFECT',[''])[0])}, {gi(block,'VALUE',blocks,variables_by_id,lists_by_id)})"
        if op == "sound_seteffectto": return f"set_sound_effect_to({py_literal((block.get('fields') or {}).get('EFFECT',[''])[0])}, {gi(block,'VALUE',blocks,variables_by_id,lists_by_id)})"
        if op == "sound_cleareffects": return "clear_sound_effects()"
        if op == "sound_changevolumeby": return f"change_volume_by({gi(block,'VOLUME',blocks,variables_by_id,lists_by_id)})"
        if op == "sound_setvolumeto": return f"set_volume_to({gi(block,'VOLUME',blocks,variables_by_id,lists_by_id)})"

        # data
        if op == "data_setvariableto":
            return f"{self.get_variable_name((block.get('fields') or {}).get('VARIABLE'), variables_by_id)} = {gi(block,'VALUE',blocks,variables_by_id,lists_by_id)}"
        if op == "data_changevariableby":
            return f"{self.get_variable_name((block.get('fields') or {}).get('VARIABLE'), variables_by_id)} += {gi(block,'VALUE',blocks,variables_by_id,lists_by_id)}"
        if op == "data_showvariable" or op == "data_hidevariable":
            return f"# TODO variable visibility: {op}"
        if op == "data_addtolist":
            return f"{self.get_list_name((block.get('fields') or {}).get('LIST'), lists_by_id)}.append({gi(block,'ITEM',blocks,variables_by_id,lists_by_id)})"
        if op == "data_deleteoflist":
            return f"delete_list_item({self.get_list_name((block.get('fields') or {}).get('LIST'), lists_by_id)}, {gi(block,'INDEX',blocks,variables_by_id,lists_by_id)})"
        if op == "data_deletealloflist":
            return f"{self.get_list_name((block.get('fields') or {}).get('LIST'), lists_by_id)}.clear()"
        if op == "data_insertatlist":
            return f"insert_list_item({self.get_list_name((block.get('fields') or {}).get('LIST'), lists_by_id)}, {gi(block,'INDEX',blocks,variables_by_id,lists_by_id)}, {gi(block,'ITEM',blocks,variables_by_id,lists_by_id)})"
        if op == "data_replaceitemoflist":
            return f"replace_list_item({self.get_list_name((block.get('fields') or {}).get('LIST'), lists_by_id)}, {gi(block,'INDEX',blocks,variables_by_id,lists_by_id)}, {gi(block,'ITEM',blocks,variables_by_id,lists_by_id)})"
        if op in {"data_showlist","data_hidelist"}:
            return f"# TODO list visibility: {op}"

        # sensing
        if op == "sensing_askandwait": return f"answer = ask({gi(block,'QUESTION',blocks,variables_by_id,lists_by_id)})"
        if op in {"sensing_setdragmode","sensing_resettimer"}:
            return f"# TODO sensing block: {op}"

        # control
        if op == "control_wait": return f"time.sleep({gi(block,'DURATION',blocks,variables_by_id,lists_by_id)})"
        if op == "control_forever":
            sub = self.get_substack_id(block, "SUBSTACK")
            return f"while True:\n{indent(self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else 'pass')}"
        if op == "control_repeat":
            sub = self.get_substack_id(block, "SUBSTACK")
            return f"for _ in range(int({gi(block,'TIMES',blocks,variables_by_id,lists_by_id)})):\n{indent(self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else 'pass')}"
        if op == "control_repeat_until":
            sub = self.get_substack_id(block, "SUBSTACK")
            cond = gi(block,'CONDITION',blocks,variables_by_id,lists_by_id)
            return f"while not ({cond}):\n{indent(self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else 'pass')}"
        if op == "control_if":
            sub = self.get_substack_id(block, "SUBSTACK")
            cond = gi(block,'CONDITION',blocks,variables_by_id,lists_by_id)
            return f"if {cond}:\n{indent(self.convert_stack(sub, blocks, variables_by_id, lists_by_id) if sub else 'pass')}"
        if op == "control_if_else":
            s1 = self.get_substack_id(block, "SUBSTACK")
            s2 = self.get_substack_id(block, "SUBSTACK2")
            cond = gi(block,'CONDITION',blocks,variables_by_id,lists_by_id)
            return f"if {cond}:\n{indent(self.convert_stack(s1, blocks, variables_by_id, lists_by_id) if s1 else 'pass')}\nelse:\n{indent(self.convert_stack(s2, blocks, variables_by_id, lists_by_id) if s2 else 'pass')}"
        if op == "control_wait_until":
            return f"while not ({gi(block,'CONDITION',blocks,variables_by_id,lists_by_id)}):\n    time.sleep(0.01)"
        if op == "control_stop": return "return"
        if op == "control_start_as_clone": return "# TODO clone hat"
        if op == "control_create_clone_of": return f"create_clone_of({gi(block,'CLONE_OPTION',blocks,variables_by_id,lists_by_id)})"
        if op == "control_delete_this_clone": return "delete_this_clone()"

        # procedures / custom blocks
        if op.startswith("procedures_") or op.startswith("argument_"):
            return f"# TODO procedure block: {op}"

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
        safe_name = sanitize_name(target_name)
        functions = []
        for block_id, block in blocks.items():
            if block.get("topLevel") and block.get("opcode") == "event_whenflagclicked":
                body = self.convert_stack(block.get("next"), blocks, variables_by_id, lists_by_id) if block.get("next") else "pass"
                functions.append((f"{safe_name}_when_green_flag_{len(functions)+1}", body))
        parts = [f"# ===== Target: {target_name} ====="]
        for var_id, var_data in target.get("variables", {}).items():
            initial = var_data[1] if isinstance(var_data, list) and len(var_data) > 1 else 0
            parts.append(f"{variables_by_id[var_id]} = {py_literal(initial)}")
        for list_id, list_data in target.get("lists", {}).items():
            initial = list_data[1] if isinstance(list_data, list) and len(list_data) > 1 and isinstance(list_data[1], list) else []
            parts.append(f"{lists_by_id[list_id]} = {repr(initial)}")
        if len(parts) > 1:
            parts.append("")
        for fn, body in functions:
            parts.append(f"def {fn}():")
            parts.append(indent(body))
            parts.append("")
        return "\n".join(parts).rstrip(), [fn for fn, _ in functions]

    def convert_project(self):
        parts = [
            "# Auto-generated from .sb3",
            "import time",
            "import threading",
            "from sb3_to_python.runtime_helpers import *",
            "",
            "answer = ''",
            "username = 'user'",
            "",
            "def custom_call(opcode, args):",
            "    print(f'CUSTOM BLOCK {opcode}: {args}')",
            "",
            "def custom_expr(opcode, args):",
            "    print(f'CUSTOM EXPR {opcode}: {args}')",
            "    return None",
            "",
        ]
        all_fns = []
        for i, target in enumerate(self.extract_targets()):
            code, fns = self.convert_target(target, i)
            parts.append(code)
            parts.append("")
            all_fns.extend(fns)
        parts.append("if __name__ == '__main__':")
        if all_fns:
            parts.append("    threads = []")
            for fn in all_fns:
                parts.append(f"    t = threading.Thread(target={fn}, daemon=True)")
                parts.append("    threads.append(t)")
                parts.append("    t.start()")
            parts.append("    try:")
            parts.append("        while True:")
            parts.append("            time.sleep(0.1)")
            parts.append("    except KeyboardInterrupt:")
            parts.append("        pass")
        else:
            parts.append("    pass")
        if self.unsupported_blocks or self.unsupported_exprs:
            parts.append("")
            for op in sorted(self.unsupported_blocks):
                parts.append(f"# unsupported block: {op}")
            for op in sorted(self.unsupported_exprs):
                parts.append(f"# unsupported expr: {op}")
        return "\n".join(parts)

def load_project_json_from_sb3(path):
    with zipfile.ZipFile(path, "r") as zf:
        with zf.open("project.json") as f:
            return json.load(f)

def build_output_path(input_path, output_path=None):
    if output_path:
        return output_path
    return os.path.splitext(input_path)[0] + ".py"

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Convert .sb3 files to Python")
    p.add_argument("input", help="input .sb3 file")
    p.add_argument("-o","--output", help="output .py file")
    p.add_argument("--single-target", action="store_true")
    p.add_argument("--target-index", type=int, default=0)
    return p.parse_args(argv)

def main(argv=None):
    args = parse_args(argv)
    if not os.path.exists(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        return 1
    data = load_project_json_from_sb3(args.input)
    converter = Converter(data, single_target=args.single_target, target_index=args.target_index)
    out = converter.convert_project()
    output_path = build_output_path(args.input, args.output)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(out)
    print(f"Generated: {output_path}")
    return 0
