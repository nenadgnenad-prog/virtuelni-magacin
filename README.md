# Virtuelni magacin

3D model magacina od 3.000 m² (60 × 50 m, visina 10 m), napravljen Python skriptom za Blender.

## Fajlovi

| Fajl | Opis |
|---|---|
| `magacin.py` | Glavna skripta – pravi celu scenu (parametri su na vrhu fajla) |
| `magacin.blend` | Gotova Blender scena (pravi je `magacin.py`) |
| `render_pregled.py` | Render slike iz glavne kamere (frejm 150) -> `magacin_pregled.png` |
| `render_odozgo.py` | Render tlocrta odozgo -> `magacin_odozgo.png` |

## Pokretanje iz VS Code

`Ctrl+Shift+B` – ponovo pravi `magacin.blend` iz `magacin.py`.
`Terminal -> Run Task...` – ostali zadaci (otvaranje u Blenderu, renderi).

Blender: **2.93.18 LTS (portable)** u `C:\Blender2.93\blender-2.93.18-windows-x64\`.
Novije verzije (3.6, 5.x) ne rade na Intel HD Graphics 4000 grafičkoj kartici ovog računara.

## Šta je u sceni

- Hala 60 × 50 × 10 m, 6 utovarnih rampi na južnom zidu, zona prijema/otpreme 10 m
- Kancelarija 12 × 10 m (severozapadni ugao)
- 14 redova paletnih regala (8 m, 5 nivoa), prolazi 4 m – 1.120 paletnih mesta (~75 % popunjeno)
- Protivpožarni put: poprečni (4 m) između blokova regala + uzdužni uz zapadnu stranu i istočni zid,
  izlazi u nuždi na istočnom i zapadnom zidu, hidranti
- 3 kamiona na rampama 2, 3 i 5
- Animacija (480 frejmova, 25 fps):
  - 3 viljuškara utovaraju kamione
  - viljuškar odlaže paletu na regal (5,4 m), drugi skida paletu sa 1,8 m
  - 2 viljuškara voze kroz prolaze, 3 parkirana kod punjača
  - 3 radnika rade popis sa skenerom, 2 radnika u zoni otpreme

## Ideje za nastavak

- Video (MP4) animacije, renderi iz više uglova
- Rampe sa visinskom razlikom (dok leveleri), punjači za viljuškare
- Stubovi hale, krovni svetlarnici, oznake lokacija na regalima
