
class AddonBase:
    name = "base"
    prefixes = []
    def handles(self, opcode: str) -> bool:
        return any(opcode.startswith(p) for p in self.prefixes)
    def convert_block(self, converter, block, blocks, variables_by_id, lists_by_id):
        return None
    def convert_expr(self, converter, block, blocks, variables_by_id, lists_by_id):
        return None
