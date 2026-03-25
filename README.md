# lora20 GUI

Prosta aplikacja Tkinter do budowania operacji lora20 (JSON), kodowania/dekodowania CBOR oraz fragmentacji payloadu pod limity Helium/LoRaWAN.

[![Download for Windows](https://img.shields.io/badge/Download-Windows%20EXE-blue?logo=windows)](https://github.com/hattimon/lora20/releases/tag/v1.0.0)

## Funkcje
- Kreator operacji: deploy, mint, transfer, link
- Kodowanie JSON -> CBOR (hex) i dekodowanie CBOR -> JSON
- Wyliczanie kosztu DC (kazde rozpoczete 24 bajty = 1 DC)
- Fragmentacja CBOR do ramek (limit 51 bajtow, naglowek 4B)
- Motyw jasny/ciemny, jezyk PL/EN
- Zapisywanie ustawien uzytkownika

## Wymagania
- Python 3 z Tkinter
- Wymagane do CBOR: cbor2
- Opcjonalnie: appdirs (lepsza lokalizacja ustawien)

## Instalacja zaleznosci
py -m pip install cbor2 appdirs

## Uruchomienie
py lora20_gui.py

## Build EXE (Windows)
py -m pip install pyinstaller
py -m PyInstaller lora20_gui.spec

Wynik znajdziesz w `dist/lora20_gui`.

## Ustawienia
Plik ustawien zapisywany jest w katalogu danych uzytkownika (appdirs) albo w `~/.lora20_gui/settings.json`.
