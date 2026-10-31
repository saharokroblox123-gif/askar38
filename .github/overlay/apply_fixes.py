#!/usr/bin/env python3
"""Apply LAST SIGNAL v0.1.1 portrait and door-interaction fixes to the CI checkout."""
from pathlib import Path
import re
import sys

root = Path(sys.argv[1])

def read(rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")

def write(rel: str, content: str) -> None:
    (root / rel).write_text(content, encoding="utf-8")

# Portrait-first project configuration.
p = "project.godot"
s = read(p)
old = """window/size/viewport_width=1280
window/size/viewport_height=720
window/size/window_width_override=1280
window/size/window_height_override=720
window/handheld/orientation=1"""
new = """window/size/viewport_width=720
window/size/viewport_height=1280
window/size/window_width_override=720
window/size/window_height_override=1280
window/handheld/orientation=1"""
if old not in s:
    raise SystemExit("Expected original viewport settings were not found.")
write(p, s.replace(old, new, 1))

p = "export_presets.cfg"
s = read(p)
s = s.replace("architectures/armeabi-v7a=false", "architectures/armeabi-v7a=true", 1)
# Android ActivityInfo.SCREEN_ORIENTATION_PORTRAIT is 2; 1 means LANDSCAPE.
if re.search(r"(?m)^screen/orientation=", s):
    s = re.sub(r"(?m)^screen/orientation=\d+\s*$", "screen/orientation=2", s)
else:
    s = s.replace("screen/immersive_mode=true", "screen/immersive_mode=true\nscreen/orientation=2", 1)
s = re.sub(r"(?m)^version/code=\d+\s*$", "version/code=3", s, count=1)
s = re.sub(r'(?m)^version/name="[^"]+"\s*$', 'version/name="0.1.2"', s, count=1)
write(p, s)

# Door panel is itself a fallback RayCast3D interaction target.
p = "scripts/main.gd"
s = read(p)
old = """\texit_door_body.name = "LockedSecurityDoor"
\texit_door_body.position = Vector3(0, 1.52, -29.72)
\tadd_child(exit_door_body)"""
new = """\texit_door_body.name = "LockedSecurityDoor"
\texit_door_body.position = Vector3(0, 1.52, -29.72)
\t# The panel is the first solid hit of the interaction ray. Keep it interactable
\t# as a fallback if the player is already inside the trigger Area3D.
\texit_door_body.add_to_group("exit_door")
\tadd_child(exit_door_body)"""
if old not in s:
    raise SystemExit("Door creation block was not found.")
s = s.replace(old, new, 1)
replacement = """func try_open_exit() -> void:
\tif door_is_open:
\t\tmobile_hud.call("show_message", "ДВЕРЬ УЖЕ ОТКРЫТА  ·  ПРОХОДИТЕ", 2.2)
\t\treturn
\tif not keycard_collected:
\t\tmobile_hud.call("show_message", "ДОСТУП ЗАПРЕЩЁН  ·  НУЖНА КАРТА", 2.8)
\t\treturn
\tif exit_door_body == null:
\t\tmobile_hud.call("show_message", "ОШИБКА ЗАМКА  ·  ПОПРОБУЙТЕ ЕЩЁ РАЗ", 2.8)
\t\treturn

\tdoor_is_open = true
\tif exit_door_mesh != null:
\t\texit_door_mesh.hide()
\t# Disable both the shape and the body's collision layer. The latter makes
\t# the passage clear on the next physics frame even if deferred shape changes
\t# are still waiting in the physics queue.
\tvar collision := exit_door_body.get_node_or_null("CollisionShape3D") as CollisionShape3D
\tif collision != null:
\t\tcollision.set_deferred("disabled", true)
\texit_door_body.set_deferred("collision_layer", 0)
\texit_door_body.set_deferred("collision_mask", 0)
\tif exit_door_trigger != null and is_instance_valid(exit_door_trigger):
\t\texit_door_trigger.set_deferred("monitoring", false)
\t\texit_door_trigger.set_deferred("monitorable", false)
\t\texit_door_trigger.queue_free()
\tmobile_hud.call("set_objective", "ЗАДАЧА 03  ·  ПРОЙДИТЕ ЧЕРЕЗ ДВЕРЬ")
\tmobile_hud.call("show_message", "ЗАМОК ОТКРЫТ  ·  ПРОХОДИТЕ", 2.8)

"""
s, count = re.subn(r"func try_open_exit\(\) -> void:\n.*?(?=func _on_victory_zone_body_entered)", replacement, s, count=1, flags=re.S)
if count != 1:
    raise SystemExit("Could not replace the door-opening function.")
s = s.replace('if body.name == "Player" and keycard_collected and not victory_shown:', 'if body.name == "Player" and door_is_open and keycard_collected and not victory_shown:', 1)
write(p, s)

# Player recognizes both the trigger and the actual door body.
p = "scripts/player.gd"
s = read(p)
s = s.replace('''\telif target is Node and target.is_in_group("exit_door_trigger"):
\t\tmobile_hud.call("set_interact_prompt", "ПРОВЕРИТЬ ДВЕРЬ · E")''', '''\telif target is Node and (target.is_in_group("exit_door") or target.is_in_group("exit_door_trigger")):
\t\tmobile_hud.call("set_interact_prompt", "ОТКРЫТЬ ДВЕРЬ · КАРТА")''', 1)
s = s.replace('''\telif target is Node and target.is_in_group("exit_door_trigger"):
\t\tgame_root.call("try_open_exit")''', '''\telif target is Node and (target.is_in_group("exit_door") or target.is_in_group("exit_door_trigger")):
\t\tgame_root.call("try_open_exit")''', 1)
write(p, s)

# Responsive portrait HUD. All positions are calculated from the current viewport.
hud = r'''extends CanvasLayer

signal move_input(value: Vector2)
signal look_input(value: Vector2)
signal run_input(value: bool)
signal crouch_toggled
signal flashlight_toggled
signal interact_requested

var objective_label: Label
var location_label: Label
var prompt_label: Label
var message_label: Label
var crosshair_label: Label
var crouch_button: Button
var flashlight_button: Button
var joystick: Control
var run_button: Button
var interact_button: Button
var message_time: float = 0.0
var overlay_root: Control

func _ready() -> void:
	add_to_group("mobile_hud")
	overlay_root = Control.new()
	overlay_root.name = "Overlay"
	overlay_root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	overlay_root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(overlay_root)

	var look_area := Control.new()
	look_area.name = "TouchLook"
	look_area.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	look_area.mouse_filter = Control.MOUSE_FILTER_STOP
	look_area.set_script(load("res://scripts/touch_look.gd"))
	overlay_root.add_child(look_area)
	look_area.connect("look_delta", _on_look_delta)

	joystick = Control.new()
	joystick.name = "MoveJoystick"
	joystick.set_script(load("res://scripts/mobile_joystick.gd"))
	overlay_root.add_child(joystick)
	joystick.connect("value_changed", _on_move_changed)

	objective_label = _make_label("ЗАДАЧА 01  ·  НАЙТИ КАРТУ ДОСТУПА", 21, Color(0.82, 0.9, 0.91))
	objective_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	overlay_root.add_child(objective_label)

	location_label = _make_label("СЕКТОР 38  /  МЕДБЛОК  ·  СВАЙП — ОБЗОР", 14, Color(0.55, 0.68, 0.71, 0.95))
	overlay_root.add_child(location_label)

	message_label = _make_label("", 19, Color(0.9, 0.94, 0.92))
	message_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	message_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	message_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	overlay_root.add_child(message_label)

	crosshair_label = _make_label("+", 24, Color(0.72, 0.82, 0.83, 0.68))
	crosshair_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	crosshair_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	overlay_root.add_child(crosshair_label)

	prompt_label = _make_label("", 17, Color(0.95, 0.82, 0.5))
	prompt_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	prompt_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	prompt_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	overlay_root.add_child(prompt_label)

	flashlight_button = _make_button("ФОНАРЬ: ВКЛ", 14)
	overlay_root.add_child(flashlight_button)
	flashlight_button.pressed.connect(_on_flashlight_pressed)

	interact_button = _make_button("ВЗАИМОДЕЙСТВИЕ", 14)
	overlay_root.add_child(interact_button)
	interact_button.pressed.connect(_on_interact_pressed)

	run_button = _make_button("БЕГ", 16)
	overlay_root.add_child(run_button)
	run_button.button_down.connect(_on_run_pressed)
	run_button.button_up.connect(_on_run_released)

	crouch_button = _make_button("ПРИСЕСТЬ", 14)
	overlay_root.add_child(crouch_button)
	crouch_button.pressed.connect(_on_crouch_pressed)

	get_viewport().size_changed.connect(_layout_controls)
	_layout_controls()

func _make_label(text_value: String, font_size: int, color: Color) -> Label:
	var label := Label.new()
	label.text = text_value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.92))
	label.add_theme_constant_override("shadow_offset_x", 2)
	label.add_theme_constant_override("shadow_offset_y", 2)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	return label

func _make_button(text_value: String, font_size: int) -> Button:
	var button := Button.new()
	button.text = text_value
	button.focus_mode = Control.FOCUS_NONE
	button.mouse_filter = Control.MOUSE_FILTER_STOP
	button.add_theme_font_size_override("font_size", font_size)
	button.add_theme_color_override("font_color", Color(0.91, 0.95, 0.95))
	button.add_theme_color_override("font_hover_color", Color.WHITE)
	button.add_theme_color_override("font_pressed_color", Color(1.0, 0.83, 0.56))
	return button

func _layout_controls() -> void:
	if overlay_root == null:
		return
	var viewport_size := get_viewport().get_visible_rect().size
	var width := viewport_size.x
	var height := viewport_size.y
	if width <= 0.0 or height <= 0.0:
		return

	# Calculate positions from the actual viewport for tall/narrow Android screens.
	var margin := clampf(width * 0.035, 18.0, 28.0)
	var ui_scale := clampf(width / 720.0, 0.82, 1.12)
	objective_label.position = Vector2(margin, 20.0)
	objective_label.size = Vector2(maxf(150.0, width - margin * 2.0 - 150.0), 66.0)
	objective_label.add_theme_font_size_override("font_size", int(round(20.0 * ui_scale)))

	location_label.position = Vector2(margin, 91.0)
	location_label.size = Vector2(width - margin * 2.0, 28.0)
	location_label.add_theme_font_size_override("font_size", int(round(14.0 * ui_scale)))

	flashlight_button.position = Vector2(width - margin - 142.0 * ui_scale, 24.0)
	flashlight_button.size = Vector2(142.0 * ui_scale, 58.0 * ui_scale)

	message_label.position = Vector2(margin, 145.0)
	message_label.size = Vector2(width - margin * 2.0, 68.0)
	message_label.add_theme_font_size_override("font_size", int(round(19.0 * ui_scale)))

	crosshair_label.position = Vector2(width * 0.5 - 18.0, height * 0.5 - 22.0)
	crosshair_label.size = Vector2(36.0, 44.0)

	prompt_label.position = Vector2(margin, height - 292.0 * ui_scale)
	prompt_label.size = Vector2(width - margin * 2.0, 48.0 * ui_scale)
	prompt_label.add_theme_font_size_override("font_size", int(round(17.0 * ui_scale)))

	var joystick_size := 180.0 * ui_scale
	joystick.position = Vector2(margin, height - joystick_size - 24.0)
	joystick.size = Vector2(joystick_size, joystick_size)

	var right := width - margin
	var bottom := height - 24.0
	var button_height := 66.0 * ui_scale
	interact_button.position = Vector2(right - 166.0 * ui_scale, bottom - button_height * 2.65)
	interact_button.size = Vector2(166.0 * ui_scale, 58.0 * ui_scale)
	run_button.position = Vector2(right - 246.0 * ui_scale, bottom - button_height)
	run_button.size = Vector2(104.0 * ui_scale, button_height)
	crouch_button.position = Vector2(right - 132.0 * ui_scale, bottom - button_height)
	crouch_button.size = Vector2(132.0 * ui_scale, button_height)

func _process(delta: float) -> void:
	if message_time > 0.0:
		message_time -= delta
		if message_time <= 0.0 and message_label != null:
			message_label.text = ""

func set_objective(value: String) -> void:
	if objective_label != null:
		objective_label.text = value

func set_interact_prompt(value: String) -> void:
	if prompt_label != null:
		prompt_label.text = value

func show_message(value: String, duration: float = 2.8) -> void:
	if message_label != null:
		message_label.text = value
	message_time = duration

func set_crouch_state(value: bool) -> void:
	if crouch_button != null:
		crouch_button.text = "ВСТАТЬ" if value else "ПРИСЕСТЬ"

func set_flashlight_state(value: bool) -> void:
	if flashlight_button != null:
		flashlight_button.text = "ФОНАРЬ: ВКЛ" if value else "ФОНАРЬ: ВЫКЛ"

func _on_move_changed(value: Vector2) -> void:
	move_input.emit(value)

func _on_look_delta(value: Vector2) -> void:
	look_input.emit(value)

func _on_flashlight_pressed() -> void:
	flashlight_toggled.emit()

func _on_interact_pressed() -> void:
	interact_requested.emit()

func _on_run_pressed() -> void:
	run_input.emit(true)

func _on_run_released() -> void:
	run_input.emit(false)

func _on_crouch_pressed() -> void:
	crouch_toggled.emit()
'''
write("scripts/mobile_hud.gd", hud)

# Keep the joystick knob centered when the responsive HUD changes its dimensions.
p = "scripts/mobile_joystick.gd"
s = read(p)
old = """func _ready() -> void:
\tmouse_filter = Control.MOUSE_FILTER_STOP
\tknob_position = size * 0.5
\tqueue_redraw()
"""
new = old + """
func _notification(what: int) -> void:
\tif what == NOTIFICATION_RESIZED:
\t\tif active_finger == -1:
\t\t\tknob_position = size * 0.5
\t\tqueue_redraw()
"""
if old not in s:
    raise SystemExit("Joystick ready function was not found.")
write(p, s.replace(old, new, 1))

# Add static regression checks so CI catches a return of the two reported bugs.
p = "tools/validate_project.py"
s = read(p)
checks = '''
# Regression checks for portrait Android layout and the locked-door interaction.
project_text = (ROOT / "project.godot").read_text(encoding="utf-8")
preset_text = (ROOT / "export_presets.cfg").read_text(encoding="utf-8")
main_script = (ROOT / "scripts/main.gd").read_text(encoding="utf-8")
player_script = (ROOT / "scripts/player.gd").read_text(encoding="utf-8")
hud_script = (ROOT / "scripts/mobile_hud.gd").read_text(encoding="utf-8")

if not re.search(r"(?m)^window/size/viewport_width=720\s*$", project_text):
    errors.append("Project viewport width must be 720 for portrait layout")
if not re.search(r"(?m)^window/size/viewport_height=1280\s*$", project_text):
    errors.append("Project viewport height must be 1280 for portrait layout")
if not re.search(r"(?m)^window/handheld/orientation=1\s*$", project_text):
    errors.append("Project handheld orientation must be portrait (1)")
if not re.search(r"(?m)^screen/orientation=2\s*$", preset_text):
    errors.append("Android export preset must explicitly request portrait orientation (Android value 2)")
if not re.search(r"(?m)^architectures/armeabi-v7a=true\s*$", preset_text):
    errors.append("Android export preset must include ARMv7 for older Galaxy A13 variants")
if 'exit_door_body.add_to_group("exit_door")' not in main_script:
    errors.append("Door body must be a fallback RayCast3D interaction target")
if 'target.is_in_group("exit_door")' not in player_script:
    errors.append("Player interaction must accept the door body as a target")
if 'exit_door_body.set_deferred("collision_layer", 0)' not in main_script:
    errors.append("Opening the door must disable its collision layer")
if 'get_viewport().size_changed.connect(_layout_controls)' not in hud_script:
    errors.append("Mobile HUD must relayout when the viewport changes")
'''
if "Regression checks for portrait Android layout" not in s:
    s = s.replace("if errors:\n", checks + "\nif errors:\n", 1)
write(p, s)

# Keep project notes aligned with the actual mobile target.
p = "README.md"
s = read(p)
s = s.replace("Проект 3D survival horror от первого лица для Android", "Портретный (вертикальный) 3D survival horror от первого лица для Android", 1)
s = s.replace("- базовый HUD на русском языке и простое аварийное освещение.", "- базовый HUD на русском языке и простое аварийное освещение;\n- портретная компоновка 720×1280 с адаптивным размещением элементов;\n- исправленное взаимодействие с дверью и снятие коллизии после открытия.", 1)
s = s.replace("ориентирован на ARM64.", "фиксирует портретную ориентацию и включает ARM64 + ARMv7 для вариантов Galaxy A13.", 1)
write(p, s)

p = "docs/PROJECT_STATUS.md"
s = read(p)
s = s.replace("Настроен ландшафтный экран", "Настроен портретный (вертикальный) экран", 1)
s = s.replace("- [x] Добавлен интерактивный цикл: карта доступа → дверь → выход из тестовой зоны.", "- [x] Добавлен интерактивный цикл: карта доступа → дверь → выход из тестовой зоны.\n- [x] Исправлена цель RayCast3D для двери и отключение коллизии после открытия.\n- [x] HUD адаптируется под портретные экраны и поворот/изменение размеров viewport.\n- [x] Android export включает ARM64 и ARMv7.", 1)
s = s.replace("- [ ] Проверить сцены/скрипты.", "- [ ] Проверить игровой процесс на физическом Samsung Galaxy A13.", 1)
write(p, s)

print("Applied LAST SIGNAL v0.1.1 portrait + door fixes.")
