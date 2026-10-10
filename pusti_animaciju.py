"""Otvara magacin.blend, namesta pogled i pusta animaciju.
Pokretanje: blender.exe magacin.blend --python pusti_animaciju.py"""
import bpy
import math
from mathutils import Euler

sc = bpy.context.scene
sc.sync_mode = 'FRAME_DROP'      # pusta u realnom vremenu (preskace frejmove ako je racunar spor)
sc.frame_set(1)


def podesi_i_pusti():
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type != 'VIEW_3D':
                continue
            sp = area.spaces.active
            sp.clip_end = 1000
            sp.shading.type = 'SOLID'
            sp.shading.color_type = 'MATERIAL'
            sp.shading.show_shadows = True
            sp.overlay.show_extras = False          # bez ikonica svetala i kamere
            sp.overlay.show_floor = False
            r3d = sp.region_3d
            r3d.view_perspective = 'PERSP'
            r3d.view_location = (30.0, 16.0, 0.0)
            r3d.view_distance = 62
            r3d.view_rotation = Euler((math.radians(58), 0, math.radians(25))).to_quaternion()
            region = next(r for r in area.regions if r.type == 'WINDOW')
            bpy.ops.screen.animation_play({"window": win, "screen": win.screen,
                                           "area": area, "region": region})
            return None
    return 1.0    # prozor jos nije spreman - probaj ponovo za 1 s


bpy.app.timers.register(podesi_i_pusti, first_interval=2.0)
