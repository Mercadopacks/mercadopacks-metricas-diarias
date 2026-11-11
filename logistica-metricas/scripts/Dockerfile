# Imagen de CI para el workflow de descarga diaria
# (.github/workflows/descarga_diaria.yml). Reemplaza instalar Chromium +
# LibreOffice + las dependencias de Python de cero en cada corrida (~1-2
# min de instalacion de los ~2 min que tarda hoy la corrida completa, ver
# reglas_de_negocio.md seccion 15) por una imagen ya armada de antemano.
#
# Se reconstruye sola via .github/workflows/build_imagen_ci.yml cuando
# cambia este archivo o requirements.txt — el workflow de descarga diaria
# no instala nada, solo usa la imagen ya publicada.
#
# Base: imagen oficial de Microsoft con Python + Playwright + Chromium +
# todas las dependencias de sistema de Chromium ya instaladas. El tag de
# version (v1.62.0-jammy) tiene que coincidir con la version de
# "playwright" fijada en requirements.txt — si se actualiza una, hay que
# actualizar la otra.
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# LibreOffice no viene en la imagen base de Playwright — hace falta como
# respaldo para los .xls viejos de LightData que a veces vienen con el
# BIFF corrupto (ver cargar_export() en generar_reporte.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-calc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
