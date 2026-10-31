extends CharacterBody3D
## The Watcher: patrol, investigate sound, detect by sight, chase, search and return.
enum State { PATROL, INVESTIGATE, CHASE, SEARCH, RETURN }

const WALK_SPEED := 1.65
const RUN_SPEED := 3.65
const SIGHT_RANGE := 17.0
const HEARING_WALK := 8.0
const HEARING_RUN := 18.0
const HEARING_CROUCH := 2.4
const CATCH_DISTANCE := 1.25

var target: CharacterBody3D
var hud: Node
var state: State = State.PATROL
var patrol_points: Array[Vector3] = [Vector3(0, 0, -13.0), Vector3(0, 0, -24.0)]
var patrol_index := 0
var last_known_position := Vector3.ZERO
var state_time := 0.0
var gait_time := 0.0
var caught := false
var body_pivot: Node3D
var head_pivot: Node3D
var left_arm: Node3D
var right_arm: Node3D
var left_leg: Node3D
var right_leg: Node3D
var eye_light: OmniLight3D
var alert_light: OmniLight3D

func _ready() -> void:
	name = "TheWatcher"
	add_to_group("monster")
	collision_layer = 2
	collision_mask = 1
	var collider := CollisionShape3D.new()
	var shape := CapsuleShape3D.new()
	shape.radius = 0.34
	shape.height = 2.35
	collider.shape = shape
	collider.position.y = 1.18
	add_child(collider)
	_build_model()
	target = get_tree().get_first_node_in_group("player") as CharacterBody3D
	hud = get_tree().get_first_node_in_group("mobile_hud")
	last_known_position = global_position

func _mat(color: Color, glow: bool = false) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = 0.96
	if glow:
		material.emission_enabled = true
		material.emission = color
		material.emission_energy_multiplier = 1.8
	return material

func _capsule(parent: Node3D, pos: Vector3, radius: float, height: float, material: Material) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := CapsuleMesh.new()
	mesh.radius = radius
	mesh.height = height
	mesh.radial_segments = 8
	mesh.rings = 4
	node.mesh = mesh
	node.material_override = material
	node.position = pos
	parent.add_child(node)
	return node

func _sphere(parent: Node3D, pos: Vector3, radius: float, material: Material) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	var mesh := SphereMesh.new()
	mesh.radius = radius
	mesh.height = radius * 2.0
	mesh.radial_segments = 8
	mesh.rings = 4
	node.mesh = mesh
	node.material_override = material
	node.position = pos
	parent.add_child(node)
	return node

func _limb(parent: Node3D, pos: Vector3, radius: float, length: float, material: Material) -> Node3D:
	var pivot := Node3D.new()
	pivot.position = pos
	parent.add_child(pivot)
	_capsule(pivot, Vector3(0, -length * 0.5, 0), radius, length, material)
	var hand := _sphere(pivot, Vector3(0, -length + 0.04, -0.015), radius * 1.12, material)
	hand.scale = Vector3(0.8, 1.35, 0.75)
	return pivot

func _build_model() -> void:
	var skin := _mat(Color(0.34, 0.36, 0.34))
	var dark := _mat(Color(0.012, 0.016, 0.018))
	var eyes := _mat(Color(0.72, 0.018, 0.008), true)
	body_pivot = Node3D.new()
	body_pivot.position.y = 1.35
	add_child(body_pivot)
	_capsule(body_pivot, Vector3.ZERO, 0.36, 0.88, skin)
	_capsule(body_pivot, Vector3(0, 0.66, 0.015), 0.2, 0.42, skin)
	head_pivot = Node3D.new()
	head_pivot.position = Vector3(0, 0.82, -0.015)
	body_pivot.add_child(head_pivot)
	_capsule(head_pivot, Vector3(0, 0.18, 0), 0.235, 0.47, skin)
	_sphere(head_pivot, Vector3(-0.09, 0.22, -0.202), 0.035, eyes)
	_sphere(head_pivot, Vector3(0.09, 0.22, -0.202), 0.035, eyes)
	var mouth := MeshInstance3D.new()
	var mouth_mesh := BoxMesh.new()
	mouth_mesh.size = Vector3(0.22, 0.12, 0.12)
	mouth.mesh = mouth_mesh
	mouth.material_override = dark
	mouth.position = Vector3(0, 0.02, -0.16)
	head_pivot.add_child(mouth)
	left_arm = _limb(body_pivot, Vector3(-0.38, 0.28, 0), 0.115, 1.05, skin)
	right_arm = _limb(body_pivot, Vector3(0.38, 0.28, 0), 0.115, 1.05, skin)
	left_leg = _limb(self, Vector3(-0.18, 0.84, 0), 0.145, 0.92, skin)
	right_leg = _limb(self, Vector3(0.18, 0.84, 0), 0.145, 0.92, skin)
	var shoulders := _sphere(body_pivot, Vector3(0, 0.34, 0), 0.34, skin)
	shoulders.scale = Vector3(1.0, 0.62, 0.72)
	eye_light = OmniLight3D.new()
	eye_light.position = Vector3(0, 2.56, -0.16)
	eye_light.light_color = Color(0.72, 0.025, 0.012)
	eye_light.light_energy = 0.12
	eye_light.omni_range = 2.0
	eye_light.shadow_enabled = false
	add_child(eye_light)
	alert_light = OmniLight3D.new()
	alert_light.position = Vector3(0, 2.9, 0)
	alert_light.light_color = Color(0.8, 0.025, 0.012)
	alert_light.light_energy = 0.0
	alert_light.omni_range = 4.5
	alert_light.shadow_enabled = false
	add_child(alert_light)

func _physics_process(delta: float) -> void:
	if caught or not is_instance_valid(target):
		return
	state_time += delta
	var sees := _can_see_player()
	if sees:
		last_known_position = target.global_position
		_set_state(State.CHASE)
	elif state != State.CHASE and _hears_player():
		last_known_position = target.global_position
		_set_state(State.INVESTIGATE)

	var destination := global_position
	var speed := WALK_SPEED
	match state:
		State.PATROL:
			destination = patrol_points[patrol_index]
			if global_position.distance_to(destination) < 1.0:
				patrol_index = (patrol_index + 1) % patrol_points.size()
				state_time = 0.0
		State.INVESTIGATE:
			destination = last_known_position
			if global_position.distance_to(destination) < 1.2:
				_set_state(State.SEARCH)
		State.CHASE:
			destination = target.global_position if sees else last_known_position
			speed = RUN_SPEED
			if not sees and global_position.distance_to(last_known_position) < 1.3:
				_set_state(State.SEARCH)
		State.SEARCH:
			destination = last_known_position
			if state_time > 4.2:
				_set_state(State.RETURN)
		State.RETURN:
			destination = patrol_points[patrol_index]
			if global_position.distance_to(destination) < 1.2:
				_set_state(State.PATROL)
	_move_to(destination, speed, delta)
	_animate(delta)
	if global_position.distance_to(target.global_position) <= CATCH_DISTANCE:
		_catch_player()

func _set_state(next_state: State) -> void:
	if state == next_state:
		return
	state = next_state
	state_time = 0.0
	match state:
		State.PATROL:
			alert_light.light_energy = 0.0
		State.INVESTIGATE:
			alert_light.light_energy = 0.18
		State.CHASE:
			alert_light.light_energy = 0.55
			if hud != null:
				hud.call("show_message", "ОН ТЕБЯ ЗАМЕТИЛ. БЕГИ!", 2.0)
		State.SEARCH:
			alert_light.light_energy = 0.24
		State.RETURN:
			alert_light.light_energy = 0.08

func _can_see_player() -> bool:
	var eye := global_position + Vector3(0, 2.45, 0)
	var player_eye := target.global_position + Vector3(0, 1.35, 0)
	var offset := player_eye - eye
	if offset.length() > SIGHT_RANGE or offset.normalized().dot(-global_transform.basis.z) < 0.2:
		return false
	var query := PhysicsRayQueryParameters3D.create(eye, player_eye)
	query.exclude = [get_rid()]
	query.collision_mask = 1
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	return not hit.is_empty() and hit.get("collider") == target

func _hears_player() -> bool:
	var distance := global_position.distance_to(target.global_position)
	var player_speed := Vector2(target.velocity.x, target.velocity.z).length()
	var hearing := HEARING_WALK
	if target.get("crouching") == true:
		hearing = HEARING_CROUCH
	elif player_speed > 4.0:
		hearing = HEARING_RUN
	elif player_speed < 0.35:
		return false
	return distance <= hearing

func _move_to(destination: Vector3, speed: float, delta: float) -> void:
	var direction := Vector3(destination.x - global_position.x, 0, destination.z - global_position.z)
	if direction.length() > 0.35:
		direction = direction.normalized()
		velocity.x = move_toward(velocity.x, direction.x * speed, 5.0 * delta)
		velocity.z = move_toward(velocity.z, direction.z * speed, 5.0 * delta)
		look_at(global_position + direction, Vector3.UP)
	else:
		velocity.x = move_toward(velocity.x, 0.0, 5.0 * delta)
		velocity.z = move_toward(velocity.z, 0.0, 5.0 * delta)
	if not is_on_floor():
		velocity.y -= 9.8 * delta
	else:
		velocity.y = -0.1
	move_and_slide()

func _animate(delta: float) -> void:
	gait_time += delta * (8.0 if state == State.CHASE else 4.8)
	var swing := sin(gait_time) * clampf(Vector2(velocity.x, velocity.z).length() / RUN_SPEED, 0.0, 1.0)
	left_arm.rotation.x = -0.65 - swing * 0.38
	right_arm.rotation.x = -0.65 + swing * 0.38
	left_leg.rotation.x = swing * 0.52
	right_leg.rotation.x = -swing * 0.52
	body_pivot.rotation.z = sin(gait_time * 0.5) * 0.035
	head_pivot.rotation.x = -0.06 + sin(gait_time * 0.7) * 0.025
	eye_light.light_energy = 0.1 + (0.25 if state == State.CHASE else 0.0)

func _catch_player() -> void:
	if caught:
		return
	caught = true
	velocity = Vector3.ZERO
	if hud != null:
		hud.call("show_message", "ТЕБЯ НАШЛИ  ·  СИГНАЛ ПОТЕРЯН", 8.0)
	target.set_physics_process(false)
	var camera := target.get_node_or_null("Head/Camera3D") as Camera3D
	if camera != null:
		camera.rotation.z = deg_to_rad(8.0)
		camera.fov = 78.0
