
from ..addon_base import AddonBase

class OfficialExtensionsAddon(AddonBase):
    name = "official_extensions"
    prefixes = [
        "pen_", "music_", "videoSensing_", "text2speech_", "translate_",
        "makeymakey_", "microbit_", "gdxfor_", "boost_", "wedo2_", "ev3_"
    ]

    def convert_expr(self, c, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")
        if op == "translate_getTranslate":
            return f"translate_get({c.get_input_expr(block, 'WORDS', blocks, variables_by_id, lists_by_id)}, {c.get_input_expr(block, 'LANGUAGE', blocks, variables_by_id, lists_by_id)})"
        if op == "music_getTempo":
            return "music_get_tempo()"
        if op == "videoSensing_videoOn":
            return f"video_on({c.get_input_expr(block, 'ATTRIBUTE', blocks, variables_by_id, lists_by_id)}, {c.get_input_expr(block, 'SUBJECT', blocks, variables_by_id, lists_by_id)})"
        return None

    def convert_block(self, c, block, blocks, variables_by_id, lists_by_id):
        op = block.get("opcode", "")
        gi = c.get_input_expr
        if op == "pen_clear": return "pen_clear()"
        if op == "pen_stamp": return "pen_stamp()"
        if op == "pen_penDown": return "pen_down()"
        if op == "pen_penUp": return "pen_up()"
        if op == "pen_setPenColorToColor": return f"pen_set_color({gi(block, 'COLOR', blocks, variables_by_id, lists_by_id)})"
        if op == "pen_changePenColorParamBy": return f"pen_change_param({gi(block, 'COLOR_PARAM', blocks, variables_by_id, lists_by_id)}, {gi(block, 'VALUE', blocks, variables_by_id, lists_by_id)})"
        if op == "pen_setPenColorParamTo": return f"pen_set_param({gi(block, 'COLOR_PARAM', blocks, variables_by_id, lists_by_id)}, {gi(block, 'VALUE', blocks, variables_by_id, lists_by_id)})"
        if op == "pen_changePenSizeBy": return f"pen_change_size({gi(block, 'SIZE', blocks, variables_by_id, lists_by_id)})"
        if op == "pen_setPenSizeTo": return f"pen_set_size({gi(block, 'SIZE', blocks, variables_by_id, lists_by_id)})"

        if op == "music_playDrumForBeats": return f"music_play_drum({gi(block, 'DRUM', blocks, variables_by_id, lists_by_id)}, {gi(block, 'BEATS', blocks, variables_by_id, lists_by_id)})"
        if op == "music_restForBeats": return f"music_rest({gi(block, 'BEATS', blocks, variables_by_id, lists_by_id)})"
        if op == "music_playNoteForBeats": return f"music_play_note({gi(block, 'NOTE', blocks, variables_by_id, lists_by_id)}, {gi(block, 'BEATS', blocks, variables_by_id, lists_by_id)})"
        if op == "music_setInstrument": return f"music_set_instrument({gi(block, 'INSTRUMENT', blocks, variables_by_id, lists_by_id)})"
        if op == "music_setTempo": return f"music_set_tempo({gi(block, 'TEMPO', blocks, variables_by_id, lists_by_id)})"
        if op == "music_changeTempo": return f"music_change_tempo({gi(block, 'TEMPO', blocks, variables_by_id, lists_by_id)})"

        if op == "videoSensing_whenMotionGreaterThan": return f"# TODO hat block: {op}"
        if op == "videoSensing_setVideoTransparency": return f"video_set_transparency({gi(block, 'TRANSPARENCY', blocks, variables_by_id, lists_by_id)})"
        if op == "videoSensing_setVideoState": return f"video_set_state({gi(block, 'VIDEO_STATE', blocks, variables_by_id, lists_by_id)})"

        if op == "text2speech_speakAndWait": return f"text2speech_speak({gi(block, 'WORDS', blocks, variables_by_id, lists_by_id)})"
        if op == "text2speech_setVoice": return f"text2speech_set_voice({gi(block, 'VOICE', blocks, variables_by_id, lists_by_id)})"
        if op == "text2speech_setLanguage": return f"text2speech_set_language({gi(block, 'LANGUAGE', blocks, variables_by_id, lists_by_id)})"

        if op == "translate_getViewerLanguage": return "translate_viewer_language()"

        # hardware extensions: keep syntax-safe stubs
        if any(op.startswith(p) for p in ["makeymakey_","microbit_","gdxfor_","boost_","wedo2_","ev3_"]):
            args = []
            for name in sorted((block.get("inputs") or {}).keys()):
                args.append(gi(block, name, blocks, variables_by_id, lists_by_id))
            return f"{op}({', '.join(args)})"
        return None
