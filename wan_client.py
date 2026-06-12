"""Client HTTP pour un micro-service auto-hébergé de génération vidéo Wan 2.x.

Ce module définit le CONTRAT attendu du serveur (à héberger sur une machine
GPU). Tout wrapper/serveur implémentant ce contrat fonctionnera avec ce client.

Variables d'environnement :
- WAN_ENDPOINT : URL de base du micro-service, ex. http://gpu-box:9000 (obligatoire)
- WAN_API_KEY  : clé API optionnelle (envoyée en header "Authorization: Bearer <clé>")
- VIDEO_POLL_TIMEOUT_SECONDS : timeout global de polling (défaut 900s = 15 min)

═══════════════════════════════════════════════════════════════════════════
CONTRAT DU SERVEUR (à implémenter côté GPU)
═══════════════════════════════════════════════════════════════════════════

1) POST {WAN_ENDPOINT}/generate
   Headers : Content-Type: application/json
             Authorization: Bearer <WAN_API_KEY>   (seulement si une clé est configurée)
   Corps JSON :
       {
         "prompt":  "<description textuelle de la vidéo>",   # str, obligatoire
         "seconds": 8,                                       # int, durée souhaitée
         "size":    "1280x720",                              # str, "LARGEURxHAUTEUR"
         "image":   "<base64>"                               # str optionnel : image
                                                             #   de départ (image-to-video),
                                                             #   encodée en base64 standard
       }
   Réponse 200 JSON :
       { "job_id": "<identifiant unique du job>" }

2) GET {WAN_ENDPOINT}/jobs/{job_id}
   Headers : Authorization: Bearer <WAN_API_KEY>  (si clé configurée)
   Réponse 200 JSON :
       {
         "status": "queued" | "processing" | "completed" | "failed",
         # si status == "completed", AU MOINS UN des deux champs :
         "video_url": "<URL http(s) téléchargeable du MP4>",
         "video_b64": "<MP4 encodé en base64>",
         # si status == "failed" :
         "error": "<message d'erreur lisible>"
       }

   Le client interroge cet endpoint toutes les 10 secondes jusqu'à
   "completed"/"failed" ou expiration de VIDEO_POLL_TIMEOUT_SECONDS.
═══════════════════════════════════════════════════════════════════════════
"""

import os
import time
import base64
from typing import Optional, Union

import httpx


def _poll_timeout_seconds() -> float:
    """Timeout global de polling (env VIDEO_POLL_TIMEOUT_SECONDS, défaut 900s = 15 min)."""
    try:
        return float(os.getenv("VIDEO_POLL_TIMEOUT_SECONDS", "900"))
    except (TypeError, ValueError):
        return 900.0


def wan_available() -> bool:
    """True si le provider Wan est configuré (WAN_ENDPOINT défini et non vide)."""
    return bool(os.getenv("WAN_ENDPOINT"))


class WanVideoClient:
    """Client pour le micro-service Wan 2.x auto-hébergé (voir contrat dans le
    docstring du module). Même forme d'appel que les autres clients vidéo
    (VeoAIClient, SoraClient)."""

    def __init__(self, endpoint: Optional[str] = None, api_key: Optional[str] = None):
        endpoint = endpoint or os.getenv("WAN_ENDPOINT")
        if not endpoint:
            raise RuntimeError("WAN_ENDPOINT is not set")
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key or os.getenv("WAN_API_KEY")

    def _headers(self) -> dict:
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def generate_video_and_wait(
        self,
        prompt: str,
        input_image_bytes: Optional[bytes] = None,
        seconds: int = 8,
        size: str = "1280x720",
        download_path: Optional[str] = None,
    ) -> Union[str, bytes]:
        """Lance une génération Wan, attend la fin, puis récupère le MP4.

        Args:
            prompt: description textuelle de la vidéo
            input_image_bytes: image de départ optionnelle (image-to-video),
                envoyée en base64 dans le champ "image"
            seconds: durée souhaitée en secondes
            size: dimensions "LARGEURxHAUTEUR", ex. "1280x720"
            download_path: si fourni, écrit le MP4 à ce chemin et retourne le
                chemin ; sinon retourne les bytes du MP4

        Returns:
            download_path (str) si fourni, sinon les bytes de la vidéo

        Raises:
            RuntimeError: job en échec ou réponse serveur invalide
            TimeoutError: dépassement de VIDEO_POLL_TIMEOUT_SECONDS
        """
        payload = {
            "prompt": prompt,
            "seconds": seconds,
            "size": size,
        }
        if input_image_bytes:
            payload["image"] = base64.b64encode(input_image_bytes).decode("ascii")

        print(f"🎥 Starting Wan video generation ({size}, {seconds}s)...")
        with httpx.Client(timeout=60.0) as client:
            response = client.post(
                f"{self.endpoint}/generate",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            job = response.json()

        job_id = job.get("job_id")
        if not job_id:
            raise RuntimeError(f"Wan server did not return a job_id: {job}")
        print(f"🎬 Wan job started: {job_id}")

        # Polling avec deadline globale (même contrat F-14 que Veo/Sora)
        timeout = _poll_timeout_seconds()
        deadline = time.monotonic() + timeout
        status = "queued"
        job_state: dict = {}

        with httpx.Client(timeout=30.0) as client:
            while status in ("queued", "processing"):
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Wan video generation timed out after {timeout:.0f}s "
                        f"(VIDEO_POLL_TIMEOUT_SECONDS), job {job_id}"
                    )
                time.sleep(10)
                response = client.get(
                    f"{self.endpoint}/jobs/{job_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
                job_state = response.json()
                status = job_state.get("status", "unknown")
                print(f"⏳ Wan job {job_id}: {status}")

        if status == "failed":
            raise RuntimeError(
                f"Wan video generation failed: {job_state.get('error', 'unknown error')}"
            )
        if status != "completed":
            raise RuntimeError(f"Unexpected Wan job status: {status}")

        # Récupération de la vidéo : video_url prioritaire, sinon video_b64
        video_bytes: Optional[bytes] = None
        video_url = job_state.get("video_url")
        if video_url:
            print(f"📥 Downloading Wan video from {video_url}")
            with httpx.Client(timeout=300.0, follow_redirects=True) as client:
                response = client.get(video_url, headers=self._headers())
                response.raise_for_status()
                video_bytes = response.content
        elif job_state.get("video_b64"):
            video_bytes = base64.b64decode(job_state["video_b64"])

        if not video_bytes:
            raise RuntimeError(
                f"Wan job {job_id} completed but returned neither video_url nor video_b64"
            )

        if download_path:
            with open(download_path, "wb") as f:
                f.write(video_bytes)
            print(f"💾 Wan video saved to: {download_path} ({len(video_bytes)} bytes)")
            return download_path

        return video_bytes
