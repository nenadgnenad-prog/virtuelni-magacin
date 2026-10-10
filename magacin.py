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
import json
import math
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
KRAJ_ANIMACIJE = 900             # 36 s animacije (Space u Blenderu pusta animaciju)

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


def materijal(ime, boja, hrapavost=0.6, metal=0.0, alpha=1.0, emisija=0.0):
    m = bpy.data.materials.new(ime)
    m.use_nodes = True
    bsdf = m.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*boja, 1.0)
    bsdf.inputs["Roughness"].default_value = hrapavost
    bsdf.inputs["Metallic"].default_value = metal
    if emisija > 0:   # svetli sam (farovi); "Emission Color" je ime u Blenderu 4+
        ulaz = "Emission" if "Emission" in bsdf.inputs else "Emission Color"
        bsdf.inputs[ulaz].default_value = (*boja, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emisija
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


def tocak(bm, x, y, z, r, sirina, mi=0, segmenti=16, osa='Y'):
    """Valjak (tocak) sa osom po Y (ili po X za osa='X'), centar (x, y, z)."""
    prsten = []
    for s in (-sirina / 2, sirina / 2):
        krug = [(r * math.cos(2 * math.pi * i / segmenti), r * math.sin(2 * math.pi * i / segmenti))
                for i in range(segmenti)]
        if osa == 'X':
            prsten.append([bm.verts.new((x + s, y + c, z + e)) for c, e in krug])
        else:
            prsten.append([bm.verts.new((x + c, y + s, z + e)) for c, e in krug])
    a, b = prsten
    for i in range(segmenti):
        j = (i + 1) % segmenti
        bm.faces.new((a[i], a[j], b[j], b[i])).material_index = mi
    bm.faces.new(list(reversed(a))).material_index = mi
    bm.faces.new(b).material_index = mi


def objekat(ime, bm, mat, kol):
    """mat = jedan materijal ili lista (indeksi odgovaraju 'mi' u kutija())."""
    me = bpy.data.meshes.new(ime)
    bm.to_mesh(me)
    bm.free()
    for m in (mat if isinstance(mat, (list, tuple)) else (mat,)):
        me.materials.append(m)
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
    "tabla": materijal("Oznaka_tabla", (0.04, 0.16, 0.42), 0.5),
    "slovo": materijal("Oznaka_slovo", (0.98, 0.98, 0.98), 0.4),
}

# roba u vise boja: kartoni razlicitih nijansi, roba u foliji, poneka obojena ambalaza
# (poseban generator, da raspored zauzetih mesta ostane isti kao sa random.seed(42))
ROBA = [
    (M["roba"], 30),
    (materijal("Roba_karton_tamni", (0.52, 0.36, 0.20), 0.85), 22),
    (materijal("Roba_karton_svetli", (0.82, 0.70, 0.50), 0.8), 18),
    (materijal("Roba_folija_bela", (0.88, 0.90, 0.92), 0.25), 12),
    (materijal("Roba_folija_plava", (0.25, 0.45, 0.75), 0.3), 8),
    (materijal("Roba_crvena", (0.70, 0.12, 0.10), 0.6), 5),
    (materijal("Roba_zelena", (0.20, 0.50, 0.25), 0.6), 5),
]
ROBA_MAT = [m for m, _ in ROBA]
ROBA_TEZINE = [t for _, t in ROBA]
rnd_boja = random.Random(7)


def boja_robe():
    """Indeks u ROBA_MAT po tezinama."""
    return rnd_boja.choices(range(len(ROBA_MAT)), ROBA_TEZINE)[0]

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

# svaki red regala (jedna dubina) dobija slovo A, B, C... od zapada ka istoku
SLOVA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
prvi_red = []            # indeks slova za prvu dubinu svakog elementa iz 'redovi'
n_redova = 0
for _, dub in redovi:
    prvi_red.append(n_redova)
    n_redova += dub
stat_reda = [{"red": SLOVA[i], "mesta": 0, "zauzeto": 0} for i in range(n_redova)]

bm_stub, bm_greda, bm_paleta, bm_roba = (bmesh.new() for _ in range(4))
s = 0.09   # presek stuba
mesta = 0
zauzeto = 0
prazna = []         # slobodna paletna mesta (za animaciju)
for (by0, by1), (ri, (rx, dubine)) in [(b, r) for b in blokovi for r in enumerate(redovi)]:
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
                    st = stat_reda[prvi_red[ri] + k]
                    st["mesta"] += 1
                    py0 = ya + 0.15 + p * 1.25
                    px0 = x0 + 0.05
                    if random.random() > POPUNJENOST:
                        # slobodno mesto - viljuskari u animaciji odlazu palete na ovakva mesta
                        prazna.append(dict(ri=ri, k=k, x0=x0, cx=px0 + 0.5, cy=py0 + 0.4,
                                           z=z, nivo=NIVOI.index(z)))
                        continue
                    zauzeto += 1
                    st["zauzeto"] += 1
                    kutija(bm_paleta, px0, py0, z, px0 + DUBINA - 0.1, py0 + 0.8, z + 0.15)
                    h = random.uniform(0.8, 1.5)
                    kutija(bm_roba, px0 + 0.03, py0 + 0.03, z + 0.15,
                           px0 + DUBINA - 0.13, py0 + 0.77, z + 0.15 + h, boja_robe())

objekat("Regali_stubovi", bm_stub, M["stub"], K_REGALI)
objekat("Regali_grede", bm_greda, M["greda"], K_REGALI)
objekat("Palete", bm_paleta, M["paleta"], K_ROBA)
objekat("Roba", bm_roba, ROBA_MAT, K_ROBA)

# ---------------------------------------------------------------- oznake redova
# tabla sa slovom na vrhu svakog reda, na oba kraja (vidi se iz zone prijema i sa severa)
K_OZNAKE = kolekcija("Oznake_redova")
TABLA_Z0, TABLA_Z1 = VISINA_REGALA + 0.15, VISINA_REGALA + 1.15


def tekst_u_mesh(ime, tekst, velicina, lok, rot_z, mat, kol):
    """Pravi 3D tekst i pretvara ga u mesh (da bi se izvezao i u .glb)."""
    cu = bpy.data.curves.new(ime, 'FONT')
    cu.body = tekst
    cu.size = velicina
    cu.extrude = 0.015
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    privremeni = bpy.data.objects.new(ime + "_tmp", cu)
    kol.objects.link(privremeni)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(privremeni.evaluated_get(dg))
    bpy.data.objects.remove(privremeni)
    bpy.data.curves.remove(cu)
    me.name = ime
    me.materials.append(mat)
    ob = bpy.data.objects.new(ime, me)
    ob.location = lok
    ob.rotation_euler = (math.radians(90), 0, math.radians(rot_z))
    kol.objects.link(ob)
    return ob


bm_table = bmesh.new()
oznake_redova = []        # za web prikaz (info tacke)
for ri, (rx, dubine) in enumerate(redovi):
    for k in range(dubine):
        st = stat_reda[prvi_red[ri] + k]
        x0 = rx + k * DUBINA
        xc = x0 + DUBINA / 2
        for yk, smer in ((REGAL_Y0, -1), (REGAL_Y1, 1)):
            # tabla 1 m siroka, malo isturena ispred cela reda
            yt = yk + smer * 0.05
            kutija(bm_table, x0 + 0.04, yt - 0.03, TABLA_Z0, x0 + DUBINA - 0.04, yt + 0.03, TABLA_Z1)
            # slovo okrenuto ka spolja (jug: gleda ka -Y, sever: ka +Y)
            tekst_u_mesh(f"Oznaka_{st['red']}_{'jug' if smer < 0 else 'sever'}", st["red"], 0.8,
                         (xc, yt + smer * 0.035, (TABLA_Z0 + TABLA_Z1) / 2),
                         0 if smer < 0 else 180, M["slovo"], K_OZNAKE)
        oznake_redova.append(dict(st, x=xc, y=REGAL_Y0 - 0.3, z=TABLA_Z1 + 0.3))
objekat("Oznake_table", bm_table, M["tabla"], K_OZNAKE)

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
M["felna"] = materijal("Felna_hrom", (0.75, 0.76, 0.78), 0.25, 0.9)
M["far"] = materijal("Far_svetlo", (1.0, 0.95, 0.80), 0.2, 0.0, 1.0, 25.0)
M["stop"] = materijal("Stop_svetlo", (0.9, 0.05, 0.02), 0.3, 0.0, 1.0, 6.0)
M["migavac"] = materijal("Migavac_narandzasti", (1.0, 0.45, 0.02), 0.3, 0.0, 1.0, 4.0)

VILJUSKA_X = 1.67     # centar palete na viljusci, lokalno ispred viljuskara
KORAK = 3             # kljucevi animacije na svaka 3 frejma (izmedju je linearno)


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
    ob = mesh_ob(ime, bm, (M["paleta"], ROBA_MAT[boja_robe()]), kol or K_ROBA)
    ob.location = (x, y, z)
    ob.rotation_euler = (0, 0, math.radians(ugao))
    return ob


def vozac(ime, roditelj):
    """Vozac koji sedi u viljuskaru (dete tela viljuskara, krece se sa njim)."""
    P, V, K, H = 0, 1, 2, 3
    bm = bmesh.new()
    kutija(bm, -0.48, -0.20, 1.15, 0.0, 0.20, 1.30, P)          # butine na sedistu
    for sy in (-0.20, 0.04):                                    # potkolenice ka pedalama
        kutija(bm, 0.0, sy, 1.05, 0.13, sy + 0.16, 1.30, P)
    kutija(bm, -0.50, -0.21, 1.30, -0.26, 0.21, 1.85, V)        # trup (fluo prsluk)
    kugla(bm, -0.37, 0.0, 1.97, 0.11, K)                        # glava
    kutija(bm, -0.49, -0.12, 2.03, -0.25, 0.12, 2.11, H)        # kaciga
    for sy in (-0.25, 0.18):                                    # ruke na volanu
        kutija(bm, -0.40, sy, 1.50, 0.36, sy + 0.07, 1.59, V)
    mesh_ob(ime, bm, (M["pantalone"], M["prsluk"], M["koza"], M["kaciga"]), K_VILJUSKARI, roditelj)


def viljuskar(ime, x, y, ugao, podizanje=0.0, sa_vozacem=True):
    """Celni viljuskar okrenut lokalno ka +X. Vraca (telo, nosac).
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
    kutija(bm, -0.20, -0.06, 2.22, -0.08, 0.06, 2.30, J)        # rotaciona lampa (postolje)
    telo = mesh_ob(ime, bm, (M["viljuskar"], M["guma"], M["jarbol"]), K_VILJUSKARI)
    telo.location = (x, y, 0)
    telo.rotation_euler = (0, 0, math.radians(ugao))
    if sa_vozacem:
        vozac(ime + "_vozac", telo)
        bm = bmesh.new()
        kutija(bm, -0.19, -0.05, 2.30, -0.09, 0.05, 2.38, 0)    # narandzasta lampa (svetli)
        mesh_ob(ime + "_lampa", bm, (M["migavac"],), K_VILJUSKARI, telo)

    bm = bmesh.new()
    for sy in (-0.32, 0.25):                                    # unutrasnji jarbol
        kutija(bm, 0.98, sy, 0.10, 1.05, sy + 0.07, 2.25, 0)
    kutija(bm, 1.05, -0.50, 0.05, 1.10, 0.50, 1.05, 0)          # nosac
    for fy in (-0.37, 0.25):                                    # viljuske
        kutija(bm, 1.10, fy, 0.05, 2.25, fy + 0.12, 0.10, 0)
    nosac = mesh_ob(ime + "_viljuska", bm, (M["jarbol"],), K_VILJUSKARI, telo)
    nosac.location = (0, 0, podizanje)
    return telo, nosac


def ease(u):
    """Glatko kretanje: polako krene, ubrza, pa uspori pred kraj."""
    return u * u * (3 - 2 * u)


def kljucevi(t, ob, *svojstva):
    for s in svojstva:
        ob.keyframe_insert(s, frame=t)


class Viljuskar:
    """Viljuskar koji izvrsava niz radnji (vozi, okreni, podigni, uzmi, ostavi...).
    Kljucevi se postavljaju na svakih KORAK frejmova, pa paleta na viljusci
    uvek prati viljuskar - i dok skrece. Paleta je na visini viljuske (nosac.z)."""
    BRZINA = 2.2 / FPS         # m po frejmu
    DIZANJE = 0.8 / FPS        # m po frejmu
    OKRET = 90 / 22            # stepeni po frejmu

    def __init__(self, ime, x, y, u, t0=1, lift=0.15):
        self.telo, self.nosac = viljuskar(ime, x, y, u, lift)
        self.x, self.y, self.u, self.lift = x, y, u, lift
        self.pal = None
        self.t = t0
        self._kljuc(1)
        if t0 > 1:
            self._kljuc(t0)

    def _kljuc(self, t):
        self.telo.location = (self.x, self.y, 0)
        self.telo.rotation_euler = (0, 0, math.radians(self.u))
        self.nosac.location = (0, 0, self.lift)
        kljucevi(t, self.telo, "location", "rotation_euler")
        kljucevi(t, self.nosac, "location")
        if self.pal:
            a = math.radians(self.u)
            self.pal.location = (self.x + VILJUSKA_X * math.cos(a),
                                 self.y + VILJUSKA_X * math.sin(a), self.lift)
            self.pal.rotation_euler = (0, 0, a)
            kljucevi(t, self.pal, "location", "rotation_euler")

    def _prelaz(self, trajanje, **cilj):
        poc = {k: getattr(self, k) for k in cilj}
        n = max(KORAK, int(math.ceil(trajanje)))
        for f in list(range(KORAK, n, KORAK)) + [n]:
            e = ease(f / n)
            for k, v in cilj.items():
                setattr(self, k, poc[k] + (v - poc[k]) * e)
            self._kljuc(self.t + f)
        self.t += n
        return self

    def vozi(self, x, y):
        """Pravo (napred ili u rikverc) do tacke (x, y), bez okretanja."""
        return self._prelaz(math.hypot(x - self.x, y - self.y) / self.BRZINA + 8, x=x, y=y)

    def okreni(self, u):
        return self._prelaz(abs(u - self.u) / self.OKRET + 4, u=u)

    def podigni(self, lift):
        return self._prelaz(abs(lift - self.lift) / self.DIZANJE + 6, lift=lift)

    def cekaj(self, n):
        self.t += n
        self._kljuc(self.t)
        return self

    def uzmi(self, pal):
        """Paleta stoji na svom mestu do ovog trenutka, posle ide sa viljuskom."""
        kljucevi(1, pal, "location", "rotation_euler")
        kljucevi(self.t, pal, "location", "rotation_euler")
        self.pal = pal
        return self

    def ostavi(self):
        self.pal = None
        return self


# ---- spoljni plato (asfalt) ispred rampi
bm = bmesh.new()
kutija(bm, -15, -30, -0.25, DUZINA + 15, -DEBLJINA_ZIDA, -0.02)
objekat("Plato_asfalt", bm, M["asfalt"], K_KAMIONI)

# ---- kamioni sa prikolicom na rampama (prikolica otvorena ka hali)
DUZ_PRIK = 13.6
UTOVARENO_REDOVA = 8                                  # redova paleta vec u prikolici
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
    yp = yk - 2.3                                                             # prednja strana kabine
    kutija(bm, xc - 1.28, yp - 0.14, 0.42, xc + 1.28, yp + 0.02, 0.70, 3)     # branik
    kutija(bm, xc - 0.60, yp - 0.04, 0.80, xc + 0.60, yp + 0.01, 1.70, 3)     # maska hladnjaka
    for sx in (-1, 1):
        kutija(bm, xc + sx * 0.72, yp - 0.06, 0.78, xc + sx * 1.12, yp + 0.01, 1.00, 5)   # far
        kutija(bm, xc + sx * 1.14, yp - 0.06, 0.78, xc + sx * 1.25, yp + 0.01, 1.00, 7)   # migavac
        # bocna markirna svetla duz prikolice
        for ym in range(1, 5):
            yy = y0 - DUZ_PRIK + ym * DUZ_PRIK / 5
            kutija(bm, xc + sx * 1.30, yy - 0.06, 0.15, xc + sx * 1.33, yy + 0.06, 0.25, 7)
    # tockovi: guma + felna, osa po X (popreko na pravac kamiona)
    for ty in (yk - 1.6, yk + 0.5, y0 - 2.0, y0 - 3.1, y0 - 4.2):   # tegljac 2 osovine, prikolica 3
        for sx in (-1, 1):
            tx = xc + sx * 1.42
            tocak(bm, tx, ty, 0.48, 0.50, 0.30, 3, 20, 'X')
            tocak(bm, tx, ty, 0.48, 0.28, 0.32, 4, 12, 'X')
    mesh_ob(f"Kamion_{n + 1}", bm, (M["prikolica"], M["kabina"], M["staklo"], M["guma"],
                                     M["felna"], M["far"], M["stop"], M["migavac"]), K_KAMIONI)
    # vec utovarene palete od prednjeg dela prikolice (dve kolone)
    for r in range(UTOVARENO_REDOVA):
        for kx in (-0.6, 0.6):
            paleta(f"Kamion_{n + 1}_paleta_{r}_{kx > 0}", xc + kx, y0 - DUZ_PRIK + 0.7 + r * 1.15,
                   ugao=90, kol=K_KAMIONI)

# ---- utovar: svaki viljuskar 2 puta uzme paletu iz zone otpreme (sa strane),
#      okrene se, uveze je u prikolicu i spusti u sledece slobodno mesto
y_slot = -DEBLJINA_ZIDA - 0.15 - DUZ_PRIK + 0.7 + UTOVARENO_REDOVA * 1.15
for n, i in enumerate(RAMPE_SA_KAMIONOM):
    xc = (otvori[i][0] + otvori[i][1]) / 2
    v = Viljuskar(f"Viljuskar_utovar_{n + 1}", xc, 8.8, -90, t0=1 + n * 35)
    for k, (ys, kol_x) in enumerate(((6.4, -0.6), (4.0, 0.6))):
        pal = paleta(f"Paleta_za_utovar_{n + 1}_{k + 1}", xc + 1.0 + VILJUSKA_X, ys, ugao=0)
        (v.vozi(xc, ys).okreni(0).podigni(0.0)
          .vozi(xc + 1.0, ys).uzmi(pal).podigni(0.15)            # podvuce viljusku i podigne
          .vozi(xc, ys).okreni(-90)                              # izadje u rikverc i okrene se
          .vozi(xc, 0.8).vozi(xc + kol_x, y_slot + VILJUSKA_X)   # kroz rampu u prikolicu
          .podigni(0.0).ostavi().cekaj(5)
          .vozi(xc, 0.8).podigni(0.15))                          # izlazi iz prikolice
    # jos paleta koje cekaju na otpremu
    for k in range(2):
        paleta(f"Otprema_{n + 1}_{k}", xc + 4.2, 3.5 + k * 1.3, ugao=90)

# ---- viljuskari u prolazima
prolazi = []
for (ra, da), (rb, _) in zip(redovi, redovi[1:]):
    prolazi.append((ra + da * DUBINA + rb) / 2)


def slobodno_mesto(a, nivo, y_oko):
    """Slobodno mesto na zadatom nivou u regalu uz prolaz a, najblize y_oko.
    Vraca (mesto, ugao viljuskara ka regalu, smer po X)."""
    kand = [s for s in prazna if s["nivo"] == nivo and (
        (s["ri"] == a and s["k"] == redovi[a][1] - 1) or (s["ri"] == a + 1 and s["k"] == 0))]
    s = min(kand, key=lambda s: abs(s["cy"] - y_oko))
    prazna.remove(s)
    return (s, 0, 1) if s["ri"] == a + 1 else (s, 180, -1)


def odlaganje(ime, a, nivo, y_oko, t0):
    """Uzme paletu iz zone prijema, odveze je kroz prolaz a i odlozi na slobodno mesto."""
    ax = prolazi[a]
    s, u, sg = slobodno_mesto(a, nivo, y_oko)
    kraj = s["cx"] - sg * VILJUSKA_X           # polozaj viljuskara kad je paleta na mestu
    pal = paleta(ime + "_paleta", ax, 6.73 + 1.0 + VILJUSKA_X, ugao=90, visina_robe=1.2)
    v = Viljuskar(ime, ax, 6.73, 90, t0)
    (v.podigni(0.0).vozi(ax, 7.73).uzmi(pal).podigni(0.15)
      .vozi(ax, s["cy"]).okreni(u).vozi(kraj - sg * 1.2, s["cy"])
      .podigni(s["z"] + 0.1).vozi(kraj, s["cy"])             # uvuce paletu iznad greda
      .podigni(s["z"]).ostavi().cekaj(6)                      # spusti je na grede
      .vozi(kraj - sg * 1.2, s["cy"]).podigni(0.15)
      .okreni(u - 90 if u == 0 else u + 90).vozi(ax, 6.0))


def skidanje(ime, a, nivo, y_oko, t0):
    """Skine paletu sa regala uz prolaz a i odveze je u zonu otpreme."""
    ax = prolazi[a]
    s, u, sg = slobodno_mesto(a, nivo, y_oko)
    kraj = s["cx"] - sg * VILJUSKA_X
    pal = paleta(ime + "_paleta", s["cx"], s["cy"], s["z"], ugao=u, visina_robe=1.1)
    v = Viljuskar(ime, ax, 14.0, 90, t0)
    (v.vozi(ax, s["cy"]).okreni(u).vozi(kraj - sg * 1.2, s["cy"])
      .podigni(s["z"]).vozi(kraj, s["cy"]).uzmi(pal)          # podvuce viljusku ispod palete
      .podigni(s["z"] + 0.1).vozi(kraj - sg * 1.2, s["cy"])   # podigne je i izvuce
      .podigni(0.15).okreni(u - 90 if u == 0 else u + 90)
      .vozi(ax, 9.6).podigni(0.0).ostavi().cekaj(5).vozi(ax, 11.5))


odlaganje("Viljuskar_regal_1", 1, 2, 17.0, 20)
odlaganje("Viljuskar_regal_2", 4, 3, 14.0, 1)
skidanje("Viljuskar_regal_3", 3, 1, 30.0, 30)

# parking viljuskara kod punjaca (pored kancelarije) - bez vozaca
for i in range(3):
    viljuskar(f"Viljuskar_parking_{i + 1}", 2.0 + i * 1.6, ky0 - 3.0, 90, sa_vozacem=False)


# ---- radnici: noge i ruke se njisu dok hodaju
def covek(ime, x, y, ugao, alat="skener"):
    """Radnik okrenut lokalno ka +X, visok ~1.8 m. Noge i slobodne ruke su posebni objekti
    (deca tela) sa osloncem u kuku / ramenu, da bi se njihale pri hodu.
    alat: skener | tablet | paletar | folija | prazno. Vraca (telo, noge, ruke)."""
    P, V, K, H, A = 0, 1, 2, 3, 4
    bm = bmesh.new()
    kutija(bm, -0.10, -0.19, 0.80, 0.10, 0.19, 0.92, P)         # karlica
    kutija(bm, -0.12, -0.22, 0.92, 0.12, 0.22, 1.45, V)         # trup (fluo prsluk)
    kutija(bm, -0.06, -0.06, 1.45, 0.06, 0.06, 1.52, K)         # vrat
    kugla(bm, 0.0, 0.0, 1.63, 0.12, K)                          # glava
    kutija(bm, -0.13, -0.13, 1.70, 0.13, 0.13, 1.80, H)         # kaciga

    def ruka_napred(sy, do_x=0.40, z=1.25):
        kutija(bm, -0.05, sy - 0.045, z, do_x, sy + 0.045, z + 0.14, V)
        kutija(bm, do_x, sy - 0.035, z + 0.02, do_x + 0.08, sy + 0.035, z + 0.11, K)

    slobodne = []                   # ruke (strana po Y) koje se njisu
    if alat == "skener":
        ruka_napred(0.265)
        kutija(bm, 0.42, 0.24, 1.36, 0.60, 0.29, 1.42, A)
        slobodne = [-0.265]
    elif alat == "tablet":
        for sy in (-0.265, 0.265):
            ruka_napred(sy, 0.28, 1.12)
        kutija(bm, 0.30, -0.20, 1.18, 0.33, 0.20, 1.45, A)
    elif alat == "paletar":
        for sy in (-0.265, 0.265):
            ruka_napred(sy, 0.48, 0.98)
    elif alat == "folija":
        for sy in (-0.265, 0.265):
            ruka_napred(sy, 0.32, 1.02)
        kutija(bm, 0.40, -0.16, 0.92, 0.52, 0.16, 1.30, H)      # rolna stretch folije
    else:
        slobodne = [-0.265, 0.265]
    telo = mesh_ob(ime, bm, (M["pantalone"], M["prsluk"], M["koza"], M["kaciga"], M["guma"]), K_LJUDI)
    telo.location = (x, y, 0)
    telo.rotation_euler = (0, 0, math.radians(ugao))

    noge = []
    for ly in (-0.10, 0.10):
        b = bmesh.new()
        kutija(b, -0.08, -0.07, -0.85, 0.08, 0.07, 0.0, 0)
        kutija(b, -0.08, -0.07, -0.85, 0.17, 0.07, -0.77, 1)    # cipela
        nog = mesh_ob(f"{ime}_noga", b, (M["pantalone"], M["guma"]), K_LJUDI, telo)
        nog.location = (0, ly, 0.85)
        noge.append(nog)
    ruke = []
    for sy in slobodne:
        b = bmesh.new()
        kutija(b, -0.05, -0.045, -0.55, 0.05, 0.045, 0.0, 0)
        kutija(b, -0.04, -0.035, -0.64, 0.04, 0.035, -0.55, 1)  # saka
        r = mesh_ob(f"{ime}_ruka", b, (M["prsluk"], M["koza"]), K_LJUDI, telo)
        r.location = (0, sy, 1.42)
        ruke.append(r)
    return telo, noge, ruke


class Osoba:
    """Radnik koji hoda od tacke do tacke (prvo se okrene ka cilju), stoji, nosi kutiju..."""
    BRZINA = 1.25 / FPS        # m po frejmu
    KORAK_M = 0.7              # duzina koraka (m)

    def __init__(self, ime, x, y, u, alat="skener", t0=1):
        self.telo, self.noge, self.ruke = covek(ime, x, y, u, alat)
        self.x, self.y, self.u = x, y, u
        self.faza = 0.0
        self.nosi = False
        self.t = t0
        self._kljuc(1, False)
        if t0 > 1:
            self._kljuc(t0, False)

    def _kljuc(self, t, hoda):
        self.telo.location = (self.x, self.y, 0)
        self.telo.rotation_euler = (0, 0, math.radians(self.u))
        kljucevi(t, self.telo, "location", "rotation_euler")
        s = math.sin(self.faza) if hoda else 0.0
        for nog, strana in zip(self.noge, (1, -1)):
            nog.rotation_euler = (0, 0.42 * s * strana, 0)
            kljucevi(t, nog, "rotation_euler")
        for r in self.ruke:          # ruka se njise suprotno od noge na istoj strani
            strana = 1 if r.location.y < 0 else -1
            r.rotation_euler = (0, -1.25 if self.nosi else -0.35 * s * strana, 0)
            kljucevi(t, r, "rotation_euler")

    def okreni(self, u):
        d = (u - self.u + 180) % 360 - 180          # najkraci smer okretanja
        if abs(d) < 1:
            return self
        u0 = self.u
        n = max(KORAK, int(abs(d) / 12) + 3)
        for f in list(range(KORAK, n, KORAK)) + [n]:
            self.u = u0 + d * ease(f / n)
            self._kljuc(self.t + f, False)
        self.t += n
        return self

    def idi(self, x, y):
        self.okreni(math.degrees(math.atan2(y - self.y, x - self.x)))
        x0, y0, f0 = self.x, self.y, self.faza
        d = math.hypot(x - x0, y - y0)
        n = max(KORAK, int(d / self.BRZINA))
        for f in list(range(KORAK, n, KORAK)) + [n]:
            u = f / n
            self.x, self.y = x0 + (x - x0) * u, y0 + (y - y0) * u
            self.faza = f0 + math.pi * d * u / self.KORAK_M
            self._kljuc(self.t + f, f != n)
        self.faza = 0.0
        self.t += n
        return self

    def stoj(self, n):
        self.t += n
        self._kljuc(self.t, False)
        return self

    def uzmi_kutiju(self, kut):
        """Kutija (dete tela, skala 0) se pojavi u rukama."""
        kut.scale = (0, 0, 0)
        kljucevi(1, kut, "scale")
        kljucevi(self.t + 4, kut, "scale")
        kut.scale = (1, 1, 1)
        kljucevi(self.t + 8, kut, "scale")
        self._kljuc(self.t, False)
        self.nosi = True
        return self.stoj(10)

    def ostavi_kutiju(self, kut, ostavljena):
        """Kutija nestane iz ruku, a ista takva se pojavi na mestu gde je spustena."""
        kljucevi(self.t + 4, kut, "scale")
        kut.scale = (0, 0, 0)
        kljucevi(self.t + 5, kut, "scale")
        ostavljena.scale = (0, 0, 0)
        kljucevi(1, ostavljena, "scale")
        kljucevi(self.t + 4, ostavljena, "scale")
        ostavljena.scale = (1, 1, 1)
        kljucevi(self.t + 5, ostavljena, "scale")
        self._kljuc(self.t, False)
        self.nosi = False
        return self.stoj(10)


def kutija_ob(ime, x, y, z, roditelj=None):
    """Kartonska kutija 0.40 x 0.35 x 0.30 m, centar dna u (x, y, z)."""
    bm = bmesh.new()
    kutija(bm, -0.20, -0.175, 0.0, 0.20, 0.175, 0.30, 0)
    ob = mesh_ob(ime, bm, (ROBA_MAT[2],), K_LJUDI, roditelj)
    ob.location = (x, y, z)
    return ob


# 1-3) popis: radnik ide od polja do polja, okrene se ka regalu i skenira
polja_y = ([REGAL_Y0 + 0.2 + POLJE * (i + 0.5) for i in range(4)] +
           [sredina + POZARNI_PUT / 2 + POLJE * (i + 0.5) for i in range(4)])
for n, (a, strana, polja, t0) in enumerate(((0, 1, polja_y[:6], 1),
                                            (2, -1, polja_y[::-1][:6], 20),
                                            (5, 1, polja_y[4:] + polja_y[4:][::-1], 40))):
    xr = prolazi[a] + strana * (PROLAZ / 2 - 0.8)        # 0.8 m od regala
    ugao_r = 0 if strana > 0 else 180
    r = Osoba(f"Radnik_popis_{n + 1}", xr, polja[0], ugao_r, "skener", t0)
    for yf in polja:
        r.idi(xr, yf).okreni(ugao_r).stoj(45)

# 4) komisioner: ide u prolaz, uzme kutiju sa regala, odnese je u zonu otpreme (2 puta)
a = len(prolazi) - 1
xr = prolazi[a] - (PROLAZ / 2 - 0.7)
r = Osoba("Radnik_komisioner", 52.0, 9.5, 90, "prazno", 1)
kut = kutija_ob("Radnik_komisioner_kutija", 0.48, 0, 0.95, r.telo)
for k, yp in enumerate((14.0, 17.5)):
    spustena = kutija_ob(f"Spustena_kutija_{k + 1}", 50.0, 8.6, 0.30 * k)
    (r.idi(xr, yp).okreni(180).stoj(20).uzmi_kutiju(kut)
      .idi(50.0 + 0.6, 8.6).okreni(180).ostavi_kutiju(kut, spustena))

# 5) radnik sa rucnim paletarom vozi paletu po zoni prijema (zapadni deo)
r = Osoba("Radnik_paletar", 4.0, 2.0, 90, "paletar", 15)
bm = bmesh.new()
kutija(bm, 0.50, -0.25, 0.97, 0.57, 0.25, 1.04, 0)              # rucka
kutija(bm, 0.54, -0.03, 0.15, 0.60, 0.03, 1.00, 0)              # poluga
kutija(bm, 0.56, -0.30, 0.05, 0.78, 0.30, 0.30, 0)              # pumpa
for fy in (-0.30, 0.18):
    kutija(bm, 0.78, fy, 0.03, 1.95, fy + 0.12, 0.09, 0)        # viljuske
mesh_ob("Rucni_paletar", bm, (M["pozar"],), K_LJUDI, r.telo)
pp = paleta("Rucni_paletar_paleta", 0, 0, 0)
pp.parent = r.telo
pp.location = (1.36, 0, 0.09)
for x, y, pauza in ((4.0, 8.0, 30), (10.5, 8.0, 60), (10.5, 3.0, 30), (4.0, 3.0, 40),
                    (4.0, 8.0, 30)):
    r.idi(x, y).stoj(pauza)

# 6) radnik omotava paletu stretch folijom - kruzi oko nje
xo, yo = 37.5, 4.5
pal = paleta("Paleta_omotavanje", xo, yo, ugao=0, visina_robe=1.3)
r = Osoba("Radnik_folija", xo - 1.0, yo - 1.0, 0, "folija", 5)
for _ in range(4):
    for x, y in ((xo + 1.0, yo - 1.0), (xo + 1.0, yo + 1.0), (xo - 1.0, yo + 1.0), (xo - 1.0, yo - 1.0)):
        r.idi(x, y)
pal.data.materials[1] = ROBA_MAT[3]                              # vec umotana (folija)

# 7) kontrolor sa tabletom obilazi rampe
r = Osoba("Radnik_kontrolor", 30.5, 1.5, 0, "tablet", 1)
for x, pauza in ((39.5, 70), (30.5, 70), (39.5, 70)):
    r.idi(x, 1.5).okreni(-90).stoj(pauza)

# 8) poslovodja izlazi iz kancelarije, obilazi regale i vraca se
r = Osoba("Radnik_poslovodja", 2.0, ky0 + 1.0, -90, "tablet", 1)
# (parkirani viljuskari su ispred kancelarije, pa ih zaobilazi)
(r.idi(2.0, ky0 - 0.4).idi(7.0, ky0 - 0.4).idi(10.0, 30.0).idi(10.0, 20.0).okreni(0).stoj(80)
  .idi(10.0, 30.0).idi(7.0, ky0 - 0.4))

# sve animacije linearno izmedju kljuceva (kljucevi su gusti, pa je kretanje glatko)
for ob in bpy.data.objects:
    if ob.animation_data and ob.animation_data.action:
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'


# ---------------------------------------------------------------- svetla
for i in range(5):
    for j in range(4):
        ld = bpy.data.lights.new(f"Svetlo_{i}_{j}", 'AREA')
        ld.energy = 900          # 2500 je previse - slika je bila "spaljena" (sve belo)
        ld.size = 3.0
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
sc.cycles.samples = 64
sc.cycles.use_denoising = True              # uklanja "sum" (zrnastu sliku)
try:
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
except TypeError:
    pass
sc.render.resolution_x = 1280
sc.render.resolution_y = 720
sc.view_settings.view_transform = 'Filmic'
try:
    sc.view_settings.look = 'Filmic - Medium High Contrast'
except TypeError:
    sc.view_settings.look = 'Medium High Contrast'

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
for st in stat_reda:
    print(f"  Red {st['red']}: {st['mesta']} mesta, zauzeto {st['zauzeto']}")

# ---------------------------------------------------------------- info tacke za web prikaz
# koordinate su Blender (X, Y, Z); izvoz_web.py ih prevodi u glTF (Y gore)
info_tacke = [
    dict(naziv="Utovarne rampe", opis=f"{BROJ_RAMPI} rampi, kamioni na {len(RAMPE_SA_KAMIONOM)}",
         x=DUZINA / 2, y=-0.5, z=RAMPA_VISINA + 0.8),
    dict(naziv="Zona prijema i otpreme", opis="10 m ispred rampi",
         x=DUZINA / 2, y=6.0, z=2.5),
    dict(naziv="Kancelarija", opis=f"{KANC_X:.0f} x {KANC_Y:.0f} m",
         x=KANC_X / 2, y=SIRINA - KANC_Y / 2, z=KANC_VISINA + 0.5),
    dict(naziv="Protivpozarni put", opis=f"{POZARNI_PUT:.0f} m, izlazi u nuzdi na oba kraja",
         x=REGAL_X0 - 2.0, y=PP_Y, z=1.0),
    dict(naziv="Punjac viljuskara", opis="3 viljuskara na parkingu",
         x=4.0, y=ky0 - 3.0, z=2.6),
]
podaci = dict(
    magacin=dict(duzina=DUZINA, sirina=SIRINA, visina=VISINA, povrsina=DUZINA * SIRINA,
                 redova=n_redova, nivoa=len(NIVOI), mesta=mesta, zauzeto=zauzeto),
    redovi=oznake_redova,
    info=info_tacke,
)
folder = os.path.dirname(os.path.abspath(__file__)) if "__file__" in globals() else os.getcwd()
with open(os.path.join(folder, "oznake_redova.json"), "w", encoding="utf-8") as f:
    json.dump(podaci, f, ensure_ascii=False, indent=1)

# ---------------------------------------------------------------- snimanje (samo u -b modu)
if bpy.app.background:
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(folder, "magacin.blend"))
