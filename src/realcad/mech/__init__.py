"""Machine element standards tables and assembly builders (CAD practical exam presets)."""

PRESETS = {
    "power_train": ("동력전달장치", "power_train", "build_power_train"),
    "eccentric_slider": ("편심왕복장치", "eccentric", "build_eccentric"),
    "gear_pump": ("기어펌프", "gear_pump", "build_gear_pump"),
    "drill_jig": ("드릴지그", "drill_jig", "build_drill_jig"),
    "vise": ("탁상 바이스", "vise", "build_vise"),
    "cam_clamp": ("캠 클램프", "cam_clamp", "build_cam_clamp"),
}


def build_assembly(a):
    """Assembly contract to the builder for its preset."""
    import importlib
    name, mod, fn = PRESETS.get(getattr(a, "preset", "power_train"), PRESETS["power_train"])
    m = importlib.import_module(f"realcad.mech.{mod}")
    return getattr(m, fn)(a)
