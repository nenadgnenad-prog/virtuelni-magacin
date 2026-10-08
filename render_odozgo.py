"""Render tlocrta magacina odozgo (ortogonalno) u magacin_odozgo.png.
Pokretanje: blender.exe -b magacin.blend --python render_odozgo.py"""
import bpy
import os

sc = bpy.context.scene
cd = bpy.data.cameras.new("Kamera_odozgo")
cd.type = 'ORTHO'
cd.ortho_scale = 64
co = bpy.data.objects.new("Kamera_odozgo", cd)
co.location = (30, 25, 60)
sc.collection.objects.link(co)
sc.camera = co
sc.render.resolution_x = 1280
sc.render.resolution_y = 1066
sc.cycles.samples = 16
sc.render.filepath = os.path.join(os.path.dirname(bpy.data.filepath), "magacin_odozgo.png")
bpy.ops.render.render(write_still=True)
