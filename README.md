# 🤖 Nexo 3.0 — Asistente Personal con Inteligencia Emocional para Windows

**Nexo 3.0** es un asistente de IA para Windows que no solo ejecuta comandos y automatiza tu PC, sino que también **entiende tus emociones** y se adapta a tu estado de ánimo.

Basado en el motor de Gemini de Google, con interfaz holográfica interactiva, control por voz, y un sistema de detección emocional que lo hace único.

---

## ✨ Características Principales

### 🧠 Inteligencia Emocional
Nexo 3.0 detecta cómo te sentís (tristeza, enojo, ansiedad, felicidad) y **adapta su tono y respuestas**:
- **Triste** → Tono calmado, palabras de apoyo, sugiere música relajante
- **Enojado** → Tono sereno, técnicas de respiración, sin confrontación
- **Ansioso** → Tono estructurado, técnicas de anclaje, organización
- **Feliz** → Celebra con vos, amplifica lo positivo

### 🎤 Control por Voz y Texto
Hablá con Nexo como si fuera una persona real. Entiende contexto, mantiene conversaciones y responde con voz natural.

### 🖥️ Automatización de PC
- Abrir aplicaciones y archivos
- Controlar ventanas y escritorio
- Controlar Spotify, YouTube, Chrome
- Apagar, reiniciar, suspender el equipo
- Monitorear sistema (CPU, RAM, batería)

### 🌐 Servicios Externos
- Clima, búsqueda web, YouTube
- Google Maps, recordatorios
- Control de hogar inteligente
- Y mucho más...

### 🎨 Interfaz Holográfica
Interfaz visual inmersiva con partículas animadas, orb interactivo, widgets flotantes y modo de accesibilidad.

---

## 📋 Requisitos del Sistema

| Requisito | Especificación |
|-----------|---------------|
| **Sistema** | Windows 10 u 11 (64 bits) |
| **Python** | 3.12 |
| **RAM** | 4 GB mínimo (8 GB recomendado) |
| **Disco** | 500 MB libres |
| **Internet** | Conexión requerida para Gemini API |
| **Micrófono** | Para control por voz |

---

## 🚀 Instalación Rápida

### Opción 1: Ejecutar desde código fuente (recomendado)

1. **Instalá Python 3.12** desde [python.org](https://www.python.org/downloads/) (marcá "Add Python to PATH")

2. **Descargá Nexo 3.0**:
   ```
   git clone https://github.com/Mikutabby/nexo-windows.git
   cd nexo-windows
   ```
   O descargá el ZIP desde la página del repositorio y extraelo.

3. **Instalá las dependencias**:
   ```
   pip install -r requirements.txt
   ```

4. **Obtené tu API Key de Gemini**:
   - Andá a https://aistudio.google.com/apikey
   - Hacé clic en "Create API Key"
   - Copiá la clave

5. **Configurá Nexo**:
   - Abrí `config/api_keys.json`
   - Reemplazá `"TU_API_KEY_AQUI"` con tu clave de Gemini
   - Configurá tu zona horaria si es necesario

6. **Ejecutá Nexo**:
   ```
   python main.py
   ```

### Opción 2: Descargar el instalador (.exe)

> ⚡ *Próximamente* — Estamos preparando un instalador automatizado. Por ahora, usá la Opción 1.

Si querés generar tu propio `.exe` portátil:
```
pip install pyinstaller
pyinstaller --onefile --windowed --icon=assets/nexo_icono.ico --name "Nexo 3.0" main.py
```
El ejecutable se creará en la carpeta `dist/`.

---

## 🎯 Primeros Pasos

1. Ejecutá Nexo con `python main.py`
2. Esperá a que aparezca la interfaz holográfica
3. Hablá o escribí comandos como:
   - *"Abrí Spotify"*
   - *"¿Cómo está el clima?"*
   - *"Buscá en internet sobre..."*
   - *"Poné música relajante"*
   - *"Estoy teniendo un mal día..."* (Nexo lo detectará emocionalmente)

---

## 🧠 Sistema de Detección Emocional

Nexo 3.0 incluye un motor de inteligencia emocional que analiza en tiempo real el texto que escribís o decís:

- **Palabras clave** → El diccionario emocional reconoce cientos de expresiones
- **Emoticonos** → `:(`, `:'(`, etc.
- **Intensidad** → Signos de exclamación, repeticiones
- **Contexto** → El historial emocional detecta tendencias

El estado emocional se inyecta directamente en el prompt de Gemini para que las respuestas sean auténticamente empáticas.

---

## 🔧 Estructura del Proyecto

```
nexo-3.0/
├── main.py                  # Cerebro principal (orquestador Gemini)
├── ui.py                    # Interfaz holográfica (PyQt6 + partículas)
├── emotion_detector.py      # 🆕 Motor de inteligencia emocional
├── beta_config.py           # Configuración beta
├── sounds.py                # Sistema de sonidos
├── launcher.pyw             # Lanzador
├── requirements.txt         # Dependencias
├── core/
│   ├── prompt.txt           # Prompt del sistema (con directivas emocionales)
│   ├── model_router.py      # Enrutamiento de modelos IA
│   └── crypto.py            # Encriptación de datos locales
├── actions/                 # 30+ módulos de automatización
│   ├── computer_control.py
│   ├── browser_control.py
│   ├── spotify_control.py
│   ├── smart_home.py
│   └── ... (30 módulos más)
├── memory/                  # Memoria persistente
├── assets/                  # Iconos, sonidos, modelos
└── config/                  # Configuración (API keys, etc.)
```

---

## 📝 Notas Importantes

- **Privacidad**: Tus datos se guardan localmente, encriptados. Solo las consultas a Gemini viajan a Google.
- **API Key**: La clave de Gemini es **gratuita** con límites generosos.
- **Beta**: Nexo 3.0 está en desarrollo activo. Algunas funciones pueden estar en refinamiento.

---

## 🤝 Contribuciones

¿Ideas, bugs, mejoras? Abrí un issue o mandá un PR. Toda contribución es bienvenida.

---

## 📜 Licencia

MIT License — podés usar, modificar y distribuir libremente.

---

## 🙌 Créditos

- **Nexo 3.0** fue creado por [Mikutabby](https://github.com/Mikutabby) como evolución del ecosistema Nexo
- Basado en la arquitectura de asistentes de IA conversacionales con Gemini
- Interfaz holográfica con PyQt6 y partículas en tiempo real

---

⭐ **Si te gustó Nexo, no olvides dejar una estrella en el repositorio**
