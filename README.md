# Equipo IA

Varias IAs gratuitas trabajando con roles fijos. Claude (Claude Code) hace de jefe:
reparte tareas, revisa y junta los resultados.

| Miembro | Rol | Usa |
|---|---|---|
| disenador | imágenes (redacta el prompt según su guía de estilo y luego genera) | Gemini → Hugging Face → Pollinations |
| redactor | propuestas Workana, textos de apps y webs | Groq → Gemini → Pollinations |
| ideas | lluvia de ideas | Groq → Gemini → Pollinations |
| revisor | revisión de código | Gemini → Groq → Pollinations |
| traductor | traducciones de juegos y fichas de tienda | Gemini → Groq → Pollinations |
| promotor | posts para redes y textos de tienda | Groq → Gemini → Pollinations |

## Uso

```
python equipo.py estado                      # qué claves hay
python equipo.py lista                       # miembros
python equipo.py redactor "propuesta para ..." -o propuesta.txt
python equipo.py disenador "ícono de ..." -o salida/icono.png --ancho 1024 --alto 1024 -n 3
python equipo.py aprender redactor "No uses la palabra 'sinergia'"
```

## Educarlas

Cada ficha en `fichas/` tiene rol, reglas y ejemplos. `aprender` agrega lecciones al final
(sección "Aprendido") y se usan en cada pedido siguiente. Para un miembro nuevo, copia una
ficha y cambia el texto.

Claves en `.env` (ver `.env.example`). Sin claves funciona igual con Pollinations.
