extends Camera3D
## Cámara libre para recorrer la demo y grabar clips.
## WASD mover, Q/E bajar/subir, clic derecho + ratón mirar,
## Shift rápido, rueda cambia la velocidad.

@export var velocidad := 120.0
@export var sensibilidad := 0.003

var _mirando := false


func _unhandled_input(evento: InputEvent) -> void:
	if evento is InputEventMouseButton:
		if evento.button_index == MOUSE_BUTTON_RIGHT:
			_mirando = evento.pressed
			Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if _mirando else Input.MOUSE_MODE_VISIBLE
		elif evento.pressed and evento.button_index == MOUSE_BUTTON_WHEEL_UP:
			velocidad = minf(velocidad * 1.2, 2000.0)
		elif evento.pressed and evento.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			velocidad = maxf(velocidad / 1.2, 5.0)
	elif evento is InputEventMouseMotion and _mirando:
		rotation.y -= evento.relative.x * sensibilidad
		rotation.x = clampf(rotation.x - evento.relative.y * sensibilidad, -1.55, 1.55)


func _process(delta: float) -> void:
	var entrada := Vector3.ZERO
	if Input.is_physical_key_pressed(KEY_W): entrada.z -= 1.0
	if Input.is_physical_key_pressed(KEY_S): entrada.z += 1.0
	if Input.is_physical_key_pressed(KEY_A): entrada.x -= 1.0
	if Input.is_physical_key_pressed(KEY_D): entrada.x += 1.0
	if Input.is_physical_key_pressed(KEY_E): entrada.y += 1.0
	if Input.is_physical_key_pressed(KEY_Q): entrada.y -= 1.0
	if entrada == Vector3.ZERO:
		return
	var rapido := 4.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 1.0
	position += (global_transform.basis * entrada.normalized()) * velocidad * rapido * delta
