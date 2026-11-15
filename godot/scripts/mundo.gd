extends Node3D
## Lee los JSON de res://datos (generados por herramientas/descargar_osm.py)
## y levanta cada edificio como un prisma sobre su huella real.
## Todo es placeholder: un color por edificio, sin estilo todavía.

const CARPETA_DATOS := "res://datos"
const COLOR_SUELO := Color(0.78, 0.74, 0.66)
const COLOR_CALLE := Color(0.33, 0.33, 0.35)
const COLOR_PEATONAL := Color(0.62, 0.58, 0.52)
const TIPOS_PEATONALES := ["pedestrian", "footway", "path", "steps", "cycleway"]
# Paleta provisional de fachadas; el generador por estilo la reemplazará.
const PALETA: Array[Color] = [
	Color(0.93, 0.80, 0.45), Color(0.87, 0.55, 0.38), Color(0.95, 0.91, 0.82),
	Color(0.55, 0.70, 0.80), Color(0.80, 0.42, 0.40), Color(0.90, 0.72, 0.60),
]

var _total_edificios := 0
var _total_calles := 0
var _descartados := 0
var _vistos := {}  # ids ya construidos: las zonas pueden solaparse


func _ready() -> void:
	_crear_ambiente()
	var limites := Rect2()
	var atribucion := ""
	for archivo in _archivos_de_datos():
		var datos: Dictionary = _leer_json(CARPETA_DATOS.path_join(archivo))
		if datos.is_empty():
			continue
		atribucion = datos.get("atribucion", atribucion)
		_construir_zona(datos)
		var l: Array = datos["limites"]
		var r := Rect2(Vector2(l[0][0], l[0][1]), Vector2(l[1][0] - l[0][0], l[1][1] - l[0][1])).abs()
		limites = r if limites.size == Vector2.ZERO else limites.merge(r)
	_crear_suelo(limites.grow(200.0))
	$Interfaz/Atribucion.text = atribucion
	$Interfaz/Info.text = "%d edificios, %d calles\nWASD mover · clic derecho mirar · Q/E bajar/subir · Shift rápido · rueda velocidad" % [_total_edificios, _total_calles]
	print("Edificios: %d, calles: %d, huellas descartadas: %d" % [_total_edificios, _total_calles, _descartados])
	if _total_edificios == 0:
		$Interfaz/Info.text = "No hay datos. Ejecuta: python herramientas/descargar_osm.py"


func _archivos_de_datos() -> Array:
	var lista := []
	var carpeta := DirAccess.open(CARPETA_DATOS)
	if carpeta:
		for nombre in carpeta.get_files():
			if nombre.ends_with(".json"):
				lista.append(nombre)
	lista.sort()
	return lista


func _leer_json(ruta: String) -> Dictionary:
	var texto := FileAccess.get_file_as_string(ruta)
	var datos = JSON.parse_string(texto)
	if typeof(datos) != TYPE_DICTIONARY:
		push_warning("No se pudo leer %s" % ruta)
		return {}
	return datos


func _construir_zona(datos: Dictionary) -> void:
	var zona := Node3D.new()
	zona.name = datos["zona"]
	add_child(zona)

	# Todos los edificios de la zona van en una sola malla: una sola draw call.
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for e in datos["edificios"]:
		if _vistos.has(e["id"]):
			continue
		_vistos[e["id"]] = true
		if _agregar_edificio(st, e):
			_total_edificios += 1
		else:
			_descartados += 1
	zona.add_child(_malla_con_color_de_vertice("Edificios", st, 0.9))

	st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	for c in datos["calles"]:
		if _vistos.has(c["id"]):
			continue
		_vistos[c["id"]] = true
		_agregar_calle(st, c)
		_total_calles += 1
	zona.add_child(_malla_con_color_de_vertice("Calles", st, 1.0))


func _malla_con_color_de_vertice(nombre: String, st: SurfaceTool, rugosidad: float) -> MeshInstance3D:
	var material := StandardMaterial3D.new()
	material.vertex_color_use_as_albedo = true
	material.roughness = rugosidad
	st.set_material(material)
	var nodo := MeshInstance3D.new()
	nodo.name = nombre
	nodo.mesh = st.commit()
	return nodo


## Agrega un triángulo cuya cara visible mira hacia `normal`,
## sin depender del orden en que lleguen los vértices.
## (En Godot la cara frontal es la que se ve en sentido horario.)
func _tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3, normal: Vector3) -> void:
	if (c - a).cross(b - a).dot(normal) < 0.0:
		var t := b
		b = c
		c = t
	st.set_normal(normal)
	st.add_vertex(a)
	st.add_vertex(b)
	st.add_vertex(c)


func _area_con_signo(pts: PackedVector2Array) -> float:
	var suma := 0.0
	for i in pts.size():
		var a := pts[i]
		var b := pts[(i + 1) % pts.size()]
		suma += a.x * b.y - b.x * a.y
	return suma * 0.5


## Prisma: techo plano triangulado + una pared por cada lado de la huella.
func _agregar_edificio(st: SurfaceTool, e: Dictionary) -> bool:
	var huella := PackedVector2Array()
	for p in e["huella"]:
		huella.append(Vector2(p[0], p[1]))
	# Con área positiva, la normal exterior del lado a->b es (dy, -dx).
	if _area_con_signo(huella) < 0.0:
		huella.reverse()
	var indices := Geometry2D.triangulate_polygon(huella)
	if indices.is_empty():
		return false  # huella que se cruza a sí misma

	var altura: float = e["altura"]
	var base := PALETA[hash(e["id"]) % PALETA.size()]
	var color_techo := Color(0.62, 0.36, 0.26) if altura < 14.0 else Color(0.70, 0.70, 0.70)

	st.set_color(color_techo)
	for i in range(0, indices.size(), 3):
		var p0 := huella[indices[i]]
		var p1 := huella[indices[i + 1]]
		var p2 := huella[indices[i + 2]]
		_tri(st, Vector3(p0.x, altura, p0.y), Vector3(p1.x, altura, p1.y), Vector3(p2.x, altura, p2.y), Vector3.UP)

	var luz := Vector3(0.5, 0.0, 0.87).normalized()
	var n := huella.size()
	for i in n:
		var a := huella[i]
		var b := huella[(i + 1) % n]
		var lado := b - a
		if lado.length_squared() < 0.0001:
			continue
		var normal2 := Vector2(lado.y, -lado.x).normalized()
		var normal := Vector3(normal2.x, 0.0, normal2.y)
		# Sombreado barato por orientación para que se lean los volúmenes.
		st.set_color(base.darkened(0.12 * (1.0 - normal.dot(luz))))
		var a0 := Vector3(a.x, 0.0, a.y)
		var b0 := Vector3(b.x, 0.0, b.y)
		var a1 := Vector3(a.x, altura, a.y)
		var b1 := Vector3(b.x, altura, b.y)
		_tri(st, a0, a1, b1, normal)
		_tri(st, a0, b1, b0, normal)
	return true


## Cinta plana a lo largo de la línea de la calle.
func _agregar_calle(st: SurfaceTool, c: Dictionary) -> void:
	var peatonal: bool = c["tipo"] in TIPOS_PEATONALES
	var y := 0.06 if peatonal else 0.1
	var medio: float = c["ancho"] * 0.5
	st.set_color(COLOR_PEATONAL if peatonal else COLOR_CALLE)
	var pts: Array = c["puntos"]
	for i in range(pts.size() - 1):
		var a := Vector2(pts[i][0], pts[i][1])
		var b := Vector2(pts[i + 1][0], pts[i + 1][1])
		var dir := b - a
		if dir.length_squared() < 0.0001:
			continue
		var lat := Vector2(-dir.y, dir.x).normalized() * medio
		# Se alarga un poco cada tramo para tapar los huecos en las curvas.
		var ext := dir.normalized() * minf(medio, 1.5)
		var p1 := a - ext + lat
		var p2 := a - ext - lat
		var p3 := b + ext - lat
		var p4 := b + ext + lat
		_tri(st, Vector3(p1.x, y, p1.y), Vector3(p2.x, y, p2.y), Vector3(p3.x, y, p3.y), Vector3.UP)
		_tri(st, Vector3(p1.x, y, p1.y), Vector3(p3.x, y, p3.y), Vector3(p4.x, y, p4.y), Vector3.UP)


func _crear_suelo(limites: Rect2) -> void:
	if limites.size == Vector2.ZERO:
		limites = Rect2(-500, -500, 1000, 1000)
	var plano := PlaneMesh.new()
	plano.size = limites.size
	var material := StandardMaterial3D.new()
	material.albedo_color = COLOR_SUELO
	plano.material = material
	var suelo := MeshInstance3D.new()
	suelo.name = "Suelo"
	suelo.mesh = plano
	var centro := limites.get_center()
	suelo.position = Vector3(centro.x, 0.0, centro.y)
	add_child(suelo)


func _crear_ambiente() -> void:
	var sol := DirectionalLight3D.new()
	sol.name = "Sol"
	sol.rotation_degrees = Vector3(-50.0, -35.0, 0.0)
	sol.shadow_enabled = true
	sol.directional_shadow_max_distance = 1200.0
	add_child(sol)

	var cielo := Sky.new()
	cielo.sky_material = ProceduralSkyMaterial.new()
	var ambiente := Environment.new()
	ambiente.background_mode = Environment.BG_SKY
	ambiente.sky = cielo
	ambiente.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	ambiente.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	var mundo := WorldEnvironment.new()
	mundo.name = "Ambiente"
	mundo.environment = ambiente
	add_child(mundo)
