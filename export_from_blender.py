"""
Firefly 萤火虫 涂装设计工具 - Blender 导出脚本（兼容 4.x / 5.x）
==============================================================
使用方法：
  1. 在 Blender 中打开你的 .blend 文件
  2. 切换到 Scripting 工作区
  3. 打开此脚本，点击 Run Script（或按 Alt+P）
  4. 报错的话把错误信息复制给我

导出内容（放在 .blend 同目录 firefly_wrap_export/）：
  - firefly.glb           — 车身 3D 模型
  - templates/left.png    — 左侧正交视图
  - templates/right.png   — 右侧
  - templates/front.png   — 前侧
  - templates/rear.png    — 后侧
  - templates/top.png     — 顶部
"""

import bpy
import os
import sys
from mathutils import Vector


def log(msg):
    print(f"[EXPORT] {msg}")
    sys.stdout.flush()


def get_output_dir():
    blend_path = bpy.data.filepath
    if not blend_path:
        blend_path = os.path.join(os.path.expanduser("~"), "Desktop", "untitled.blend")
    base_dir = os.path.dirname(blend_path)
    output_dir = os.path.join(base_dir, "firefly_wrap_export")
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "templates"), exist_ok=True)
    return output_dir


def get_render_engine():
    """Detect correct EEVEE render engine name for this Blender version"""
    # Blender 5.0+ uses 'BLENDER_EEVEE', 4.x uses 'BLENDER_EEVEE_NEXT'
    ver = bpy.app.version
    if ver[0] >= 5:
        return 'BLENDER_EEVEE'
    else:
        # Try BLENDER_EEVEE_NEXT first, fallback to BLENDER_EEVEE
        return 'BLENDER_EEVEE'


def get_all_mesh_objects():
    """Collect ALL visible mesh objects (including wheels, glass, etc.)"""
    car_meshes = []
    for obj in bpy.data.objects:
        if obj.type != 'MESH':
            continue
        if obj.hide_viewport or obj.hide_render:
            continue
        car_meshes.append(obj)

    log(f"找到 {len(car_meshes)} 个 mesh 对象:")
    for obj in car_meshes:
        log(f"  - {obj.name} (面数: {len(obj.data.polygons)})")

    return car_meshes


def export_glb(output_dir, car_objects):
    log("=== 导出 GLB ===")

    # Deselect all
    bpy.ops.object.select_all(action='DESELECT')
    for obj in car_objects:
        obj.select_set(True)

    glb_path = os.path.join(output_dir, "firefly.glb")

    # Build export kwargs based on available params
    export_kwargs = {
        'filepath': glb_path,
        'use_selection': True,
        'export_format': 'GLB',
        'export_texcoords': True,
        'export_normals': True,
    }

    # These params may not exist in all versions
    try:
        bpy.ops.export_scene.gltf(
            **export_kwargs,
            export_apply=True,
            export_materials='EXPORT',
        )
    except TypeError:
        # Fallback for older Blender versions
        bpy.ops.export_scene.gltf(**export_kwargs)

    size_mb = os.path.getsize(glb_path) / (1024 * 1024)
    log(f"GLB 已导出: {os.path.basename(glb_path)} ({size_mb:.1f} MB)")
    return glb_path


def render_ortho_views(output_dir, car_objects):
    log("=== 导出正交视图模板 ===")

    engine = get_render_engine()
    log(f"使用渲染引擎: {engine}")

    # Make sure we're in object mode
    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    # Camera direction vectors (world space)
    views = {
        'left':  Vector((-1, 0, 0)),
        'right': Vector((1, 0, 0)),
        'front': Vector((0, -1, 0)),
        'rear':  Vector((0, 1, 0)),
        'top':   Vector((0, 0, 1)),
    }

    # Compute scene bounds of all car objects
    all_verts = []
    for obj in car_objects:
        mesh = obj.data
        for v in mesh.vertices:
            all_verts.append(obj.matrix_world @ v.co)

    if not all_verts:
        log("  错误: 车身 mesh 没有顶点数据")
        return

    # Bounding box
    min_corner = Vector((
        min(v.x for v in all_verts),
        min(v.y for v in all_verts),
        min(v.z for v in all_verts),
    ))
    max_corner = Vector((
        max(v.x for v in all_verts),
        max(v.y for v in all_verts),
        max(v.z for v in all_verts),
    ))
    center = (min_corner + max_corner) / 2
    size = max_corner - min_corner
    max_dim = max(size.x, size.y, size.z)
    log(f"  包围盒: {size.x:.2f} × {size.y:.2f} × {size.z:.2f}")

    for view_name, direction in views.items():
        log(f"  渲染 {view_name}...")

        # Create camera
        cam_data = bpy.data.cameras.new(name=f"_wrap_cam_{view_name}")
        cam_data.type = 'ORTHO'
        cam_data.ortho_scale = max_dim * 1.2

        cam_obj = bpy.data.objects.new(name=f"_wrap_cam_{view_name}", object_data=cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)

        # Place camera
        cam_pos = center + direction * max_dim * 3
        cam_obj.location = cam_pos

        # Look at center
        look_dir = center - cam_pos
        cam_obj.rotation_euler = look_dir.to_track_quat('-Z', 'Y').to_euler()

        # Set as active camera
        bpy.context.scene.camera = cam_obj

        # Render settings
        scene = bpy.context.scene
        scene.render.engine = engine
        scene.render.resolution_x = 2048
        scene.render.resolution_y = 2048
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.render.film_transparent = True

        filepath = os.path.join(output_dir, "templates", f"{view_name}.png")
        scene.render.filepath = filepath
        bpy.ops.render.render(write_still=True)

        # Cleanup
        bpy.data.objects.remove(cam_obj)
        bpy.data.cameras.remove(cam_data)

        log(f"    已保存: templates/{view_name}.png")


def export_uv_layout(output_dir, car_objects):
    log("=== 导出 UV 布局参考 ===")

    engine = get_render_engine()

    if bpy.context.mode != 'OBJECT':
        bpy.ops.object.mode_set(mode='OBJECT')

    bpy.ops.object.select_all(action='DESELECT')
    for obj in car_objects:
        obj.select_set(True)

    # Assign temporary colored materials to distinguish objects
    colors = [
        (0.8, 0.2, 0.2, 1),
        (0.2, 0.6, 0.2, 1),
        (0.2, 0.2, 0.8, 1),
        (0.8, 0.6, 0.1, 1),
        (0.6, 0.2, 0.6, 1),
        (0.2, 0.6, 0.6, 1),
        (0.8, 0.8, 0.2, 1),
        (0.4, 0.4, 0.4, 1),
    ]

    temp_mats = []
    for i, obj in enumerate(car_objects):
        color = colors[i % len(colors)]
        mat = bpy.data.materials.new(name=f"_wrap_temp_{obj.name}")
        mat.diffuse_color = color
        mat.use_nodes = False  # Simplify
        # Clear existing material slots and assign temp
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        temp_mats.append(mat)

    scene = bpy.context.scene
    scene.render.engine = engine
    scene.render.resolution_x = 4096
    scene.render.resolution_y = 4096
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True

    filepath = os.path.join(output_dir, "templates", "uv_layout.png")
    scene.render.filepath = filepath
    bpy.ops.render.render(write_still=True)

    # Cleanup temp materials
    for mat in temp_mats:
        bpy.data.materials.remove(mat)

    log(f"UV 布局已导出: templates/uv_layout.png")


def main():
    log("=" * 60)
    log(f"  Blender {bpy.app.version_string} | Python {sys.version_info.major}.{sys.version_info.minor}")
    log("  Firefly 涂装工具 - 导出脚本")
    log("=" * 60)

    output_dir = get_output_dir()
    log(f"输出目录: {output_dir}")

    try:
        car_objects = get_all_mesh_objects()
        if not car_objects:
            log("错误: 没有找到任何 mesh 对象")
            return
    except Exception as e:
        log(f"错误: 获取车身对象失败 — {e}")
        return

    try:
        export_glb(output_dir, car_objects)
    except Exception as e:
        log(f"错误: GLB 导出失败 — {e}")
        log("尝试不勾选 apply...")
        # Retry without export_apply
        try:
            bpy.ops.object.select_all(action='DESELECT')
            for obj in car_objects:
                obj.select_set(True)
            glb_path = os.path.join(output_dir, "firefly.glb")
            bpy.ops.export_scene.gltf(filepath=glb_path, use_selection=True, export_format='GLB')
            log(f"GLB 已导出 (fallback): {os.path.basename(glb_path)}")
        except Exception as e2:
            log(f"错误: GLB 导出重试也失败 — {e2}")

    try:
        render_ortho_views(output_dir, car_objects)
    except Exception as e:
        log(f"错误: 正交视图渲染失败 — {e}")
        import traceback
        traceback.print_exc()

    try:
        export_uv_layout(output_dir, car_objects)
    except Exception as e:
        log(f"错误: UV 布局导出失败 — {e}")

    log("=" * 60)
    log("  导出完成")
    log(f"  文件: {output_dir}")
    log("=" * 60)


if __name__ == "__main__":
    main()
