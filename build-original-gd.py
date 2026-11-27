#!/usr/bin/env python3
import base64, gzip, math, pathlib, struct, subprocess, wave, xml.etree.ElementTree as ET

ROOT = pathlib.Path(".")
OUT = ROOT / "output"
OUT.mkdir(exist_ok=True)

def b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")

# Read the real GD container, preserving its complete metadata structure.
encoded = (ROOT / "README.md").read_text(encoding="utf-8").strip()
wrapper_xml = gzip.decompress(base64.urlsafe_b64decode(encoded + "=" * ((4-len(encoded)%4)%4)))
root = ET.fromstring(wrapper_xml)
d = root.find("dict")
children = list(d)
nodes = {}
for i in range(0, len(children), 2):
    nodes[children[i].text or ""] = children[i+1]

# The original prefix contains GD's color-channel table and level-start settings.
original_inner = gzip.decompress(base64.urlsafe_b64decode((nodes["k4"].text or "") + "=" * ((4-len(nodes["k4"].text or "")%4)%4))).decode("utf-8")
metadata = original_inner.split(";", 1)[0]

objects = []
def obj(oid, x, y, extra=None):
    fields = [("1", str(oid)), ("2", f"{x:g}"), ("3", f"{y:g}")]
    if extra:
        fields.extend((str(k), str(v)) for k,v in extra.items())
    objects.append(",".join(v for pair in fields for v in pair))

# A continuous, readable floor; the challenge comes from rhythmic spike patterns.
# Tile centers are 15 + 30n, with the floor's top at y=30.
length = 6600
floor_x = set(range(15, length, 30))
for x in sorted(floor_x):
    obj(1, x, 15)

# Hand-authored Easy Demon progression: introductory singles, doubles, syncopation,
# then denser but consistently readable closing patterns.
hazards = [
  315, 555, 795, 915, 945, 1155,
  1395, 1515, 1545, 1755, 1995, 2115, 2145, 2175,
  2415, 2535, 2565, 2775, 3015, 3135, 3165, 3375,
  3495, 3525, 3555, 3795, 3915, 3945, 4155, 4395,
  4515, 4545, 4755, 4875, 4905, 4935, 5175, 5295,
  5325, 5535, 5655, 5685, 5895, 6015, 6045, 6075,
  6315, 6435, 6465
]
for x in hazards:
    obj(8, x, 45)

# A handful of low, broad platforms add visual rhythm without blocking the jump lane.
# Their tops are high enough to read as scenery, not surprise collision walls.
for start, count in [(690,3),(1650,3),(2850,4),(4050,3),(5250,4),(6150,3)]:
    for i in range(count):
        obj(1, start + i*30, 195)

# Background architecture: sparse pillars and overhead beams, kept clear of the player.
for x in range(240, length-120, 600):
    for y in (255,285,315):
        obj(1, x, y)
    for dx in (30,60,90):
        obj(1, x+dx, 315)

level_text = metadata + ";" + ";".join(objects) + ";"
inner_encoded = b64url(gzip.compress(level_text.encode("utf-8"), compresslevel=9, mtime=0))
nodes["k2"].text = "AFTERIMAGE"
nodes["k4"].text = inner_encoded
# GD stores a song reference, not audio bytes. Use the built-in song as a safe fallback;
# the original companion soundtrack is supplied separately for local custom-song use.
if "k45" in nodes:
    nodes["k45"].text = "0"

outer_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
level_file = b64url(gzip.compress(outer_xml, compresslevel=9, mtime=0))
(OUT / "AFTERIMAGE.gdlvl").write_text(level_file, encoding="ascii")

# Compose an original 150 BPM electronic/chiptune track, 16 bars (25.6 seconds).
sr = 44100
bpm = 150
bars = 16
duration = bars * 4 * 60 / bpm
nframes = int(sr * duration)
notes = [0, 3, 7, 10, 7, 3, 0, -2, 0, 5, 8, 12, 8, 5, 3, 0]
scale = [55.0 * (2 ** (s/12)) for s in notes]
wav_path = OUT / "AFTERIMAGE-original-song.wav"
with wave.open(str(wav_path), "wb") as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
    buf = bytearray()
    beat = 60 / bpm
    for i in range(nframes):
        t = i / sr
        beat_pos = t / beat
        beat_idx = int(beat_pos)
        frac = beat_pos - beat_idx
        bar_step = int(t / (beat*4) * 4) % len(scale)
        freq = scale[bar_step]
        # warm pulse lead with a soft detuned overtone
        lead_env = min(1.0, frac*10) * min(1.0, (1-frac)*7)
        lead = (0.10*math.sin(2*math.pi*freq*t) +
                0.035*math.sin(2*math.pi*freq*2.01*t) +
                0.018*math.sin(2*math.pi*freq*3*t)) * lead_env
        # syncopated bass
        bass_freq = 55.0 * (2 ** ([0,0,7,0,3,3,10,7][(int(beat_pos*2))%8]/12))
        bass = 0.13 * math.sin(2*math.pi*bass_freq*t) * (0.55 + 0.45*math.exp(-frac*8))
        # kick on beats 1 and 3, snare on 2 and 4, hats on eighth notes
        kick_phase = (t % (2*beat))
        kick = 0.32 * math.exp(-kick_phase*18) * math.sin(2*math.pi*(48-22*min(kick_phase,0.08)/0.08)*kick_phase) if kick_phase < 0.18 else 0.0
        beat_in_bar = beat_idx % 4
        snare_phase = t % (4*beat)
        snare = 0.0
        if beat_in_bar in (1,3) and frac < 0.18:
            snare = 0.13 * math.exp(-frac*35) * math.sin(2*math.pi*185*t)
        hat_phase = beat_pos*2
        hat_frac = hat_phase - math.floor(hat_phase)
        hat = 0.035 * math.exp(-hat_frac*70) * math.sin(2*math.pi*(7000 + 400*math.sin(t))*t)
        # subtle stereo movement
        mix = lead + bass + kick + snare + hat
        left = max(-0.95, min(0.95, mix * (0.96 + 0.04*math.sin(t*1.7))))
        right = max(-0.95, min(0.95, mix * (0.96 + 0.04*math.cos(t*1.5))))
        buf.extend(struct.pack("<hh", int(left*32767), int(right*32767)))
    w.writeframes(buf)

subprocess.run(["ffmpeg","-y","-loglevel","error","-i",str(wav_path),"-codec:a","libmp3lame","-b:a","192k",str(OUT/"AFTERIMAGE-original-song.mp3")], check=True)
wav_path.unlink()

# Round-trip validation of both compression layers and basic object integrity.
check_outer = gzip.decompress(base64.urlsafe_b64decode(level_file + "="*((4-len(level_file)%4)%4)))
check_root = ET.fromstring(check_outer)
check_nodes = list(check_root.find("dict"))
vals = {}
for i in range(0,len(check_nodes),2):
    vals[check_nodes[i].text or ""] = check_nodes[i+1].text or ""
check_inner = gzip.decompress(base64.urlsafe_b64decode(vals["k4"] + "="*((4-len(vals["k4"])%4)%4))).decode()
records = [r for r in check_inner.split(";") if r.startswith("1,") and ",2," in r and ",3," in r]
assert len(records) == len(objects), (len(records),len(objects))
assert vals["k2"] == "AFTERIMAGE"
assert len(level_file) > 1000
print("Generated:", OUT/"AFTERIMAGE.gdlvl", "objects:", len(objects), "level bytes:", len(level_file))
print("Generated original soundtrack:", OUT/"AFTERIMAGE-original-song.mp3", "duration:", duration)
