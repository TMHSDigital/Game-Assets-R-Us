# SPDX-License-Identifier: GPL-3.0-or-later
# Loads every imported GLB under res://models and writes what Godot built:
# visual meshes with their AABB size, and physics shapes with their type.
# Run: godot --headless --path PROJECT --script res://godot_check.gd -- OUT.json
extends SceneTree


func _world(node: Node) -> Transform3D:
	# The tree is not running inside _init, so global_transform is not
	# available; accumulate local transforms instead.
	var xf := Transform3D.IDENTITY
	var n := node
	while n != null:
		if n is Node3D:
			xf = n.transform * xf
		n = n.get_parent()
	return xf


func _collect(node: Node, report: Dictionary) -> void:
	if node is MeshInstance3D:
		var aabb: AABB = _world(node) * node.get_aabb()
		report["meshes"].append({"name": str(node.name), "size": [aabb.size.x, aabb.size.y, aabb.size.z]})
	if node is CollisionShape3D and node.shape != null:
		report["shapes"].append({"name": str(node.get_parent().name), "type": node.shape.get_class()})
	if node is StaticBody3D:
		report["bodies"].append(str(node.name))
	for child in node.get_children():
		_collect(child, report)


func _init() -> void:
	var args := OS.get_cmdline_user_args()
	var out_path: String = args[0] if args.size() > 0 else "user://godot_check.json"
	var result := {}
	var dir := DirAccess.open("res://models")
	for file in dir.get_files():
		if not file.ends_with(".glb"):
			continue
		var packed: PackedScene = load("res://models/" + file)
		var report := {"loaded": packed != null, "meshes": [], "shapes": [], "bodies": []}
		if packed != null:
			var root := packed.instantiate()
			_collect(root, report)
			root.free()
		result[file] = report
	var fh := FileAccess.open(out_path, FileAccess.WRITE)
	fh.store_string(JSON.stringify(result, "  ", true))
	fh.close()
	print("GODOT_CHECK files=", result.size())
	quit(0)
