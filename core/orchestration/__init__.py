"""
Orquestación
============

El sidecar HTTP (`sidecar_server` y sus routers en `sidecar/`): fuentes y
escaneo multifuente, juez, búsqueda sobre la evidencia, Gemini y salud.

El grafo LangGraph de la pipeline antigua de Reddit (fetch → filter →
intelligence → storage → quality gate), su servidor MCP, la agregación en
clusters y el Top N se retiraron en C2: ninguna vista ni comando los usaba.
Sus tablas se conservan sin escrituras (docs/pipeline-antigua.md).
"""
