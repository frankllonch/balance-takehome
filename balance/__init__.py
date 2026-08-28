"""
Balance · del log de eventos de un dispositivo a decisiones de producto.

El fichero de eventos es el sistema de registro: inmutable y única fuente de
verdad. Todo lo que hay en este paquete es dato derivado, calculado como una
función pura y determinista de ese log.

    events  →  metrics  →  score  →  intelligence
     capa 0     capa 1     capa 2       capa 3

Ninguna de esas cuatro capas importa Streamlit ni Plotly: `run.py` (CLI) y
`app.py` (dashboard) son dos adaptadores sobre el mismo núcleo, y `charts.py` y
`theme.py` son presentación pura.

Ver `ARCHITECTURE.md` para el mapa completo y para cómo hacer los cambios más
habituales.
"""

__version__ = "1.0.0"
