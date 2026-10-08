"""
Virtuelni magacin 60 x 50 m (3000 m2), visina 10 m.
Blender 2.93 LTS.

Pokretanje:
  - u Blenderu: Scripting tab -> Open -> magacin.py -> Run Script
  - ili iz komandne linije (bez prozora):
      blender.exe -b --python magacin.py
    (snima magacin.blend pored skripte)

Koordinate: X 0..60 m (duzina), Y 0..50 m (sirina), Z = visina.
Juzni zid (Y=0) ima utovarne rampe, kancelarija je u severozapadnom uglu.
"""
import bpy
import bmesh
import os
import random

# ---------------------------------------------------------------- parametri
DUZINA = 60.0          # X
SIRINA = 50.0          # Y
VISINA = 10.0          # Z
DEBLJINA_ZIDA = 0.3

BROJ_RAMPI = 6
RAMPA_SIRINA = 3.5
RAMPA_VISINA = 4.0
RAMPE_SA_KAMIONOM = [1, 2, 4]    # indeksi rampi (0..5) na kojima je kamion

FPS = 25
KRAJ_ANIMACIJE = 480             # 19 s animacije (Space u Blenderu pusta animaciju)

KANC_X, KANC_Y = 12.0, 10.0      # kancelarija u uglu X 0..12, Y 40..50
KANC_VISINA = 3.5

# regali (paletni, podizni)
REGAL_Y0, REGAL_Y1 = 12.0, 38.0   # zona regala po Y (od zone za prijem do kancelarije)
REGAL_X0 = 13.5
POLJE = 2.7                       # sirina jednog polja regala
DUBINA = 1.1                      # dubina jednog reda
PROLAZ = 4.0                      # sirina prolaza za viljuskar
POZARNI_PUT = 4.0                 # poprecni protivpozarni put kroz sredinu regala
PP_Y = (REGAL_Y0 + REGAL_Y1) / 2  # Y sredina protivpozarnog puta
IZLAZ_SIRINA, IZLAZ_VISINA = 2.0, 2.5   # izlazi u nuzdi (istocni i zapadni zid)
NIVOI = [0.0, 1.8, 3.6, 5.4, 7.2] # visine nivoa (0 = pod)
VISINA_REGALA = 8.0
POPUNJENOST = 0.75                # verovatnoca da je mesto zauzeto paletom

random.seed(42)


# ---------------------------------------------------------------- pomocne
def ocisti_scenu():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for kolekcija in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                      bpy.data.cameras, bpy.data.collections):
        for blok in list(kolekcija):
            kolekcija.remove(blok)


def kolekcija(ime):
    c = bpy.data.collections.new(ime)
    bpy.context.scene.collection.children.link(c)
    return c


def materijal(ime, boja, hrapavost=0.6, metal=0.0, alpha=1.0):
    m = bpy.data.materials.new(ime)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*boja, 1.0)
    bsdf.inputs["Roughness"].default_value = hrapavost
    bsdf.inputs["Metallic"].default_value = metal
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = 'BLEND'
    m.diffuse_color = (*boja, alpha)   # boja u Solid prikazu
    return m


def kutija(bm, x0, y0, z0, x1, y1, z1, mi=0):
    """Dodaje kvadar od (x0,y0,z0) do (x1,y1,z1) u bmesh (mi = indeks materijala)."""
    v = [bm.verts.new(p) for p in (
        (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))]
    for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
              (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
        bm.faces.new([v[i] for i in f]).material_index = mi


def tocak(bm, x, y, z, r, sirina, mi=0, segmenti=16):
    """Valjak (tocak) sa osom po Y, centar (x, y, z)."""
    import math
    prsten = []
    for yy in (y - sirina / 2, y + sirina / 2):
        prsten.append([bm.verts.new((x + r * math.cos(2 * math.pi * i / segmenti), yy,
                                     z + r * math.sin(2 * math.pi * i / segmenti)))
                       for i in range(segmenti)])
    a, b = prsten
    for i in range(segmenti):
        j = (i + 1) % segmenti
        bm.faces.new((a[i], a[j], b[j], b[i])).material_index = mi
    bm.faces.new(list(reversed(a))).material_index = mi
    bm.faces.new(b).material_index = mi


def objekat(ime, bm, mat, kol):
    me = bpy.data.meshes.new(ime)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(ime, me)
    kol.objects.link(ob)
    return ob


# ---------------------------------------------------------------- scena
ocisti_scenu()
sc = bpy.context.scene
sc.unit_settings.system = 'METRIC'
sc.unit_settings.scale_length = 1.0

M = {
    "beton": materijal("Beton_pod", (0.45, 0.45, 0.43), 0.8),
    "zid": materijal("Zid_panel", (0.78, 0.80, 0.82), 0.5),
    "krov": materijal("Krov", (0.60, 0.62, 0.65), 0.5, 0.3),
    "vrata": materijal("Rampa_vrata", (0.20, 0.25, 0.32), 0.4, 0.5),
    "stub": materijal("Regal_stub", (0.05, 0.20, 0.55), 0.4, 0.6),
    "greda": materijal("Regal_greda", (0.95, 0.40, 0.05), 0.4, 0.6),
    "paleta": materijal("Paleta_drvo", (0.55, 0.40, 0.22), 0.9),
    "roba": materijal("Roba_karton", (0.70, 0.55, 0.35), 0.8),
    "linija": materijal("Linija_zuta", (0.95, 0.80, 0.05), 0.5),
    "kanc": materijal("Kancelarija_zid", (0.92, 0.92, 0.90), 0.6),
    "staklo": materijal("Staklo", (0.60, 0.80, 0.90), 0.05, 0.0, 0.3),
    "viljuskar": materijal("Viljuskar_zuta", (0.95, 0.65, 0.02), 0.35, 0.2),
    "guma": materijal("Guma", (0.03, 0.03, 0.03), 0.9),
    "jarbol": materijal("Jarbol_celik", (0.15, 0.15, 0.17), 0.4, 0.8),
    "pozar": materijal("Pozar_crvena", (0.85, 0.05, 0.03), 0.4),
    "pozar_pod": materijal("Pozarni_put_pod", (0.75, 0.35, 0.33), 0.7),
    "izlaz": materijal("Izlaz_zelena", (0.05, 0.65, 0.20), 0.4),
}

K_ZGRADA = kolekcija("Zgrada")
K_KROV = kolekcija("Krov")
K_REGALI = kolekcija("Regali")
K_ROBA = kolekcija("Roba")
K_VILJUSKARI = kolekcija("Viljuskari")
K_POZAR = kolekcija("Protivpozarna_zastita")
K_PRIKAZ = kolekcija("Svetla_i_kamera")

# ---------------------------------------------------------------- pod
bm = bmesh.new()
kutija(bm, -DEBLJINA_ZIDA, -DEBLJINA_ZIDA, -0.2,
       DUZINA + DEBLJINA_ZIDA, SIRINA + DEBLJINA_ZIDA, 0.0)
objekat("Pod", bm, M["beton"], K_ZGRADA)

# ---------------------------------------------------------------- zidovi
d = DEBLJINA_ZIDA
bm = bmesh.new()
# severni, istocni, zapadni zid - puni
kutija(bm, -d, SIRINA, 0, DUZINA + d, SIRINA + d, VISINA)
# istocni i zapadni zid sa otvorom za izlaz u nuzdi na sredini protivpozarnog puta
ia, ib = PP_Y - IZLAZ_SIRINA / 2, PP_Y + IZLAZ_SIRINA / 2
for xa, xb in ((DUZINA, DUZINA + d), (-d, 0)):
    kutija(bm, xa, 0, 0, xb, ia, VISINA)
    kutija(bm, xa, ia, IZLAZ_VISINA, xb, ib, VISINA)
    kutija(bm, xa, ib, 0, xb, SIRINA, VISINA)
# juzni zid sa otvorima za rampe
razmak = DUZINA / BROJ_RAMPI
otvori = [(razmak * (i + 0.5) - RAMPA_SIRINA / 2, razmak * (i + 0.5) + RAMPA_SIRINA / 2)
          for i in range(BROJ_RAMPI)]
x = -d
for a, b in otvori:
    kutija(bm, x, -d, 0, a, 0, VISINA)          # zid izmedju vrata
    kutija(bm, a, -d, RAMPA_VISINA, b, 0, VISINA)  # nadvratnik
    x = b
kutija(bm, x, -d, 0, DUZINA + d, 0, VISINA)
objekat("Zidovi", bm, M["zid"], K_ZGRADA)

# segmentna vrata rampi (malo uvucena)
bm = bmesh.new()
for i, (a, b) in enumerate(otvori):
    if i in RAMPE_SA_KAMIONOM:   # podignuta (otvorena) vrata
        kutija(bm, a, -d * 0.6, RAMPA_VISINA - 0.4, b, -d * 0.4, RAMPA_VISINA)
    else:
        kutija(bm, a, -d * 0.6, 0, b, -d * 0.4, RAMPA_VISINA)
objekat("Rampe_vrata", bm, M["vrata"], K_ZGRADA)

# ---------------------------------------------------------------- krov
bm = bmesh.new()
kutija(bm, -d, -d, VISINA, DUZINA + d, SIRINA + d, VISINA + 0.3)
krov = objekat("Krov", bm, M["krov"], K_KROV)
# krov je sakriven da bi se video unutrasnji prostor (oko u Outliner-u ga ukljucuje)
K_KROV.hide_viewport = False
krov.hide_set(True)
krov.hide_render = True

# ---------------------------------------------------------------- kancelarija
kx0, ky0 = 0.0, SIRINA - KANC_Y
t = 0.15
bm = bmesh.new()
kutija(bm, kx0 + KANC_X - t, ky0, 0, kx0 + KANC_X, SIRINA, KANC_VISINA)   # istocni zid
kutija(bm, kx0, ky0 + 0.0, KANC_VISINA - 0.15, kx0 + KANC_X, SIRINA, KANC_VISINA)  # plafon
# juzni zid sa vratima (1 m) i parapetom ispod prozora
kutija(bm, kx0, ky0, 0, kx0 + 1.5, ky0 + t, KANC_VISINA)
kutija(bm, kx0 + 2.5, ky0, 0, kx0 + KANC_X - t, ky0 + t, 1.0)
kutija(bm, kx0 + 1.5, ky0, 2.2, kx0 + KANC_X - t, ky0 + t, KANC_VISINA)
objekat("Kancelarija", bm, M["kanc"], K_ZGRADA)

bm = bmesh.new()
kutija(bm, kx0 + 2.5, ky0 + 0.05, 1.0, kx0 + KANC_X - t, ky0 + 0.1, 2.2)
objekat("Kancelarija_prozor", bm, M["staklo"], K_ZGRADA)

# ---------------------------------------------------------------- regali
# raspored redova po X: jednostruki uz zid, pa dvostruki (back-to-back), pa jednostruki
redovi = []          # (x_pocetak, broj_dubina)
x = REGAL_X0
redovi.append((x, 1)); x += DUBINA + PROLAZ
while x + 2 * DUBINA + PROLAZ + DUBINA <= DUZINA - 0.5:
    redovi.append((x, 2)); x += 2 * DUBINA + PROLAZ
redovi.append((x, 1))

# regali su podeljeni u dva bloka po Y, izmedju njih je protivpozarni put
sredina = (REGAL_Y0 + REGAL_Y1) / 2
blokovi = [(REGAL_Y0, sredina - POZARNI_PUT / 2), (sredina + POZARNI_PUT / 2, REGAL_Y1)]
broj_polja = 0

bm_stub, bm_greda, bm_paleta, bm_roba = (bmesh.new() for _ in range(4))
s = 0.09   # presek stuba
mesta = 0
zauzeto = 0
for (by0, by1), (rx, dubine) in [(b, r) for b in blokovi for r in redovi]:
    n = int((by1 - by0) // POLJE)
    broj_polja += n if rx == redovi[0][0] else 0
    # blok se poravnava uz protivpozarni put
    ys = ([by1 - (n - i) * POLJE for i in range(n + 1)] if by1 <= sredina
          else [by0 + i * POLJE for i in range(n + 1)])
    for k in range(dubine):
        x0 = rx + k * DUBINA
        x1 = x0 + DUBINA
        # stubovi (napred i pozadi) na svakoj granici polja
        for y in ys:
            for xs in (x0, x1 - s):
                kutija(bm_stub, xs, y - s / 2, 0, xs + s, y + s / 2, VISINA_REGALA)
        # grede i palete po polju i nivou
        for i in range(n):
            ya, yb = ys[i] + s / 2, ys[i + 1] - s / 2
            for z in NIVOI:
                if z > 0:
                    for xs in (x0, x1 - 0.05):
                        kutija(bm_greda, xs, ya, z - 0.12, xs + 0.05, yb, z)
                # dve palete (1.2 x 0.8) po polju
                for p in range(2):
                    mesta += 1
                    if random.random() > POPUNJENOST:
                        continue
                    zauzeto += 1
                    py0 = ya + 0.15 + p * 1.25
                    px0 = x0 + 0.05
                    kutija(bm_paleta, px0, py0, z, px0 + DUBINA - 0.1, py0 + 0.8, z + 0.15)
                    h = random.uniform(0.8, 1.5)
                    kutija(bm_roba, px0 + 0.03, py0 + 0.03, z + 0.15,
                           px0 + DUBINA - 0.13, py0 + 0.77, z + 0.15 + h)

objekat("Regali_stubovi", bm_stub, M["stub"], K_REGALI)
objekat("Regali_grede", bm_greda, M["greda"], K_REGALI)
objekat("Palete", bm_paleta, M["paleta"], K_ROBA)
objekat("Roba", bm_roba, M["roba"], K_ROBA)

# ---------------------------------------------------------------- oznake na podu
bm = bmesh.new()
w = 0.1
z0, z1 = 0.0, 0.01
# granica zone prijema/otpreme (ispred rampi)
kutija(bm, 0.5, 10.0, z0, DUZINA - 0.5, 10.0 + w, z1)
# ivice prolaza izmedju regala (po blokovima)
for by0, by1 in blokovi:
    for rx, dubine in redovi:
        sirina_reda = dubine * DUBINA
        for xl in (rx - 0.15, rx + sirina_reda + 0.05):
            kutija(bm, xl, by0 - 0.3, z0, xl + w, by1 + 0.3, z1)
# okvir kancelarije
kutija(bm, KANC_X + 0.3, ky0 - 0.5, z0, KANC_X + 0.3 + w, SIRINA - 0.2, z1)
objekat("Linije_pod", bm, M["linija"], K_ZGRADA)

# ---------------------------------------------------------------- protivpozarni put
# poprecni put (izmedju blokova, od zapadnog do istocnog izlaza) + uzduzni putevi
# uz zapadnu stranu i uz istocni zid, povezani sa zonom rampi
kraj_regala = redovi[-1][0] + redovi[-1][1] * DUBINA
putevi = [
    (0.3, sredina - POZARNI_PUT / 2, DUZINA - 0.3, sredina + POZARNI_PUT / 2),   # poprecni
    (KANC_X - 4.0, 10.3, KANC_X, ky0 - 0.3),                                     # zapadni
    (max(kraj_regala + 0.3, DUZINA - 4.0), 10.3, DUZINA - 0.3, SIRINA - 0.3),    # istocni
]
bm_pp = bmesh.new()
bm_ivica = bmesh.new()
for x0, y0, x1, y1 in putevi:
    kutija(bm_pp, x0, y0, 0.0, x1, y1, 0.006)
    for a, b, c, e in ((x0, y0, x1, y0 + 0.15), (x0, y1 - 0.15, x1, y1),
                       (x0, y0, x0 + 0.15, y1), (x1 - 0.15, y0, x1, y1)):
        kutija(bm_ivica, a, b, 0.006, c, e, 0.012)
objekat("Pozarni_put", bm_pp, M["pozar_pod"], K_POZAR)
objekat("Pozarni_put_ivice", bm_ivica, M["pozar"], K_POZAR)

# izlazi u nuzdi na krajevima poprecnog puta (zeleni) i hidranti pored njih
bm_izlaz = bmesh.new()
bm_hidrant = bmesh.new()
for xw, smer in ((-d, 1), (DUZINA, -1)):
    kutija(bm_izlaz, xw + d * 0.4, PP_Y - IZLAZ_SIRINA / 2, 0,
           xw + d * 0.6, PP_Y + IZLAZ_SIRINA / 2, IZLAZ_VISINA)
    xu = 0.0 if smer == 1 else DUZINA
    # znak "izlaz" iznad vrata
    kutija(bm_izlaz, xu + smer * 0.02, PP_Y - 0.4, IZLAZ_VISINA + 0.2,
           xu + smer * 0.08, PP_Y + 0.4, IZLAZ_VISINA + 0.5)
    # hidrantski orman pored vrata
    for yh in (PP_Y - IZLAZ_SIRINA / 2 - 1.2, PP_Y + IZLAZ_SIRINA / 2 + 0.4):
        kutija(bm_hidrant, xu, yh, 1.0, xu + smer * 0.25, yh + 0.8, 2.0)
# hidranti i uz zone rampi / kancelarije
for xh in (DUZINA * 0.25, DUZINA * 0.75):
    kutija(bm_hidrant, xh, SIRINA - 0.25, 1.0, xh + 0.8, SIRINA, 2.0)
objekat("Izlazi_u_nuzdi", bm_izlaz, M["izlaz"], K_POZAR)
objekat("Hidranti", bm_hidrant, M["pozar"], K_POZAR)


# ---------------------------------------------------------------- viljuskari, kamioni, ljudi
import math

K_KAMIONI = kolekcija("Kamioni")
K_LJUDI = kolekcija("Ljudi")
sc.render.fps = FPS
sc.frame_start = 1
sc.frame_end = KRAJ_ANIMACIJE

M["asfalt"] = materijal("Asfalt", (0.12, 0.12, 0.13), 0.9)
M["prikolica"] = materijal("Prikolica_cerada", (0.75, 0.78, 0.80), 0.6)
M["kabina"] = materijal("Kabina_crvena", (0.65, 0.05, 0.05), 0.3, 0.4)
M["pantalone"] = materijal("Pantalone", (0.08, 0.10, 0.20), 0.8)
M["prsluk"] = materijal("Prsluk_fluo", (0.85, 0.95, 0.10), 0.6)
M["koza"] = materijal("Koza", (0.85, 0.62, 0.48), 0.6)
M["kaciga"] = materijal("Kaciga_bela", (0.95, 0.95, 0.95), 0.4)

VILJUSKA_X = 1.67     # centar palete na viljusci, lokalno ispred viljuskara
VILJUSKA_Z = 0.10     # visina palete na viljusci kad je nosac na 0


def mesh_ob(ime, bm, mats, kol, roditelj=None):
    me = bpy.data.meshes.new(ime)
    bm.to_mesh(me)
    bm.free()
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(ime, me)
    kol.objects.link(ob)
    if roditelj:
        ob.parent = roditelj
    return ob


def kugla(bm, x, y, z, r, mi=0):
    mat = __import__("mathutils").Matrix.Translation((x, y, z))
    try:
        rez = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r, matrix=mat)
    except TypeError:   # Blender 2.9x: parametar se zove "diameter" (a znaci poluprecnik)
        rez = bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, diameter=r, matrix=mat)
    for v in rez["verts"]:
        for f in v.link_faces:
            f.material_index = mi


def paleta(ime, x, y, z=0.0, ugao=0.0, kol=None, visina_robe=None):
    """Paleta sa robom; lokalno: duza strana (1.1 m) po X, centar dna u (0,0,0)."""
    bm = bmesh.new()
    kutija(bm, -0.55, -0.40, 0.0, 0.55, 0.40, 0.15, 0)
    h = visina_robe or random.uniform(0.8, 1.3)
    kutija(bm, -0.52, -0.37, 0.15, 0.52, 0.37, 0.15 + h, 1)
    ob = mesh_ob(ime, bm, (M["paleta"], M["roba"]), kol or K_ROBA)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, math.radians(ugao))
    return ob


def viljuskar(ime, x, y, ugao, podizanje=0.0, sa_paletom=False):
    """Celni viljuskar okrenut lokalno ka +X. Vraca (telo, nosac, paleta|None).
    Nosac (viljuska + unutrasnji jarbol) je poseban objekat da bi mogao da se podize."""
    Z, G, J = 0, 1, 2
    bm = bmesh.new()
    kutija(bm, -1.2, -0.55, 0.25, 0.85, 0.55, 1.05, Z)          # sasija
    kutija(bm, -1.3, -0.58, 0.25, -0.75, 0.58, 1.35, Z)         # kontrateg
    kutija(bm, -0.55, -0.25, 1.05, -0.10, 0.25, 1.15, G)        # sediste
    kutija(bm, -0.60, -0.25, 1.15, -0.50, 0.25, 1.65, G)        # naslon
    kutija(bm, 0.35, -0.04, 1.05, 0.43, 0.04, 1.55, G)          # volan
    for sx in (-0.65, 0.65):                                    # zastitni ram
        for sy in (-0.55, 0.50):
            kutija(bm, sx, sy, 1.05, sx + 0.06, sy + 0.05, 2.15, J)
    kutija(bm, -0.68, -0.58, 2.15, 0.74, 0.58, 2.22, J)
    for tx, r in ((0.55, 0.33), (-0.90, 0.28)):                 # tockovi
        for ty in (-0.48, 0.48):
            tocak(bm, tx, ty, r, r, 0.24, G)
    for sy in (-0.40, 0.33):                                    # spoljni jarbol
        kutija(bm, 0.90, sy, 0.05, 1.00, sy + 0.07, 2.3, J)
    kutija(bm, 0.90, -0.40, 2.2, 1.00, 0.40, 2.3, J)
    telo = mesh_ob(ime, bm, (M["viljuskar"], M["guma"], M["jarbol"]), K_VILJUSKARI)
    telo.location = (x, y, 0)
    telo.rotation_euler = (0, 0, math.radians(ugao))

    bm = bmesh.new()
    for sy in (-0.32, 0.25):                                    # unutrasnji jarbol
        kutija(bm, 0.98, sy, 0.10, 1.05, sy + 0.07, 2.25, 0)
    kutija(bm, 1.05, -0.50, 0.05, 1.10, 0.50, 1.05, 0)          # nosac
    for fy in (-0.37, 0.25):                                    # viljuske
        kutija(bm, 1.10, fy, 0.05, 2.25, fy + 0.12, 0.10, 0)
    nosac = mesh_ob(ime + "_viljuska", bm, (M["jarbol"],), K_VILJUSKARI, telo)
    nosac.location = (0, 0, podizanje)

    p = None
    if sa_paletom:
        p = paleta(ime + "_paleta", VILJUSKA_X, 0, VILJUSKA_Z)
        p.rotation_euler = (0, 0, 0)
        p.parent = nosac
    return telo, nosac, p


def kljuc(ob, frejm, lok=None):
    if lok is not None:
        ob.location = lok
    ob.keyframe_insert("location", frame=frejm)


def voznja(telo, nosac, pal, ugao, tacke):
    """Animira viljuskar i paletu (paleta nije child, pa moze da ostane gde je spustena).
    tacke = [(frejm, x, y, podizanje, nosi_paletu)]"""
    ca, sa = math.cos(math.radians(ugao)), math.sin(math.radians(ugao))
    for frejm, x, y, lift, nosi in tacke:
        kljuc(telo, frejm, (x, y, 0))
        kljuc(nosac, frejm, (0, 0, lift))
        if pal is not None:
            if nosi:
                pal.location = (x + VILJUSKA_X * ca, y + VILJUSKA_X * sa, lift + VILJUSKA_Z)
            kljuc(pal, frejm)


# ---- spoljni plato (asfalt) ispred rampi
bm = bmesh.new()
kutija(bm, -15, -30, -0.25, DUZINA + 15, -DEBLJINA_ZIDA, -0.02)
objekat("Plato_asfalt", bm, M["asfalt"], K_KAMIONI)

# ---- kamioni sa prikolicom na rampama (prikolica otvorena ka hali)
DUZ_PRIK = 13.6
for n, i in enumerate(RAMPE_SA_KAMIONOM):
    xc = (otvori[i][0] + otvori[i][1]) / 2
    y0 = -DEBLJINA_ZIDA - 0.15                       # zadnji kraj prikolice uz zid
    bm = bmesh.new()
    kutija(bm, xc - 1.30, y0 - DUZ_PRIK, -0.10, xc + 1.30, y0, 0.0, 0)        # pod
    kutija(bm, xc - 1.30, y0 - DUZ_PRIK, 0.0, xc - 1.25, y0, 2.8, 0)          # bocne stranice
    kutija(bm, xc + 1.25, y0 - DUZ_PRIK, 0.0, xc + 1.30, y0, 2.8, 0)
    kutija(bm, xc - 1.30, y0 - DUZ_PRIK, 2.8, xc + 1.30, y0, 2.9, 0)          # krov
    kutija(bm, xc - 1.30, y0 - DUZ_PRIK, 0.0, xc + 1.30, y0 - DUZ_PRIK + 0.05, 2.8, 0)
    # kabina tegljaca
    yk = y0 - DUZ_PRIK - 0.4
    kutija(bm, xc - 1.25, yk - 2.3, 0.5, xc + 1.25, yk, 3.4, 1)
    kutija(bm, xc - 1.20, yk - 2.35, 1.9, xc + 1.20, yk - 2.3, 3.0, 2)        # vetrobran
    for ty in (yk - 1.6, y0 - DUZ_PRIK + 1.0, y0 - DUZ_PRIK + 2.4):
        for tx in (xc - 1.15, xc + 1.15):
            b2 = bm
            # tocak sa osom po X: valjak po Y pa rotacija nije potrebna za izgled odozgo/sa strane
            kutija(b2, tx - 0.15, ty - 0.5, -0.02, tx + 0.15, ty + 0.5, 0.98, 3)
    mesh_ob(f"Kamion_{n + 1}", bm, (M["prikolica"], M["kabina"], M["staklo"], M["guma"]), K_KAMIONI)
    # vec utovarene palete na prednjem delu prikolice (dve kolone)
    for r in range(4):
        for kx in (-0.6, 0.6):
            paleta(f"Kamion_{n + 1}_paleta_{r}_{kx > 0}", xc + kx, y0 - DUZ_PRIK + 0.7 + r * 1.15,
                   ugao=90, kol=K_KAMIONI)

# ---- utovar: viljuskar uzima paletu iz zone otpreme i vozi je u kamion
for n, i in enumerate(RAMPE_SA_KAMIONOM):
    xc = (otvori[i][0] + otvori[i][1]) / 2
    t0 = 1 + n * 50                                   # viljuskari krecu sa zakasnjenjem
    y_paleta = 7.0                                    # gde paleta ceka u zoni otpreme
    y_start = y_paleta + VILJUSKA_X + 1.5             # viljuskar stoji iza palete
    y_spust = -DEBLJINA_ZIDA - DUZ_PRIK + 0.7 + 4 * 1.15 + 0.2   # sledece slobodno mesto u prikolici
    tel, nos, _ = viljuskar(f"Viljuskar_utovar_{n + 1}", xc, y_start, -90)
    pal = paleta(f"Paleta_za_utovar_{n + 1}", xc, y_paleta, ugao=90)
    yv = lambda yp: yp + VILJUSKA_X                   # polozaj viljuskara za paletu na yp
    voznja(tel, nos, pal, -90, [
        (t0,       xc, y_start,      0.0,  False),
        (t0 + 30,  xc, yv(y_paleta), 0.0,  False),    # podvlaci viljusku
        (t0 + 45,  xc, yv(y_paleta), 0.15, True),     # podize paletu
        (t0 + 190, xc, yv(y_spust),  0.15, True),     # vozi u prikolicu
        (t0 + 205, xc, yv(y_spust),  0.0,  True),     # spusta paletu
        (t0 + 215, xc, yv(y_spust),  0.0,  False),
        (t0 + 360, xc, y_start,      0.0,  False),    # vraca se po sledecu
    ])
    # palete koje cekaju na otpremu pored
    for k in range(3):
        paleta(f"Otprema_{n + 1}_{k}", xc + 2.4, 4.0 + k * 1.3, ugao=90)

# ---- viljuskari u prolazima
prolazi = []
for (ra, da), (rb, _) in zip(redovi, redovi[1:]):
    prolazi.append((ra + da * DUBINA + rb) / 2)

# 1) vozi paletu duz prolaza i nazad
tel, nos, pal = viljuskar("Viljuskar_prolaz_1", prolazi[0], 13.0, 90, 0.1, True)
voznja(tel, nos, None, 90, [(1, prolazi[0], 13.0, 0.1, True), (220, prolazi[0], 33.0, 0.1, True),
                           (260, prolazi[0], 33.0, 0.1, True), (KRAJ_ANIMACIJE, prolazi[0], 13.0, 0.1, True)])

# 2) odlaze paletu na 3. nivo regala (podigne, ugura, spusti, izvuce se, spusti viljusku)
xa = prolazi[2] - 0.3
tel, nos, _ = viljuskar("Viljuskar_regal_1", xa, 28.8, 0, 0.1)
pal = paleta("Paleta_na_regal", xa + VILJUSKA_X, 28.8, VILJUSKA_Z + 0.1, ugao=0)
z3 = NIVOI[3] - VILJUSKA_Z + 0.08
voznja(tel, nos, pal, 0, [
    (1,   xa,       28.8, 0.1,         True),
    (120, xa,       28.8, z3,          True),     # podizanje
    (170, xa + 1.2, 28.8, z3,          True),     # ulazak u regal
    (185, xa + 1.2, 28.8, z3 - 0.08,   True),     # spustanje na grede
    (190, xa + 1.2, 28.8, z3 - 0.08,   False),
    (240, xa,       28.8, z3 - 0.08,   False),    # izvlacenje
    (330, xa,       28.8, 0.1,         False),    # spustanje viljuske
])

# 3) prazan viljuskar se vozi kroz prolaz
tel, nos, _ = viljuskar("Viljuskar_prolaz_2", prolazi[4], 36.0, -90, 0.1)
voznja(tel, nos, None, -90, [(1, prolazi[4], 36.0, 0.1, False), (60, prolazi[4], 36.0, 0.1, False),
                            (300, prolazi[4], 14.0, 0.1, False), (KRAJ_ANIMACIJE, prolazi[4], 14.0, 0.1, False)])

# 4) skida paletu sa 2. nivoa i spusta je na pod
xb = prolazi[6] - 0.9
tel, nos, _ = viljuskar("Viljuskar_regal_2", xb, 16.7, 180, NIVOI[1] - VILJUSKA_Z - 0.05)
pal = paleta("Paleta_sa_regala", xb - VILJUSKA_X, 16.7, NIVOI[1], ugao=180)
z2 = NIVOI[1] - VILJUSKA_Z
voznja(tel, nos, pal, 180, [
    (100, xb,       16.7, z2 - 0.05, False),
    (115, xb,       16.7, z2 + 0.05, True),       # podize paletu sa greda
    (175, xb + 1.2, 16.7, z2 + 0.05, True),       # izvlaci je iz regala
    (280, xb + 1.2, 16.7, 0.1,       True),       # spusta je
])

# parking viljuskara kod punjaca (pored kancelarije)
for i in range(3):
    viljuskar(f"Viljuskar_parking_{i + 1}", 2.0 + i * 1.6, ky0 - 3.0, 90)


# ---- ljudi koji rade popis (skener u ruci, hodaju od polja do polja)
def covek(ime, x, y, ugao, alat="skener"):
    """Radnik okrenut lokalno ka +X, visok ~1.8 m. alat: skener | tablet."""
    P, V, K, H, A = 0, 1, 2, 3, 4
    bm = bmesh.new()
    for ly in (-0.17, 0.03):                                    # noge
        kutija(bm, -0.08, ly, 0.0, 0.08, ly + 0.14, 0.85, P)
    kutija(bm, -0.12, -0.22, 0.85, 0.12, 0.22, 1.45, V)         # trup (fluo prsluk)
    kutija(bm, -0.06, -0.06, 1.45, 0.06, 0.06, 1.52, K)         # vrat
    kugla(bm, 0.0, 0.0, 1.63, 0.12, K)                          # glava
    kutija(bm, -0.13, -0.13, 1.70, 0.13, 0.13, 1.80, H)         # kaciga
    kutija(bm, -0.06, -0.31, 0.80, 0.06, -0.22, 1.42, V)        # leva ruka niz telo
    kutija(bm, -0.05, 0.22, 1.25, 0.40, 0.31, 1.40, V)          # desna ruka ispruzena napred
    kutija(bm, 0.40, 0.23, 1.27, 0.48, 0.30, 1.36, K)           # saka
    if alat == "skener":
        kutija(bm, 0.42, 0.24, 1.36, 0.60, 0.29, 1.42, A)
    else:   # tablet drzi ispred sebe
        kutija(bm, 0.30, 0.0, 1.20, 0.33, 0.30, 1.42, A)
    ob = mesh_ob(ime, bm, (M["pantalone"], M["prsluk"], M["koza"], M["kaciga"], M["guma"]), K_LJUDI)
    ob.location = (x, y, 0)
    ob.rotation_euler = (0, 0, math.radians(ugao))
    return ob


def popis(ob, x, y_od, polja, smer, t0=1):
    """Radnik ide od polja do polja (POLJE m), na svakom stoji i skenira."""
    t = t0
    y = y_od
    for k in range(polja):
        kljuc(ob, t, (x, y, 0))
        t += 40                                          # skenira
        kljuc(ob, t, (x, y, 0))
        y += smer * POLJE
        t += 30                                          # prelazi do sledeceg polja
    kljuc(ob, t, (x, y, 0))


# u prolazima bez viljuskara; radnik stoji 1.2 m od regala, okrenut ka njemu
for n, (pi, ugao_c, y0, smer) in enumerate(((1, 0, 13.5, 1), (3, 180, 36.5, -1), (5, 0, 28.5, 1))):
    xr = prolazi[pi] + (0.8 if ugao_c == 0 else -0.8)
    popis(covek(f"Radnik_popis_{n + 1}", xr, y0, ugao_c), xr, y0, 3, smer, 1 + n * 25)
# kontrolor sa tabletom u zoni otpreme
covek("Radnik_otprema_tablet", otvori[2][1] + 1.5, 5.0, 180, "tablet")
covek("Radnik_otprema_2", otvori[1][1] + 1.6, 3.0, 135, "skener")


# ---------------------------------------------------------------- svetla
for i in range(5):
    for j in range(4):
        ld = bpy.data.lights.new(f"Svetlo_{i}_{j}", 'AREA')
        ld.energy = 2500
        ld.size = 2.0
        lo = bpy.data.objects.new(ld.name, ld)
        lo.location = (DUZINA * (i + 0.5) / 5, SIRINA * (j + 0.5) / 4, VISINA - 0.3)
        K_PRIKAZ.objects.link(lo)

sun = bpy.data.lights.new("Sunce", 'SUN')
sun.energy = 3.0
so = bpy.data.objects.new("Sunce", sun)
so.rotation_euler = (0.8, 0.2, 0.6)
K_PRIKAZ.objects.link(so)

world = sc.world or bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.65, 0.80, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6

# ---------------------------------------------------------------- kamera
cd = bpy.data.cameras.new("Kamera")
cd.lens = 24
cd.clip_end = 500
co = bpy.data.objects.new("Kamera", cd)
co.location = (DUZINA + 22, -22, 38)
K_PRIKAZ.objects.link(co)
cil = bpy.data.objects.new("Kamera_cilj", None)
cil.location = (DUZINA / 2, SIRINA / 2, 0)
K_PRIKAZ.objects.link(cil)
tr = co.constraints.new('TRACK_TO')
tr.target = cil
tr.track_axis = 'TRACK_NEGATIVE_Z'
tr.up_axis = 'UP_Y'
sc.camera = co

sc.render.engine = 'CYCLES'
sc.cycles.device = 'CPU'
sc.cycles.samples = 32
sc.render.resolution_x = 1280
sc.render.resolution_y = 720

# viewport: pomeri pogled i približi magacin (kad se skripta pokrene u Blenderu)
if bpy.context.screen:
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces.active
            sp.clip_end = 1000
            sp.shading.type = 'SOLID'
            sp.shading.color_type = 'MATERIAL'
            r3d = sp.region_3d
            r3d.view_location = (DUZINA / 2, SIRINA / 2, 0)
            r3d.view_distance = 110

print(f"Magacin {DUZINA:.0f} x {SIRINA:.0f} m = {DUZINA*SIRINA:.0f} m2, visina {VISINA:.0f} m")
print(f"Redova regala: {sum(dub for _, dub in redovi)}, polja po redu: {broj_polja}")
print(f"Paletnih mesta: {mesta}, zauzeto: {zauzeto}")

# ---------------------------------------------------------------- snimanje (samo u -b modu)
if bpy.app.background:
    folder = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, "magacin.blend"))
