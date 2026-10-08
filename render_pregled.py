import bpy, os
sc = bpy.context.scene
sc.frame_set(150)
sc.render.resolution_x, sc.render.resolution_y = 960, 540
sc.cycles.samples = 12
sc.render.filepath = os.path.join(os.path.dirname(bpy.data.filepath), "magacin_pregled.png")
bpy.ops.render.render(write_still=True)
