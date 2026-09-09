# TAMPER - Taludas Anno 117 Map Template Editor

> Eine eigenständige Desktop-Anwendung zum Erstellen, Bearbeiten und Exportieren von **Anno 117**-Kartenvorlagen (`.a7tinfo`).

![Thumbnail](thumbnail_en.jpg)

-> Englisches Readme findet ihr [hier](README_en.md)

---

## Inhaltsverzeichnis

- [TAMPER - Taludas Anno 117 Map Template Editor](#tamper---taludas-anno-117-map-template-editor)
  - [Inhaltsverzeichnis](#inhaltsverzeichnis)
  - [1. Übersicht](#1-übersicht)
  - [2. Systemanforderungen](#2-systemanforderungen)
  - [3. Installation](#3-installation)
    - [Standalone-Binary (Empfohlen)](#standalone-binary-empfohlen)
    - [Ausführen aus dem Quellcode](#ausführen-aus-dem-quellcode)
  - [4. Ersteinrichtung](#4-ersteinrichtung)
  - [5. Benutzeroberfläche](#5-benutzeroberfläche)
  - [6. Funktionsreferenz](#6-funktionsreferenz)
    - [6.1 Neue Karte erstellen](#61-neue-karte-erstellen)
    - [6.2 Vorhandene Vorlage importieren](#62-vorhandene-vorlage-importieren)
    - [6.3 Die Kartenansicht](#63-die-kartenansicht)
    - [6.4 Inseln platzieren](#64-inseln-platzieren)
    - [6.5 Benutzerdefinierte (feste) Inseln](#65-benutzerdefinierte-feste-inseln)
    - [6.6 Schiffsstartpunkte](#66-schiffsstartpunkte)
    - [6.7 Verschieben und Neupositionieren](#67-verschieben-und-neupositionieren)
    - [6.8 Kollisionserkennung](#68-kollisionserkennung)
    - [6.9 Erweiterte (DLC01) Vorlagen](#69-erweiterte-dlc01-vorlagen)
    - [6.10 Inseleigenschaften-Dialog](#610-inseleigenschaften-dialog)
    - [6.11 Validierung und Limits](#611-validierung-und-limits)
    - [6.12 Platzierungshilfen (Spiegelmodus, Kollisionen ignorieren, Formation sperren)](#612-platzierungshilfen-spiegelmodus-kollisionen-ignorieren-formation-sperren)
  - [7. Speichern und Exportieren](#7-speichern-und-exportieren)
    - [7.1 XML speichern / laden](#71-xml-speichern--laden)
    - [7.2 Als .a7tinfo exportieren](#72-als-a7tinfo-exportieren)
    - [7.3 PNG exportieren](#73-png-exportieren)
    - [7.4 Als spielbare Mod exportieren (.zip)](#74-als-spielbare-mod-exportieren-zip)
  - [8. Insel-Referenz](#8-insel-referenz)
    - [Pool-Limits (zufällige Inseln pro Region)](#pool-limits-zufällige-inseln-pro-region)
    - [Inselgrößen-Referenz (Spielpixel)](#inselgrößen-referenz-spielpixel)
  - [9. Technische Hinweise](#9-technische-hinweise)
    - [Dateiformat](#dateiformat)
    - [Koordinatensystem](#koordinatensystem)
    - [Insel-Registry](#insel-registry)
    - [PyInstaller-Build](#pyinstaller-build)
  - [10. Lizenz und Credits](#10-lizenz-und-credits)
    - [Abhängigkeiten:](#abhängigkeiten)
    - [Lizenz:](#lizenz)
    - [Credits:](#credits)

---

## 1. Übersicht

**TAMPER** ist ein Community-Karteneditor für das Kartenvorlagen-System in **Anno 117: Pax Romana**. Das Spiel generiert seine Spielwelten prozedural aus Karten-*Vorlagen* - binären Dateien (`.a7tinfo`), die festlegen, welche Inseln an welchen Positionen, in welchen Größen und Konfigurationen erscheinen können. TAMPER bietet eine grafische Oberfläche, um diese Vorlagen zu erstellen und zu bearbeiten, ohne direkt XML zu bearbeiten.

**Was du mit TAMPER machen kannst:**

- Vollständige Kartenlayouts für beide Regionen - Latium (Römisch) und Albion (Keltisch) - von Grund auf entwerfen.
- Beliebige Spielvorlagen, einschließlich der Vanillakarten, importieren und visuell inspizieren.
- Zufällige Inseln (Klein, Mittel, Groß, Extra Groß) nach Typ (Normal, Startinsel, Drittpartei, Pirat, Vulkan) platzieren.
- Bestimmte Spielinseln als feste Inseln mit Rotation, Inselbeschriftung und individuell zugewiesenen Fruchtbarkeiten einbinden.
- Schiffsstartpunkte setzen.
- Den spielbaren Bereich und - bei DLC01-aktivierten Karten - den erweiterten spielbaren Bereich konfigurieren.
- Das Ergebnis als fertig installierbare Mod-`.zip`-Datei für alle drei Schwierigkeitsvarianten exportieren oder - für erfahrenere Modder - in .a7tinfo- oder XML-Dateien.

TAMPER ist eine eigenständige GUI-Anwendung (Tkinter) und verändert keine Spieldateien direkt. Ubisoft's proprietäres Binärformat wird über das Open-Source-Tool **FileDBReader** gelesen und geschrieben.

---

## 2. Systemanforderungen

| Komponente | Anforderung |
|---|---|
| Betriebssystem | Windows 10/11 (64-Bit) oder Linux |
| Python | 3.10 oder neuer (nur im Quellcode-Modus) |
| Pillow | 9.x oder neuer (`pip install pillow`) (nur im Quellcode-Modus) |
| FileDBReader | Erforderlich für `.a7tinfo`-Import/Export - [Download auf GitHub](https://github.com/anno-mods/FileDBReader/releases) |
| RdaConsole | Erforderlich nur für **Import aus dem Spiel** - [Download auf GitHub](https://github.com/anno-mods/RdaConsole/releases) |
| Anno 117 | Erforderlich nur für **Import aus dem Spiel**; nicht für Bearbeitung oder Export |

> **Linux-Hinweis:** FileDBReader stellt eine native Linux-Binary bereit. RdaConsole wird derzeit nur als Windows-`.exe` ausgeliefert; der direkte Import aus den Spielarchiven erfordert daher Wine. Alle anderen Editorfunktionen - Erstellen, Bearbeiten und Exportieren von Karten - funktionieren nativ unter Linux.

---

## 3. Installation

### Standalone-Binary (Empfohlen)

Lade die neueste `.exe` von der [Releases-Seite](../../releases) herunter. Eine Python-Installation ist nicht erforderlich. Lege die Binary an einem beliebigen Ort ab und starte sie direkt.

FileDBReader/RDAConsole ist **nicht** enthalten und muss separat heruntergeladen werden. Der Editor fordert dich beim ersten Start zur Einrichtung auf, falls er ihn nicht automatisch findet.

### Ausführen aus dem Quellcode

```bash
git clone https://github.com/taludas/anno-117-map-editor.git
cd anno-117-map-editor
python main.py
```

**Abhängigkeiten:**

```
pillow>=9.0
```

Lege `FileDBReader.exe` (Windows) oder `FileDBReader` (Linux) und `RDAConsole.exe` an einem der folgenden Orte ab, damit der Editor ihn automatisch erkennt:

- `tools/FileDBReader[.exe]` (relativ zu `main.py`)
- `C:\tools\FileDBReader.exe` (Windows-Standard)
- `~/.local/bin/FileDBReader` (Linux-Standard)

---

## 4. Ersteinrichtung

Beim ersten Start prüft der Editor, ob die benötigten Tools vorhanden sind, und zeigt einen Einrichtungsdialog an, falls etwas fehlt.

**Spielpfad**
Einstellbar über `Bearbeiten → Spielpfad festlegen…` oder die Automatisch-Erkennen-Funktion. Der Editor sucht selbstständig in bekannten Ubisoft Connect-, Steam- und Epic-Installationsverzeichnissen. Wird für den „Import aus dem Spiel"-Workflow benötigt.

**FileDBReader-Pfad**
Einstellbar über `Optionen → FileDBReader-Pfad festlegen…`, falls er nicht automatisch erkannt wird. Erforderlich zum Importieren von `.a7tinfo`-Dateien und zum Komprimieren von Exporten. Zeigt auf die `FileDBReader`-Programmdatei.

**RdaConsole-Pfad**
Einstellbar über `Optionen → RdaConsole-Pfad festlegen…`. Nur erforderlich, wenn du `Datei → Import aus Spiel` verwenden möchtest, um Kartenvorlagen direkt aus den RDA-Archiven des Spiels zu extrahieren. Nicht nötig zum Bearbeiten von XML-Dateien oder zum Exportieren.

Falls keines der beiden Tools automatisch gefunden wird, öffnet sich beim Start ein **Tool-Einrichtungsdialog**, der anbietet, sie von GitHub automatisch zu installieren, manuell auszuwählen, oder die Einrichtung vorerst zu überspringen.

Alle Pfade werden sitzungsübergreifend im plattformgerechten Konfigurationsverzeichnis gespeichert (`%APPDATA%\Anno117MapEditor` unter Windows, `~/.config/Anno117MapEditor` unter Linux).

**Optionen-Menü:** Neben den oben genannten Tool-/Spielpfaden enthält `Optionen` auch zwei Export-Schalter - „Region Name in PNG-Files" (siehe [7.3](#73-png-exportieren)) und „Enable all Islands in all Regions", der dem Feste-Insel-Auswähler ([6.5](#65-benutzerdefinierte-feste-inseln)) erlaubt, römische und keltische Inseln unabhängig vom aktiven Regions-Tab anzubieten. Beide sind standardmäßig aktiviert.

---

## 5. Benutzeroberfläche

![Main app window layout](main_window.png)

**Tabs:** Jede Region (Latium / Albion) hat einen eigenen Tab mit unabhängiger Kartenansicht und Seitenleiste. Vorlagen für beide Regionen können gleichzeitig geöffnet sein.

**Kartenansicht:** Die Karte wird in einer isometrischen (um 45° gedrehten) Projektion dargestellt, die der In-Game-Ansicht entspricht. Himmelsrichtungen (N/S/O/W) sind an den Kartenrändern eingeblendet. Eine Legende mit Steuerungshinweisen und ein Statistikfeld sind in den Ecken untergebracht.

**Seitenleiste:** Enthält die Inselplatzier-Palette, Aktionsschaltflächen für die Auswahl, Warnungen zu Insel-Limits, einen Startinsel-Zähler und Ansichtsoptionen.

---

## 6. Funktionsreferenz

### 6.1 Neue Karte erstellen

`Datei → Neu…` (oder die **Neue Karte**-Schaltfläche in der Kopfzeile) öffnet den Neue-Karte-Dialog.

**Einstellungen:**

| Feld | Beschreibung |
|---|---|
| Region | Latium (Römisch) oder Albion (Keltisch) |
| Schwierigkeit | Standardschwierigkeit für automatische Ableitung der anderen Schwierigkeitsgrade beim Mod-Export |
| Erweiterte Vorlage | DLC01-Unterstützung (Prophecies of Ash) aktivieren |
| Kartengröße | Gesamtgröße der Karte in Spielpixeln, in 64-Px-Schritten einstellbar bis maximal 8192. Standard ist 2048 (2688 bei aktivierter „Erweiterte Vorlage" für Latium) |
| Randabstand | Abstand in Spielpixeln vom Kartenrand zur Spielbereichsgrenze |
| X- / Y-Versatz | Asymmetrischer Versatz des Spielbereichsmittelpunkts |

**Spielbarer Bereich (PA):** Der Editor verwendet ein *Randabstand* + *Versatz*-Modell. PA-Koordinaten werden stets auf Vielfache von 4 Px gerundet (Spielanforderung). Die Formel lautet:

```
PA = (Abstand + Vx,  Abstand + Vy,  Größe − Abstand + Vx,  Größe − Abstand + Vy)
```

Die Schieberegler erzwingen automatisch einen Mindestrand von 20 Px auf allen Seiten. Werte können auch direkt in die Textfelder neben den Schiebereglern eingegeben werden.

**Erweiterte Vorlagen:** Wenn „Erweiterte Vorlage" aktiviert wird, entsteht ein DLC01-kompatibles Layout. Die Karte verwendet eine größere Gesamtgröße (2688 × 2688 für Latium), und der Editor verwaltet sowohl den regulären *InitialPlayableArea* (ohne DLC sichtbar) als auch den vollen *PlayableArea* (mit DLC01 freigeschaltet). Der initiale PA wird automatisch vom vollen PA abgeleitet - er wird nie separat gespeichert.

**Live-Vorschau:** Eine Echtzeit-Isometrie-Miniaturansicht zeigt beim Verschieben der Regler die spielbaren Bereiche von Latium und Albion nebeneinander.

Nach Bestätigung erstellt TAMPER die Vorlage für die gewählte Region und initialisiert gleichzeitig eine leere Standardvorlage für die Gegenregion, sodass beide Tabs sofort bearbeitet werden können.

**Kartengröße über den Standard hinaus:** Größen bis 4096 sind im Spiel nachweislich problemlos. Darüber wirst du vor dem Fortfahren um Bestätigung gebeten: Bei 6144 rendert das Spiel korrekt, außer sehr nah am Kartenrand, und bei 8192 werden Gebäude nicht mehr angezeigt (funktionieren aber weiterhin) - das ist eine Einschränkung der Render-/Streaming-Reichweite des Spiels selbst, nicht der exportierten Kartendaten. Die Karte bleibt bei jeder Größe voll spielbar; betroffen ist nur, was zu sehen ist.

**Eine vorhandene Karte vergrößern:** `Bearbeiten → Karte vergrößern…` vergrößert die Gesamtgröße der Karte im aktiven Tab nachträglich. Nur Vergrößern wird unterstützt - Verkleinern würde riskieren, vorhandene Inseln aus den Kartengrenzen zu schieben. Neuer Platz wird immer an der Nord-/Ostkante hinzugefügt; der bestehende spielbare Bereich und jede bereits platzierte Insel bleiben unverändert.

---

### 6.2 Vorhandene Vorlage importieren

**Aus Spielarchiven** (`Datei → Import aus Spiel…`):
Öffnet einen durchsuchbaren Baum aller Kartenvorlagen-Assets, die aus den RDA-Archiven des Spiels extrahiert wurden. Wähle einen Eintrag aus und klicke auf „Importieren". Der Editor:
- Extrahiert und dekomprimiert die `.a7tinfo`-Datei automatisch mit RdaConsole und FileDBReader.
- Erkennt die Region anhand des Dateipfads (`roman` → Latium, `celtic` → Albion).
- Lädt automatisch die Vorlage der Gegenregion (z. B. Albion beim Import einer Latium-Datei).
- Erkennt die Schwierigkeit aus dem Dateinamens-Suffix (`_easy`, `_medium`, `_hard`).

**Aus `.a7tinfo`-Datei** (`Datei → .a7tinfo importieren…`):
Importiert direkt eine beliebige `.a7tinfo`-Binärdatei. Dekomprimiert sie per FileDBReader in XML und lädt das Ergebnis in den aktiven Tab.

**XML öffnen** (`Datei → XML öffnen…`):
Öffnet eine vom Editor zuvor gespeicherte XML-Datei. Kein FileDBReader erforderlich.

---

### 6.3 Die Kartenansicht

**Navigation:**

| Aktion | Geste |
|---|---|
| Zoomen | Mausrad |
| Schwenken (vertikal) | Strg + Mausrad |
| Schwenken (horizontal) | Umschalt + Mausrad |
| Freies Schwenken | Mittlere Maustaste + Ziehen |
| An Fenster anpassen | Ansicht → An Fenster anpassen |

**Koordinatensystem:** Spielkoordinaten verwenden ein standardmäßiges (gx, gy)-System, bei dem gx nach Osten und gy nach Norden zunimmt. Die untere linke Ecke (SW in der isometrischen Ansicht, d. h. die untere Spitze des Diamanten) ist (0, 0). Inselpositionen beziehen sich auf die untere linke Ecke des achsenausgerichteten Begrenzungsrahmens (AABB) der Insel.

**Overlays:**
- Ausgewählte Insel: Ein Informationspanel mit Position, Größe, Typ, Rotation und Dateipfad erscheint oben links in der Kartenansicht.
- Geist-Insel: Im Platzierungsmodus folgt ein farbkodierter Geist dem Cursor - grün bei gültiger Position, rot bei Kollisionsverletzung.
- Spielbarer Bereich: Als Diamant-Umriss dargestellt. Bei erweiterten Karten werden sowohl der volle PA als auch der Initial-PA angezeigt.

**Legende und Statistiken:** Panele in den Ecken zeigen Tastatur-/Maussteuerung, Inselgrößen- und Typabkürzungen sowie Inselzahlen pro Typ für die aktuelle Vorlage.

---

### 6.4 Inseln platzieren

Wähle eine Größe und einen Typ aus der Seitenleiste, um den **Geist-Platzierungsmodus** zu aktivieren. Der Cursor wechselt zum Fadenkreuz und eine halbtransparente Geist-Insel folgt der Mausbewegung.

**Inseltypen und gültige Größen:**

| Typ | Gültige Größen | Hinweise |
|---|---|---|
| Normal | S, M, L, XL | Hauptbauinseln |
| Startinsel | L, XL (Latium) / L (Albion) | Spielerstartinseln |
| Drittpartei | S | NPC-Fraktionsinseln |
| Pirat | M | Piratenfraktionsinseln |
| Vulkan | S, M | Vulkaninseln (nur Latium) |
| Kontinental | Nur fest | Großes DLC01-Festland |

**Platzierungssteuerung:**
- **Linksklick** - Geist-Insel an der aktuellen Position bestätigen.
- **Mittlere Maustaste** (Klick, kein Ziehen) - Geist um 90° im Uhrzeigersinn drehen. Ziehen mit der mittleren Maustaste schwenkt die Kamera ohne Rotation.
- **`.` und `,`-Taste** - ebenfalls um 90° im Uhrzeigersinn drehen.
- **`Esc`** - Platzierung abbrechen.

Der Geist wird rot angezeigt und die Platzierung gesperrt, wenn:
- Die Position eine Überlappung oder unzureichenden Abstand zu einer bestehenden Insel verursachen würde.
- Die Insel außerhalb der Spielbereichsgrenze platziert würde.
- Ein bestehender Schiffsstartpunkt überdeckt würde.

Nach der Platzierung können Inseln gezogen, in der Größe geändert (über „Bearbeiten") oder mit den Pfeiltasten neu positioniert werden.

---

### 6.5 Benutzerdefinierte (feste) Inseln

Klicke auf **📌 Benutzerdefinierte Insel platzieren…**, um den **Feste-Insel-Auswähler** zu öffnen. Dieser Dialog listet alle `RandomIsland`-Assets auf, die aus der `assets.xml` des Spiels gelesen wurden. Inseln können nach Name und Typ (Normal, Startinsel, Drittpartei, Pirat, Vulkan, Kontinental) gefiltert werden.

Wähle eine Insel aus und klicke auf **Platzieren**, um den Geist-Platzierungsmodus für diese bestimmte Inseldatei zu starten.

**Eigenschaften fester Inseln** (zugänglich über den Rechtsklick **Inseleigenschaften**-Dialog oder den Auswähler):

| Eigenschaft | Beschreibung |
|---|---|
| Kartendateipfad | `.a7m`-Dateipfad relativ zum Spieldatenwurzelverzeichnis |
| Inselbeschriftung | Optionales Label |
| Rotation | 0°, 90°, 180° oder 270° |
| Inseltyp | Normal, Startinsel, Drittpartei, Pirat, Vulkan, Kontinental |
| Fruchtbarkeit zufällig | Wenn aktiviert: Das Spiel wählt Fruchtbarkeiten zur Laufzeit (für die meisten Fälle empfohlen) |
| Fruchtbarkeits-GUIDs | Wenn „Zufällig" deaktiviert: Explizite Liste der dieser Insel zugewiesenen Fruchtbarkeits-GUIDs |

**Fruchtbarkeitszuweisung:** Feste Inseln können ihre Fruchtbarkeiten explizit festgelegt bekommen. Im Inseleigenschaften-Dialog werden Fruchtbarkeiten als Checkbox-Liste nach Typ gruppiert dargestellt (Universal, Römisch/Latium-spezifisch, Keltisch/Albion-spezifisch). Das Ankreuzen einzelner Boxen baut die GUID-Liste auf. Alternativ kann „Fruchtbarkeit zufällig" aktiviert werden, damit das Spiel Fruchtbarkeiten aus dem passenden Pool zur Laufzeit auswählt.

---

### 6.6 Schiffsstartpunkte

Wähle **Startpunkt** in der Seitenleiste (Ankersymbol), um einen Schiffsstartpunkt zu setzen - die Position, an der die Startflotte des Spielers erscheint. Jede Kartenvorlage muss mindestens einen Startpunkt enthalten.

Startpunkte:
- Werden genauso platziert und bewegt wie Inseln.
- Unterstützen Pfeiltasten-Bewegung (8 Px pro Tastendruck).
- Können per Doppelklick dupliziert werden.
- Können nicht innerhalb des Begrenzungsrahmens einer Insel platziert werden (Kollision wird in beide Richtungen geprüft: Inseln können nicht über Startpunkte geschoben werden, und Startpunkte können nicht in Inseln bewegt werden).

---

### 6.7 Verschieben und Neupositionieren

**Maus-Ziehen:** Klicke und ziehe eine Insel, um sie frei zu verschieben. Die Kollisionsprüfung erfolgt kontinuierlich während des Ziehens. Das Insel-Informations-Overlay oben links wird beim Ziehen live aktualisiert und zeigt die aktuelle Position.

**Pfeiltasten:** Mit einer oder mehreren ausgewählten Inseln kannst du mit den Pfeiltasten um den Gitter-Snap (8 Px) verschieben. Kollisionsblockierung gilt auch für Pfeiltasten-Bewegung.

**Mehrfachauswahl:** Halte Shift gedrückt und klicke, um Inseln zur Auswahl hinzuzufügen. Pfeiltasten-Bewegung gilt für alle ausgewählten Inseln gleichzeitig, wobei die Gruppe für Kollisionszwecke als starrer Körper behandelt wird.

**Auswahl rotieren:** `Strg+R` / `Umschalt+Strg+R` (oder `Bearbeiten → Auswahl 90° drehen (CW/CCW)`) dreht alle aktuell ausgewählten Inseln als starren Körper um 90° um den gemeinsamen Mittelpunkt der Gruppe. Dies ist unabhängig von der Geist-Rotation aus Abschnitt [6.4](#64-inseln-platzieren), die nur während der aktiven Platzierung einer Insel gilt.

**Gitter-Snap:** Alle Inselpositionen werden auf Vielfache von 8 Px gerundet (Spielanforderung). Positionen werden auch beim Drücken von Inseln an die Spielbereichsgrenze eingerastet.

**Rückgängig / Wiederherstellen:** Eine vollständige Rückgängig-Chronik wird geführt (`Strg+Z` / `Strg+Y`). Jede Platzierung, Bewegung, Löschung und Eigenschaftsänderung ist ein separater Schritt.

---

### 6.8 Kollisionserkennung

TAMPER erzwingt drei Kategorien räumlicher Einschränkungen:

**Insel-Insel-Abstand:**
Die achsenausgerichteten Begrenzungsrahmen (AABBs) der Inseln dürfen sich nicht überlappen.

**Extra-Groß-Insel-Randabstand (`XL_COLLISION_GAP`):**
Extra-Groß-Inseln benötigen einen zusätzlichen Abstand von 64 Px zur Spielbereichsgrenze auf allen Seiten. Dieser Abstand gilt auch bei Kollisionen zwischen Extra-Groß- und Kontinentalinseln. Er wird bei Platzierung, Ziehen und Pfeiltasten-Bewegung durchgesetzt und ist aufgrund der reduzierten Darstellungsgröße der XL-Inseln in der App erforderlich. Die Begrenzungsrahmen sind im Spiel größer, was die Sicht des Benutzers auf die Kartenvorlage beeinträchtigen würde, wenn sie unverändert blieben.

**Kontinentalinsel-Überlappung:**
Anderen Inseln ist es erlaubt, den AABB der Kontinentalinsel zu überlappen, aber *nur* innerhalb der Grenzen des `InitialPlayableArea`. Dies entspricht dem tatsächlichen Spielverhalten, bei dem der Ozean rund um das Kontinent über dem Festland platziert wird.

**Startpunkt-Kollision:**
Inseln können nicht über einen Schiffsstartpunkt geschoben werden. Umgekehrt können Startpunkte nicht in den Begrenzungsrahmen einer Insel bewegt werden.

Wenn ein Zug oder eine Platzierung gegen eine dieser Regeln verstoßen würde, wird der Geist oder Zug blockiert und der Geist rot eingefärbt.

---

### 6.9 Erweiterte (DLC01) Vorlagen

Der „Prophecies of Ash"-DLC erweitert die Latium-Karte mit einem größeren spielbaren Bereich und einer Kontinentalinsel. TAMPER unterstützt dies durch den **Erweiterte-Vorlage**-Modus.

**Funktionsweise:**
- Der volle `PlayableArea` umfasst den erweiterten DLC-aktivierten Bereich.
- Der `InitialPlayableArea` wird automatisch als `(PA.x1, PA.y1, PA.x2 − 420, PA.y2 − 420)` abgeleitet.
- Inseln, die als **Gesperrt** markiert sind, erscheinen in der Basis-Spiel-`.a7tinfo` (Vor-DLC-Inhalte, für alle Spieler sichtbar).
- Inseln, die als **Entsperrt** markiert sind, erscheinen nur in der `_enlarged.a7tinfo` (DLC-Inhalte, freigeschaltet wenn Prophecies of Ash aktiv ist).
- Der Editor exportiert beim Erstellen einer Mod automatisch sowohl die reguläre als auch die `_enlarged`-Variante.

**Inseln sperren:** Klicke mit der rechten Maustaste auf eine beliebige Insel auf der Karte und schalte **Gesperrt** um, um zu steuern, zu welcher Variante sie gehört.

---

### 6.10 Inseleigenschaften-Dialog

Zugänglich durch Auswahl einer Insel und Klick auf **Bearbeiten**, oder über das Rechtsklick-Kontextmenü.

Für **zufällige Inseln:**
- Größe und Typ ändern.
- In eine feste Insel umwandeln (öffnet den Feste-Insel-Auswähler).

Für **feste Inseln:**
- Kartendateipfad, Inselbeschriftung, Rotation, Inseltyp und Fruchtbarkeitseinstellungen ändern.
- Detaillierte Fruchtbarkeitszuweisung über Checkbox-Liste (siehe Abschnitt 6.5).

Bei der Bestätigung wird validiert: Ungültige Größen-/Typ-Kombinationen (z. B. Drittpartei auf Groß gestellt) werden mit einer beschreibenden Fehlermeldung abgelehnt.

---

### 6.11 Validierung und Limits

**Seitenleisten-Warnungen:** Die Seitenleiste zeigt kontinuierlich:
- Warnungen zur Inselanzahl pro Typ, wenn Pool-Limits überschritten werden (z. B. zu viele XG-Normalinseln).
- Einen Startinsel-Zähler, der den Fortschritt auf das Minimum von 4 anzeigt.

**Export-Warnungen:** Vor jedem Export, der eine Bereitstellung erfordert (Mod-Zip), führt der Editor eine vollständige Validierung durch und zeigt alle erkannten Probleme mit einer „Trotzdem fortfahren?"-Abfrage an. Prüfungen umfassen:
- Typ-/Größen-Regelverstöße (z. B. Pirat muss Mittel sein).
- Überschreitung der regionalen Insel-Pool-Limits.
- Inseln außerhalb des spielbaren Bereichs.
- Inseln, die zu mehr als 50 % in der Randzone liegen (weiche Warnung für Kontinentalinseln).
- Fehlende Schiffsstartpunkte (harte Sperre für Mod-Export).
- Unzureichende Startinseln (< 4, harte Sperre für Mod-Export).

---

### 6.12 Platzierungshilfen (Spiegelmodus, Kollisionen ignorieren, Formation sperren)

Der Bereich **Ansicht** in der Seitenleiste enthält drei Schalter, die symmetrische oder dichte Kartenlayouts erleichtern:

**Spiegeln:** Eine Radiobutton-Gruppe (`aus` / `2×` / `4×`), die automatisch rotierte Kopien jeder neu platzierten Insel um das Kartenzentrum herum erzeugt - `2×` fügt eine Kopie an der gegenüberliegenden Ecke hinzu, `4×` Kopien an allen vier Ecken. Gedacht, um Multiplayer-Startpositionen fair zu halten, ohne jede Ecke von Hand zu platzieren. Findet eine gespiegelte Kopie an ihrer Zielposition keinen Platz, wird sie übersprungen und nach der Platzierung eine Zusammenfassung angezeigt; mit aktiviertem „Kollisionen ignorieren" wird garantiert der vollständige Satz platziert.

**Kollisionen ignorieren:** Wenn aktiviert, können Inseln platziert, gezogen oder verschoben werden, ohne durch Überlappung mit anderen Inseln, Startpunkten oder der Spielbereichsgrenze blockiert zu werden. Nützlich, um ein Layout schnell grob zu entwerfen, bevor der Abstand manuell bereinigt wird.

**Formation an Rändern sperren:** Normalerweise wird eine Auswahl, die teilweise aus dem spielbaren Bereich hinausbewegt würde, als Ganzes zurück in die Grenzen geklemmt. Ist dieser Schalter aktiviert, kann sich die Gruppe frei bewegen, ohne dieses Klemmen - praktisch, wenn eine Mehrinsel-Formation absichtlich über die Grenze hinausragen soll.

---

## 7. Speichern und Exportieren

### 7.1 XML speichern / laden

`Datei → XML speichern` / `Datei → XML speichern unter…` - speichert die Vorlage des **aktiven Tabs** als einfach lesbares XML. Dies ist das native Arbeitsformat des Editors. Zum Speichern und erneuten Öffnen von XML-Dateien ist kein FileDBReader erforderlich.

`Datei → XML öffnen…` - öffnet eine XML-Datei in den aktiven Tab.

Das XML-Format ist die dekomprimierte Darstellung der `.a7tinfo`-Binärdatei - alle Felder werden direkt abgebildet.

### 7.2 Als .a7tinfo exportieren

`Datei → .a7tinfo exportieren…` - exportiert die Vorlage des **aktiven Tabs** und komprimiert sie per FileDBReader in das binäre `.a7tinfo`-Format. Das Ergebnis kann direkt in die Ordnerstruktur einer Mod abgelegt und vom Spiel geladen werden.

FileDBReader muss konfiguriert sein (siehe Abschnitt 4).

### 7.3 PNG exportieren

`Datei → PNG exportieren…` (oder der PrtScn-Shortcut) - rendert die Kartenansicht des aktiven Tabs als PNG-Bild, beschnitten auf den spielbaren Bereich. Nützlich für Dokumentation und Vorschaubilder.

Der Regionsname (z. B. „Latium") wird standardmäßig oben links in das Bild eingeblendet; deaktivierbar über `Optionen → Region Name in PNG-Files`.

### 7.4 Als spielbare Mod exportieren (.zip)

`Datei → Als Mod exportieren (.zip)…` (oder Strg+S) - der umfassendste Exportweg. Verpackt sowohl die Latium- als auch die Albion-Vorlage in eine sofort installierbare Anno 117-Mod. Der Build läuft in einem Hintergrund-Thread hinter einem Fortschrittsfenster, sodass die Benutzeroberfläche währenddessen reaktionsfähig bleibt - große Kartengrößen benötigen dabei merklich länger als die vanilla Standardwerte (2048/2688).

**Was erzeugt wird:**

- Drei `.a7tinfo`-Schwierigkeitsvarianten pro Region (`easy`, `medium`, `hard`).
- Für erweiterte Latium-Karten: zusätzlich drei `_enlarged.a7tinfo`-Varianten (voller DLC-aktivierter PA).
- Vorkompilierte `.a7t`-/`.a7te`-Binärvorlagen (im Editor enthalten).
- `assets.xml` mit vollständigen `MapTemplate`-Asset-Definitionen inkl. Horizont-Inseln und DLC-Einstellungen.
- `modinfo.json` mit Mod-Name, Beschreibung, GUID-Bereich und Abhängigkeitsinformationen.
- Locale-XML-Dateien für alle 12 unterstützten Sprachen (Name und Beschreibung werden auf Englisch vorausgefüllt; für andere Sprachen eigene Übersetzungstools verwenden).

**Dialog-Optionen:**

| Feld | Hinweise |
|---|---|
| Mod-Name | Kleinbuchstaben, nur Bindestriche, keine Unterstriche. Wird als Dateiname und Mod-ID verwendet. |
| Beschreibung | Englische Beschreibung für den Mod-Manager. |
| Start-GUID | Die erste GUID im Bereich. Sieben aufeinanderfolgende GUIDs werden reserviert. |
| Persönlicher GUID-Bereich | Ein privater Testbereich (2001001000–2001009999). Exporte in diesem Bereich werden direkt installiert; kein teilbares Zip wird erstellt. |
| Eigener reservierter Bereich | Gib einen community-registrierten GUID-Bereich für die öffentliche Veröffentlichung ein. |
| Schwierigkeiten automatisch ableiten | Wenn aktiviert, werden Mittel- und Schwer-Varianten algorithmisch durch Skalierung der Inselgrößen generiert, anstatt die Quellvorlage identisch zu kopieren (siehe unten). |
| Direktinstallation | Falls verfügbar, installiert den Mod-Ordner sofort nach dem Erstellen direkt in das `mods/`-Verzeichnis des Spiels. |

**Schwierigkeiten automatisch ableiten:**
Wenn „Andere Schwierigkeitsvarianten automatisch aus dieser Karte ableiten" aktiviert ist, wendet der Editor die folgenden Inselgrößentransformationen an, um die fehlenden Schwierigkeitsvarianten aus der Quellvorlage zu erzeugen:

| Konvertierung | Normalinsel-Änderungen | Startinsel-Änderungen |
|---|---|---|
| Leicht → Mittel | Jede 2. G→M; jede 4. M→K | Keine Änderung (G ist Minimum) |
| Mittel → Schwer | Alle XG→G; jede 2. G→M; jede 2. M→K | XG→G |
| Schwer → Mittel | Alle G→XG; jede 2. M→G; jede 2. K→M | G→XG |
| Mittel → Leicht | Jede 2. M→G; jede 4. K→M | Keine Änderung |

Leicht→Schwer- und Schwer→Leicht-Konvertierungen verlaufen durch Mittel. Feste Inseln und zufällige Inseln, die nicht vom Typ Normal sind (Pirat, Drittpartei, Vulkan), werden nicht in der Größe geändert.

---

## 8. Insel-Referenz

### Pool-Limits (zufällige Inseln pro Region)

| Typ | Größe | Latium | Albion |
|---|---|---|---|
| Normal | Extra Groß | 4 | - |
| Normal | Groß | 8 | 8 |
| Normal | Mittel | 8 | 7 |
| Normal | Klein | 7 | 7 |
| Drittpartei | (beliebig) | 2 | 2 |
| Pirat | (beliebig) | 1 | 1 |
| Vulkan | Mittel | 3 | - |
| Vulkan | Klein | 2 | - |

Feste Inseln werden nicht auf diese Limits angerechnet.

### Inselgrößen-Referenz (Spielpixel)

| Größenbezeichnung | AABB-Seite (Spielpx) |
|---|---|
| Klein | 256 |
| Mittel | 320 |
| Groß | 435 |
| Extra Groß | 435 |
| Kontinental | 768 |

Hinweis: Groß und Extra Groß teilen die gleiche AABB-Dimension; sie unterscheiden sich im Pool, aus dem sie schöpfen, und in der Inselgrafik. Den Insel-Dateien zufolge sind beide Inseltypen eigentlich 512 Pixel groß, allerdings ist bei der L-Insel viel Leerraum enthalten, beim XL-Modell etwas weniger. Ich habe mich daher entschlossen, die Anzeigegröße zu verringern, da die ursprüngliche Seitenlänge bei importierten Standard-Kartenvorlagen zu erheblichen visuellen Überlappungen führen würde.

---

## 9. Technische Hinweise

### Dateiformat

`.a7tinfo`-Dateien sind komprimierte Binärdateien im FileDB-Format von Ubisoft. Der Editor arbeitet ausschließlich mit der dekomprimierten XML-Darstellung und delegiert Komprimierung/Dekomprimierung an **FileDBReader**. Die XML-Struktur folgt Ubisofts `MapTemplate`-Asset-Schema, wie in den Reverse-Engineering-Bemühungen der Community dokumentiert.

### Koordinatensystem

Spielkoordinaten sind achsenausgerichtete Ganzzahlen in „Spielpixeln". Die Karte ist ein quadratisches Raster; (0, 0) ist die südwestliche Ecke (untere Spitze in der isometrischen Ansicht). Inseln werden durch die untere linke Ecke ihrer Position dargestellt. Alle Inselpositionen müssen durch 8 teilbar sein.

### Insel-Registry

Beim Start parst der Editor asynchron die `assets.xml` des Spiels (in das Benutzerdatenverzeichnis extrahiert), um den Katalog des Feste-Insel-Auswählers aufzubauen. Falls `assets.xml` nicht verfügbar ist (Spiel noch nicht extrahiert), zeigt der Auswähler eine Aufforderung zur Ausführung der Extraktion. Die Registry lädt im Hintergrund und blockiert die Benutzeroberfläche nicht.

### PyInstaller-Build

Die Standalone-Binary wird mit PyInstaller erstellt:

```bash
pyinstaller anno117-map-editor.spec
```

Die Spec-Datei bündelt das gesamte `data/`-Verzeichnis und die Mod-Vorlagenordner (`[Map] $ModName (TAMPER)/`) in die Einzeldatei-Executable.

---

## 10. Lizenz und Credits

TAMPER ist ein Community-Tool und steht in **keiner Verbindung mit Ubisoft Mainz und wird von diesen nicht unterstützt**.

Anno 117: Pax Romana ist eine Marke der Ubisoft Entertainment.

### Abhängigkeiten:

| Tool / Bibliothek | Autor | Lizenz |
|---|---|---|
| [FileDBReader](https://github.com/anno-mods/FileDBReader) | anno-mods | MIT |
| [RdaConsole](https://github.com/anno-mods/RdaConsole) | anno-mods | MIT |

### Lizenz:
MIT

### Credits:
- Taubenangriff und Jakob für ihre hervorragende Arbeit an der bestehenden Tool-Pipeline
- Claude Code dafür, dass er meine Vision eines Karteneditors verwirklicht hat

---

*Für Fragen, Fehlerberichte und Beiträge öffne bitte ein Issue oder einen Pull Request im [GitHub-Repository](https://github.com/taludas/anno-117-map-editor).*
