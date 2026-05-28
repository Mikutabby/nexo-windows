"""
emotion_detector.py — Nexo 3.0 Emotional Intelligence Module
Detecta estados emocionales del usuario y sugiere respuestas adaptativas.

Arquitectura:
  1. Análisis por palabras clave (rápido, offline)
  2. Análisis por LLM (profundo, usa Gemini si está disponible)
  3. Estrategias de respuesta según emoción detectada
  4. Historial emocional para detectar tendencias
"""

import json
import re
import time
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Optional

# ─── Constantes ───────────────────────────────────────────────────────────────

EMOTION_HISTORY_FILE = Path(__file__).parent / "memory" / "emotion_history.json"
MAX_HISTORY = 50  # entradas en el historial

EMOTIONS = {
    "felicidad": {
        "keywords": [
            "feliz", "contento", "alegre", "genial", "excelente", "maravilloso",
            "joya", "perfecto", "me encanta", "amo", "fantástico", "increíble",
            "bien", "súper", "re cont", "felicidad", "celebrar", "logré", "conseguí",
            ":)","=)", ":D", "❤️", "🎉"
        ],
        "pesos_positivos": 2,
        "pesos_negativos": 0,
        "intensidad_base": 0.6,
    },
    "tristeza": {
        "keywords": [
            "triste", "tristeza", "deprimido", "depresion", "depresión", "mal",
            "llorar", "lloro", "llorando", "llorique", "desanimado", "sin ganas",
            "no puedo más", "agotado", "cansado de todo", "solo", "solitario",
            "vacío", "vacía", "abandonado", "melancolía", "nostalgia",
            ":(", ":'(", "ya no", "terminó", "perdí", "duele", "dolor",
            "sufro", "sufriendo", "sufrimiento", "desesperanza", "sin sentido",
            "no sirvo", "no valgo", "no tengo", "me falta"
        ],
        "pesos_positivos": 0,
        "pesos_negativos": 2,
        "intensidad_base": 0.7,
    },
    "enojo": {
        "keywords": [
            "enojado", "enojada", "enojadisimo", "enojadísimo", "furioso", "rabia",
            "odio", "molesto", "fastidio", "harto", "no aguanto", "insoportable",
            "estúpido", "imbécil", "idiota", "maldito", "puta", "carajo", "mierda",
            "cojones", "cabreado", "enfadado", "irritado", "frustrado", "qué rabia",
            "injusticia", "no es justo", "basura", "asqueroso", "indignado",
            "cabreado", "caliente", "arde", "furia", "colérico", "hostia",
            "joder", "coño", "la puta", "puto"
        ],
        "pesos_positivos": 0,
        "pesos_negativos": 3,
        "intensidad_base": 0.8,
    },
    "ansiedad": {
        "keywords": [
            "ansiedad", "ansioso", "nervioso", "preocupado", "estresado",
            "estrés", "no puedo", "miedo", "temor", "pánico", "angustia",
            "desesperado", "acelerado", "corazón", "respira", "calma",
            "tranquilo", "relajado", "insomnio", "no duermo", "pienso demasiado",
            "abrumado", "saturado", "colapsar", "colapso"
        ],
        "pesos_positivos": 0,
        "pesos_negativos": 2,
        "intensidad_base": 0.75,
    },
    "agradecimiento": {
        "keywords": [
            "gracias", "agradecido", "agradezco", "te agradezco", "muchas gracias",
            "mil gracias", "te lo agradezco", "grato", "agradecimiento",
            "thank", "thanks", "appreciate"
        ],
        "pesos_positivos": 1,
        "pesos_negativos": 0,
        "intensidad_base": 0.4,
    },
    "neutro": {
        "keywords": [],
        "pesos_positivos": 0,
        "pesos_negativos": 0,
        "intensidad_base": 0.0,
    }
}

RESPONSE_STRATEGIES = {
    "tristeza": {
        "tono": "calmado, suave, comprensivo, pausado",
        "acciones_sugeridas": [
            "🎵 Reproducir música relajante (lofi, chillhop, piano)",
            "🌿 Sugerir una pausa o respiración profunda",
            "💬 Palabras de apoyo y validación emocional",
            "📝 Ofrecer escribir un diario o desahogarse"
        ],
        "frases_evitar": [
            "no estés triste", "anímate", "podría ser peor",
            "todo pasa por algo", "sé positivo"
        ],
        "prioridad": "contención emocional > solución"
    },
    "enojo": {
        "tono": "sereno, pausado, neutral, respetuoso",
        "acciones_sugeridas": [
            "🧘 Ejercicio de respiración guiada (4-7-8)",
            "🚶 Sugerir una caminata corta o cambio de ambiente",
            "🎮 Redirigir a actividad distractora (música, juego)",
            "💨 Técnica de descarga: contar hasta 10"
        ],
        "frases_evitar": [
            "cálmate", "relájate", "no es para tanto",
            "exageras", "tranquilo", "baja los humos"
        ],
        "prioridad": "desescalada > validación"
    },
    "ansiedad": {
        "tono": "tranquilo, pausado, estructurado, seguro",
        "acciones_sugeridas": [
            "🌬️ Respiración guiada (caja: 4-4-4-4)",
            "📋 Hacer lista de cosas controlables",
            "🎵 Música ambiental o sonidos de naturaleza",
            "✋ Técnica de anclaje: 5 cosas que ves, 4 que tocas..."
        ],
        "frases_evitar": [
            "preocuparse no sirve", "es mental", "tranquilízate",
            "no pienses en eso", "exageras"
        ],
        "prioridad": "anclaje > validación > solución"
    },
    "felicidad": {
        "tono": "cálido, enérgico, celebratorio, positivo",
        "acciones_sugeridas": [
            "🎉 Celebrar con el usuario",
            "🎵 Subir música alegre si corresponde",
            "💬 Amplificar lo positivo, preguntar más"
        ],
        "frases_evitar": [
            "no es para tanto", "ya se te pasará"
        ],
        "prioridad": "amplificar > celebrar"
    },
    "agradecimiento": {
        "tono": "cálido, humilde, genuino",
        "acciones_sugeridas": [
            "💬 Responder con calidez genuina",
            "✨ Ofrecer ayuda adicional si aplica"
        ],
        "frases_evitar": [
            "no hay problema", "es mi trabajo", "de nada"
        ],
        "prioridad": "conexión genuina"
    },
    "neutro": {
        "tono": "normal, profesional, según contexto",
        "acciones_sugeridas": [],
        "frases_evitar": [],
        "prioridad": "ejecución normal"
    }
}


# ─── Detector de emociones ────────────────────────────────────────────────────

class EmotionDetector:
    """Detecta estados emocionales del usuario mediante análisis de texto."""

    def __init__(self):
        self.history = self._load_history()
        self._last_emotion = "neutro"
        self._last_confidence = 0.0

    def _load_history(self) -> deque:
        """Carga historial emocional desde archivo JSON."""
        try:
            if EMOTION_HISTORY_FILE.exists():
                data = json.loads(EMOTION_HISTORY_FILE.read_text(encoding="utf-8"))
                return deque(data, maxlen=MAX_HISTORY)
        except Exception as e:
            print(f"[EMOTION] Error loading history: {e}")
        return deque(maxlen=MAX_HISTORY)

    def _save_history(self):
        """Guarda historial emocional."""
        try:
            EMOTION_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            EMOTION_HISTORY_FILE.write_text(
                json.dumps(list(self.history), ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception as e:
            print(f"[EMOTION] Error saving history: {e}")

    def analyze(self, text: str) -> dict:
        """
        Analiza el texto del usuario y devuelve el estado emocional detectado.
        
        Returns:
            dict con:
            - emotion: str (emoción principal)
            - confidence: float (0.0 - 1.0)
            - intensity: float (qué tan fuerte es la emoción)
            - strategies: dict (estrategias de respuesta sugeridas)
            - all_scores: dict (puntaje de cada emoción)
        """
        if not text or not text.strip():
            return {
                "emotion": "neutro",
                "confidence": 1.0,
                "intensity": 0.0,
                "strategies": RESPONSE_STRATEGIES["neutro"],
                "all_scores": {"neutro": 1.0}
            }

        text_lower = text.lower()
        scores = {}

        for emotion_name, config in EMOTIONS.items():
            score = 0.0
            matches = 0
            for keyword in config["keywords"]:
                if keyword in text_lower:
                    matches += 1
                    # Peso según posición y contexto
                    score += config["pesos_positivos"] if config["pesos_positivos"] > 0 else 0
                    score += config["pesos_negativos"] if config["pesos_negativos"] > 0 else 0

            # Normalizar: más matches = más confianza
            if matches > 0:
                normalized = min(1.0, (matches * config["intensidad_base"]))
                # Bonus si hay múltiples keywords de la misma emoción
                if matches >= 3:
                    normalized = min(1.0, normalized * 1.3)
                scores[emotion_name] = normalized
            else:
                scores[emotion_name] = 0.0

        # Detectar negación (no + palabra emocional = invertir)
        negacion_patterns = [
            r"no\s+(estoy\s+|me\s+siento\s+|tengo\s+)?(triste|enojado|ansioso|feliz)",
            r"nunca\s+(estoy|me\s+siento)",
            r"ni\s+(triste|enojado|ansioso)"
        ]
        for pattern in negacion_patterns:
            if re.search(pattern, text_lower):
                # Invertir las puntuaciones
                for em in scores:
                    if em in ["tristeza", "enojo", "ansiedad", "felicidad"]:
                        scores[em] = max(0, scores[em] - 0.5)

        # Detectar signos de exclamación (intensidad)
        exclamations = text.count("!") + text.count("¡")
        intensidad_extra = min(0.3, exclamations * 0.1)

        # Determinar emoción principal
        if not scores or all(v == 0 for v in scores.values()):
            scores["neutro"] = 1.0

        emotion = max(scores, key=scores.get)
        confidence = scores[emotion]

        # Ajustar por intensidad de signos
        if intensidad_extra > 0 and emotion != "neutro":
            confidence = min(1.0, confidence + intensidad_extra)

        # Guardar en historial
        entry = {
            "timestamp": datetime.now().isoformat(),
            "text": text[:100],
            "emotion": emotion,
            "confidence": round(confidence, 2),
            "scores": {k: round(v, 2) for k, v in scores.items()}
        }
        self.history.append(entry)
        self._save_history()

        self._last_emotion = emotion
        self._last_confidence = confidence

        return {
            "emotion": emotion,
            "confidence": round(confidence, 2),
            "intensity": round(confidence, 2),
            "strategies": RESPONSE_STRATEGIES.get(emotion, RESPONSE_STRATEGIES["neutro"]),
            "all_scores": scores
        }

    def get_last_emotion(self) -> tuple[str, float]:
        """Devuelve la última emoción detectada y su confianza."""
        return self._last_emotion, self._last_confidence

    def get_emotional_trend(self) -> dict:
        """
        Analiza tendencias emocionales en el historial reciente.
        Útil para detectar patrones (ej: varias veces triste = depresión).
        """
        if len(self.history) < 3:
            return {"trend": "insufficient_data", "message": "Aún no hay suficientes datos."}

        recent = list(self.history)[-10:]
        emotions_count = {}
        for entry in recent:
            em = entry["emotion"]
            emotions_count[em] = emotions_count.get(em, 0) + 1

        most_common = max(emotions_count, key=emotions_count.get)
        total = len(recent)
        percentage = (emotions_count[most_common] / total) * 100

        if percentage > 60 and most_common in ["tristeza", "ansiedad"]:
            return {
                "trend": "alerta",
                "emotion": most_common,
                "percentage": percentage,
                "message": f"El usuario ha mostrado {most_common} en el {percentage:.0f}% de las interacciones recientes."
            }
        elif percentage > 40 and most_common != "neutro":
            return {
                "trend": "notable",
                "emotion": most_common,
                "percentage": percentage,
                "message": f"Tendencia a {most_common} en el {percentage:.0f}% de las interacciones."
            }
        return {
            "trend": "estable",
            "emotion": most_common,
            "percentage": percentage,
            "message": "Estado emocional estable."
        }

    def generate_emotional_context(self, text: str) -> Optional[str]:
        """
        Genera un contexto emocional para inyectar en el prompt de Gemini.
        Si la emoción es fuerte, devuelve un string con instrucciones para Gemini.
        Si es neutro, devuelve None.
        """
        result = self.analyze(text)
        emotion = result["emotion"]
        confidence = result["confidence"]
        strategies = result["strategies"]

        if emotion == "neutro" or confidence < 0.3:
            return None

        tono = strategies.get("tono", "normal")
        prioridad = strategies.get("prioridad", "normal")

        # Construir contexto para Gemini
        context = (
            f"[CONTEXTO EMOCIONAL - CONFIANZA: {confidence:.0%}]\n"
            f"El usuario parece estar experimentando {emotion}.\n"
            f"TONO RECOMENDADO: {tono}.\n"
            f"PRIORIDAD: {prioridad}.\n"
            f"EVITAR frases como: {', '.join(strategies.get('frases_evitar', ['ninguna']))}.\n"
        )

        if emotion in ["tristeza", "ansiedad"]:
            context += (
                "Ofrece apoyo genuino, validá sus sentimientos, "
                "preguntá si necesita algo específico.\n"
            )
        elif emotion == "enojo":
            context += (
                "No contradigas al usuario ni minimices su enojo. "
                "Respondé de manera calmada y respetuosa. "
                "Si es apropiado, sugerí una pausa o técnica de respiración.\n"
            )
        elif emotion == "felicidad":
            context += (
                "Celebrá con el usuario, mostrate contento por él/ella. "
                "Preguntá más sobre lo que le hace feliz.\n"
            )

        return context


# ─── Instancia global ─────────────────────────────────────────────────────────

_detector: Optional[EmotionDetector] = None

def get_detector() -> EmotionDetector:
    """Obtiene la instancia global del detector emocional."""
    global _detector
    if _detector is None:
        _detector = EmotionDetector()
    return _detector

def analyze_emotion(text: str) -> dict:
    """Función helper para análisis rápido."""
    return get_detector().analyze(text)

def get_emotional_context(text: str) -> Optional[str]:
    """Función helper para obtener contexto emocional."""
    return get_detector().generate_emotional_context(text)
