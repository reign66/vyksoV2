"""Notifications WhatsApp via une passerelle OpenWA (openwa / wa-automate).

Module autonome (stdlib + httpx uniquement). Les notifications ne doivent
JAMAIS casser un flux métier : aucune fonction de ce module ne lève
d'exception — en cas d'erreur, on loggue et on retourne False.

Variables d'environnement requises (les 4) :
- OPENWA_URL        : URL de base de la passerelle, ex. http://host:2785
- OPENWA_API_KEY    : clé API (header X-API-Key)
- OPENWA_SESSION_ID : identifiant de session OpenWA
- OPENWA_CHAT_ID    : destinataire, ex. 33612345678@c.us
"""

import os
import logging
import threading

import httpx

logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = ("OPENWA_URL", "OPENWA_API_KEY", "OPENWA_SESSION_ID", "OPENWA_CHAT_ID")


def whatsapp_enabled() -> bool:
    """True si les 4 variables d'environnement OpenWA sont définies (non vides)."""
    return all(os.getenv(var) for var in _REQUIRED_ENV_VARS)


def send_whatsapp(text: str) -> bool:
    """Envoie un message texte WhatsApp via la passerelle OpenWA.

    POST {OPENWA_URL}/api/sessions/{OPENWA_SESSION_ID}/messages/send-text
    Header X-API-Key, JSON {"chatId": OPENWA_CHAT_ID, "text": text}, timeout 10s.

    Ne lève JAMAIS d'exception : retourne True en cas de succès, False sinon
    (notification désactivée, erreur réseau, erreur HTTP...).
    """
    try:
        if not whatsapp_enabled():
            logger.debug("WhatsApp notifications disabled (missing OPENWA_* env vars)")
            return False

        base_url = os.getenv("OPENWA_URL", "").rstrip("/")
        session_id = os.getenv("OPENWA_SESSION_ID")
        url = f"{base_url}/api/sessions/{session_id}/messages/send-text"

        response = httpx.post(
            url,
            headers={"X-API-Key": os.getenv("OPENWA_API_KEY")},
            json={"chatId": os.getenv("OPENWA_CHAT_ID"), "text": text},
            timeout=10.0,
        )
        if response.status_code >= 400:
            logger.warning(
                "WhatsApp notification failed: HTTP %s — %s",
                response.status_code,
                response.text[:500],
            )
            return False
        return True
    except Exception as e:  # noqa: BLE001 — les notifications ne doivent jamais casser le flux métier
        logger.warning("WhatsApp notification error: %s", e)
        return False


def notify_event(event: str, details: dict) -> bool:
    """Formate un message lisible en français et l'envoie sur WhatsApp.

    Format :
        🔔 Vykso — {event}
        clé: valeur
        ...

    Envoi FIRE-AND-FORGET dans un thread daemon : les appelants sont des
    coroutines (webhook Stripe, jobs vidéo) et un POST synchrone de 10 s
    gèlerait l'event loop. Retourne True si l'envoi a été déclenché
    (notifications activées), False sinon. Ne lève jamais d'exception.
    """
    try:
        if not whatsapp_enabled():
            return False
        lines = [f"🔔 Vykso — {event}"]
        for key, value in (details or {}).items():
            lines.append(f"{key}: {value}")
        text = "\n".join(lines)
        threading.Thread(target=send_whatsapp, args=(text,), daemon=True).start()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("notify_event error: %s", e)
        return False
