"""Equipo IA: varias IAs gratuitas trabajando con roles fijos.

Uso:
    python equipo.py lista
    python equipo.py <miembro> "tarea" [-o archivo] [--ancho 1024 --alto 1024] [-n 1]
    python equipo.py aprender <miembro> "lección que debe recordar"
    python equipo.py estado

Cada miembro tiene su ficha en fichas/<miembro>.md: proveedores (en orden de
preferencia), rol, reglas, ejemplos y lo aprendido. Si un proveedor falla o no
tiene clave, se pasa al siguiente. Pollinations no necesita clave, así que
siempre hay respaldo.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
FICHAS = RAIZ / "fichas"
SALIDA = RAIZ / "salida"
HISTORIAL = RAIZ / "historial"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- claves ----

def cargar_env() -> None:
    for archivo in (RAIZ / ".env", RAIZ.parent / "ChatbotPyme" / ".env"):
        if not archivo.exists():
            continue
        for linea in archivo.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            k, v = linea.split("=", 1)
            v = v.strip().strip('"').strip("'")
            if v and not os.environ.get(k.strip()):
                os.environ[k.strip()] = v


def clave(nombre: str) -> str | None:
    return os.environ.get(nombre) or None


# ----------------------------------------------------------------- http -----

def _post(url: str, cuerpo: dict, cabeceras: dict, crudo=False, espera=120):
    datos = json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method="POST",
                                 headers={"Content-Type": "application/json",
                                          "User-Agent": "EquipoIA/1.0", **cabeceras})
    with urllib.request.urlopen(req, timeout=espera) as r:
        contenido = r.read()
    return contenido if crudo else json.loads(contenido)


def _get(url: str, espera=180) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "EquipoIA/1.0"})
    with urllib.request.urlopen(req, timeout=espera) as r:
        return r.read()


class SinClave(Exception):
    pass


def reintentar(fn, intentos=3):
    """Pollinations gratis permite 1 pedido cada ~45 s: si nos frena, espera y reintenta."""
    for i in range(intentos):
        try:
            return fn()
        except urllib.error.HTTPError as e:
            if e.code not in (402, 429) or i == intentos - 1:
                raise
            cuerpo = e.read().decode("utf-8", "replace")
            m = re.search(r"Retry after (\d+)", cuerpo)
            espera = int(m.group(1)) + 3 if m else 50
            print(f"(límite gratis, espero {espera} s...)", file=sys.stderr)
            time.sleep(espera)


# ------------------------------------------------------------ proveedores ---
# Texto: (sistema, tarea) -> str

def texto_groq(sistema: str, tarea: str, modelo: str | None) -> str:
    k = clave("GROQ_API_KEY")
    if not k:
        raise SinClave("GROQ_API_KEY")
    r = _post("https://api.groq.com/openai/v1/chat/completions",
              {"model": modelo or "openai/gpt-oss-120b",
               "messages": [{"role": "system", "content": sistema},
                            {"role": "user", "content": tarea}],
               "temperature": 0.7},
              {"Authorization": f"Bearer {k}"})
    return r["choices"][0]["message"]["content"]


def texto_gemini(sistema: str, tarea: str, modelo: str | None) -> str:
    k = clave("GEMINI_API_KEY")
    if not k:
        raise SinClave("GEMINI_API_KEY")
    modelo = modelo or "gemini-3.5-flash"
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
              {"system_instruction": {"parts": [{"text": sistema}]},
               "contents": [{"role": "user", "parts": [{"text": tarea}]}]},
              {"x-goog-api-key": k})
    partes = r["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in partes)


def texto_pollinations(sistema: str, tarea: str, modelo: str | None) -> str:
    r = reintentar(lambda: _post("https://text.pollinations.ai/openai",
                                 {"model": modelo or "openai",
                                  "messages": [{"role": "system", "content": sistema},
                                               {"role": "user", "content": tarea}]},
                                 {}))
    return r["choices"][0]["message"]["content"]


# Imagen: (prompt, ancho, alto) -> bytes

def imagen_gemini(prompt: str, ancho: int, alto: int, modelo: str | None) -> bytes:
    k = clave("GEMINI_API_KEY")
    if not k:
        raise SinClave("GEMINI_API_KEY")
    modelo = modelo or "gemini-3.1-flash-image"
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent",
              {"contents": [{"parts": [{"text": f"{prompt}\n(aspect ratio {ancho}:{alto})"}]}],
               "generationConfig": {"responseModalities": ["IMAGE"]}},
              {"x-goog-api-key": k}, espera=180)
    for p in r["candidates"][0]["content"]["parts"]:
        if "inlineData" in p:
            return base64.b64decode(p["inlineData"]["data"])
    raise RuntimeError("Gemini no devolvió imagen")


def imagen_hf(prompt: str, ancho: int, alto: int, modelo: str | None) -> bytes:
    k = clave("HF_TOKEN")
    if not k:
        raise SinClave("HF_TOKEN")
    modelo = modelo or "black-forest-labs/FLUX.1-schnell"
    return _post(f"https://router.huggingface.co/hf-inference/models/{modelo}",
                 {"inputs": prompt, "parameters": {"width": ancho, "height": alto}},
                 {"Authorization": f"Bearer {k}"}, crudo=True, espera=180)


def imagen_pollinations(prompt: str, ancho: int, alto: int, modelo: str | None) -> bytes:
    q = urllib.parse.quote(prompt[:1500])
    semilla = int(time.time()) % 100000
    return reintentar(lambda: _get(f"https://image.pollinations.ai/prompt/{q}?width={ancho}&height={alto}"
                                   f"&nologo=true&model={modelo or 'flux'}&seed={semilla}"))


TEXTO = {"groq": texto_groq, "gemini": texto_gemini, "pollinations": texto_pollinations}
IMAGEN = {"gemini": imagen_gemini, "hf": imagen_hf, "pollinations": imagen_pollinations}


# ---------------------------------------------------------------- fichas ----

def leer_ficha(nombre: str) -> dict:
    ruta = FICHAS / f"{nombre}.md"
    if not ruta.exists():
        raise SystemExit(f"No existe el miembro '{nombre}'. Usa: python equipo.py lista")
    txt = ruta.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", txt, re.S)
    if not m:
        raise SystemExit(f"Ficha mal formada: {ruta}")
    meta = {}
    for linea in m.group(1).splitlines():
        if ":" in linea:
            k, v = linea.split(":", 1)
            meta[k.strip()] = v.strip()
    contexto = FICHAS / "_contexto.md"
    base = contexto.read_text(encoding="utf-8").strip() + "\n\n---\n\n" if contexto.exists() else ""
    meta["cuerpo"] = base + "# Tu rol en el equipo\n\n" + m.group(2).strip()
    meta["ruta"] = ruta
    meta["nombre"] = nombre
    return meta


def proveedores(texto: str) -> list[tuple[str, str | None]]:
    """'groq, gemini:gemini-2.5-pro' -> [('groq', None), ('gemini', 'gemini-2.5-pro')]"""
    res = []
    for p in texto.split(","):
        p = p.strip()
        if p:
            nombre, _, modelo = p.partition(":")
            res.append((nombre.strip(), modelo.strip() or None))
    return res


def con_respaldo(tabla: dict, lista, *args):
    errores = []
    for nombre, modelo in lista:
        fn = tabla.get(nombre)
        if not fn:
            errores.append(f"{nombre}: desconocido")
            continue
        try:
            return fn(*args, modelo), nombre
        except SinClave as e:
            errores.append(f"{nombre}: falta {e}")
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")[:300]
            errores.append(f"{nombre}: HTTP {e.code} {cuerpo}")
        except Exception as e:  # noqa: BLE001
            errores.append(f"{nombre}: {type(e).__name__} {e}")
    raise SystemExit("Ningún proveedor respondió:\n  " + "\n  ".join(errores))


# ---------------------------------------------------------------- acciones --

def guardar_historial(miembro: str, tarea: str, proveedor: str, resultado: str) -> None:
    HISTORIAL.mkdir(exist_ok=True)
    with open(HISTORIAL / f"{dt.date.today()}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"hora": dt.datetime.now().isoformat(timespec="seconds"),
                            "miembro": miembro, "proveedor": proveedor,
                            "tarea": tarea, "resultado": resultado[:4000]},
                           ensure_ascii=False) + "\n")


def nombre_archivo(tarea: str, ext: str) -> Path:
    base = re.sub(r"[^a-z0-9]+", "-", tarea.lower())[:40].strip("-") or "resultado"
    SALIDA.mkdir(exist_ok=True)
    return SALIDA / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{base}.{ext}"


def trabajar(args) -> None:
    f = leer_ficha(args.miembro)
    tipo = f.get("tipo", "texto")
    if tipo == "texto":
        out, prov = con_respaldo(TEXTO, proveedores(f.get("proveedores", "pollinations")),
                                 f["cuerpo"], args.tarea)
        print(out)
        if args.o:
            Path(args.o).write_text(out, encoding="utf-8")
            print(f"\n[guardado en {args.o}]", file=sys.stderr)
        guardar_historial(args.miembro, args.tarea, prov, out)
        print(f"\n[{args.miembro} vía {prov}]", file=sys.stderr)
    elif tipo == "imagen":
        # 1) Un modelo de texto convierte el pedido en un prompt detallado según la guía de estilo
        prompt, prov_t = con_respaldo(TEXTO, proveedores(f.get("redacta_con", "pollinations")),
                                      f["cuerpo"], args.tarea)
        prompt = prompt.strip().strip('"')
        print(f"Prompt ({prov_t}): {prompt}\n")
        rutas = []
        for i in range(args.n):
            datos, prov = con_respaldo(IMAGEN, proveedores(f.get("proveedores", "pollinations")),
                                       prompt, args.ancho, args.alto)
            ext = "jpg" if datos[:3] == b"\xff\xd8\xff" else "png"
            ruta = Path(args.o) if (args.o and args.n == 1) else nombre_archivo(args.tarea, ext)
            if args.o and args.n > 1:
                p = Path(args.o)
                ruta = p.with_name(f"{p.stem}-{i + 1}{p.suffix or '.' + ext}")
            ruta.parent.mkdir(parents=True, exist_ok=True)
            ruta.write_bytes(datos)
            rutas.append(str(ruta))
            print(f"Imagen ({prov}): {ruta}")
        guardar_historial(args.miembro, args.tarea, f"{prov_t}+{prov}", prompt + "\n" + "\n".join(rutas))
    else:
        raise SystemExit(f"Tipo desconocido: {tipo}")


def aprender(miembro: str, leccion: str) -> None:
    f = leer_ficha(miembro)
    txt = f["ruta"].read_text(encoding="utf-8").rstrip()
    if "## Aprendido" not in txt:
        txt += "\n\n## Aprendido\n"
    txt += f"\n- ({dt.date.today()}) {leccion}"
    f["ruta"].write_text(txt + "\n", encoding="utf-8")
    print(f"{miembro} aprendió: {leccion}")


def lista() -> None:
    for ruta in sorted(FICHAS.glob("*.md")):
        if ruta.stem.startswith("_"):
            continue
        f = leer_ficha(ruta.stem)
        print(f"{ruta.stem:12} [{f.get('tipo', 'texto'):6}] {f.get('rol', '')}  ({f.get('proveedores', '')})")


def estado() -> None:
    for k in ("GROQ_API_KEY", "GEMINI_API_KEY", "HF_TOKEN"):
        print(f"{k:15} {'OK' if clave(k) else 'falta (se usa respaldo)'}")
    print("Pollinations    OK (sin clave)")


def main() -> None:
    cargar_env()
    if len(sys.argv) >= 2 and sys.argv[1] == "lista":
        return lista()
    if len(sys.argv) >= 2 and sys.argv[1] == "estado":
        return estado()
    if len(sys.argv) >= 4 and sys.argv[1] == "aprender":
        return aprender(sys.argv[2], " ".join(sys.argv[3:]))
    ap = argparse.ArgumentParser(description="Equipo IA")
    ap.add_argument("miembro")
    ap.add_argument("tarea")
    ap.add_argument("-o", help="archivo de salida")
    ap.add_argument("-n", type=int, default=1, help="cantidad de imágenes")
    ap.add_argument("--ancho", type=int, default=1024)
    ap.add_argument("--alto", type=int, default=1024)
    trabajar(ap.parse_args())


if __name__ == "__main__":
    main()
