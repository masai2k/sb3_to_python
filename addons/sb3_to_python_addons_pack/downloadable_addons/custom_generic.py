
from ..addon_base import AddonBase

class GenericCustomExtensionAddon(AddonBase):
    name = "generic_custom_extension"
    prefixes = []

    STANDARD_PREFIXES = {
        "motion","looks","sound","event","control","sensing","operator","data",
        "procedures","argument","pen","music","videoSensing","text2speech",
        "translate","makeymakey","microbit","gdxfor","boost","wedo2","ev3"
    }

    def _is_custom(self, opcode: str) -> bool:
        if "_" not in opcode:
            return False
        prefix = opcode.split("_", 1)[0]
        return prefix not in self.STANDARD_PREFIXES

    def convert_expr(self, c, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")
        if not self._is_custom(op):
            return None
        args = []
        for name in sorted((block.get("inputs") or {}).keys()):
            args.append(c.get_input_expr(block, name, blocks, variables_by_id, lists_by_id))
        return f"custom_expr({op!r}, [{', '.join(args)}])"

    def convert_block(self, c, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")
        if not self._is_custom(op):
            return None
        args = []
        for name in sorted((block.get("inputs") or {}).keys()):
            args.append(c.get_input_expr(block, name, blocks, variables_by_id, lists_by_id))
        return f"custom_call({op!r}, [{', '.join(args)}])"
