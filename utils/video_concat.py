import os
import shutil
import subprocess
import tempfile
import httpx
from typing import List, Optional, Union


def ensure_ffmpeg():
    """Vérifie que ffmpeg et ffprobe sont disponibles sur le système (F-22).

    Lève une RuntimeError explicite (en français) si l'un des deux manque,
    plutôt qu'un FileNotFoundError cryptique au milieu d'un job.
    """
    missing = [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(
            f"Outil(s) vidéo introuvable(s) : {', '.join(missing)}. "
            "ffmpeg (avec ffprobe) doit être installé et présent dans le PATH du serveur "
            "pour la concaténation et l'extraction de frames."
        )


def _run_cmd(cmd: List[str], timeout: int) -> subprocess.CompletedProcess:
    """Run an ffmpeg/ffprobe command with proper error checking (F-25).

    Raises RuntimeError including the tool's stderr on non-zero exit.
    """
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"{cmd[0]} timed out after {timeout}s") from e
    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise RuntimeError(
            f"{cmd[0]} failed (exit code {result.returncode}): {stderr_tail or 'no stderr output'}"
        )
    return result


def _probe_duration(video_path: str) -> float:
    """Return the duration in seconds of a video file via ffprobe (F-24: no hardcoded durations)."""
    result = _run_cmd([
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        video_path
    ], timeout=30)
    try:
        return float(result.stdout.strip())
    except (TypeError, ValueError) as e:
        raise RuntimeError(f"ffprobe returned an unparseable duration for {video_path}: {result.stdout!r}") from e


def _has_audio_stream(video_path: str) -> bool:
    """Return True if the video file contains at least one audio stream."""
    result = _run_cmd([
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=index',
        '-of', 'csv=p=0',
        video_path
    ], timeout=30)
    return bool(result.stdout.strip())


class VideoEditor:
    """Concaténation de vidéos avec ffmpeg et extraction de frames"""

    @staticmethod
    def download_video(url: str, output_path: str):
        """Download une vidéo depuis une URL"""
        print(f"📥 Downloading {url}")
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(url)
            response.raise_for_status()
            with open(output_path, 'wb') as f:
                f.write(response.content)
        file_size = os.path.getsize(output_path)
        print(f"✅ Downloaded to {output_path} ({file_size} bytes)")

    @staticmethod
    def extract_last_frame(video_path_or_bytes: Union[str, bytes], output_path: Optional[str] = None) -> bytes:
        """
        Extract the last frame from a video file.

        This is crucial for maintaining visual continuity between sequences.
        The extracted frame will be used as the START keyframe for the next sequence.

        Args:
            video_path_or_bytes: Path to video file or video bytes
            output_path: Optional path to save the frame image

        Returns:
            JPEG image bytes of the last frame
        """
        ensure_ffmpeg()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Handle bytes input
            if isinstance(video_path_or_bytes, bytes):
                video_path = os.path.join(tmpdir, "input_video.mp4")
                with open(video_path, "wb") as f:
                    f.write(video_path_or_bytes)
            else:
                video_path = video_path_or_bytes

            # Output path for the frame
            frame_path = output_path or os.path.join(tmpdir, "last_frame.jpg")

            # Extract last frame
            # Method 1: Use sseof to seek from end (most reliable)
            extract_cmd = [
                'ffmpeg',
                '-y',
                '-sseof', '-0.1',  # Seek to 0.1s before end
                '-i', video_path,
                '-vframes', '1',
                '-q:v', '2',  # High quality JPEG
                frame_path
            ]

            first_error = None
            try:
                _run_cmd(extract_cmd, timeout=60)
            except RuntimeError as e:
                first_error = e

            if first_error is None and os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                print(f"✅ Last frame extracted: {os.path.getsize(frame_path)} bytes")
                with open(frame_path, 'rb') as f:
                    return f.read()

            # Fallback: use frame count method
            print(f"⚠️ First method failed ({first_error}), trying frame count method...")

            # Get total frame count
            count_cmd = [
                'ffprobe',
                '-v', 'error',
                '-select_streams', 'v:0',
                '-count_packets',
                '-show_entries', 'stream=nb_read_packets',
                '-of', 'csv=p=0',
                video_path
            ]

            result = _run_cmd(count_cmd, timeout=30)
            frame_count = int(result.stdout.strip())

            # Extract the last frame by frame number
            extract_cmd2 = [
                'ffmpeg',
                '-y',
                '-i', video_path,
                '-vf', f'select=eq(n\\,{frame_count - 1})',
                '-vframes', '1',
                '-q:v', '2',
                frame_path
            ]

            _run_cmd(extract_cmd2, timeout=60)

            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                with open(frame_path, 'rb') as f:
                    return f.read()

            raise RuntimeError(
                f"Failed to extract last frame with both methods (first error: {first_error})"
            )

    @staticmethod
    def extract_frame_at_position(
        video_path_or_bytes: Union[str, bytes],
        position: float,  # 0.0 to 1.0 (percentage through video)
        output_path: Optional[str] = None
    ) -> bytes:
        """
        Extract a frame at a specific position in the video.

        Args:
            video_path_or_bytes: Path to video file or video bytes
            position: Position in video (0.0 = start, 0.5 = middle, 1.0 = end)
            output_path: Optional path to save the frame image

        Returns:
            JPEG image bytes
        """
        ensure_ffmpeg()
        with tempfile.TemporaryDirectory() as tmpdir:
            # Handle bytes input
            if isinstance(video_path_or_bytes, bytes):
                video_path = os.path.join(tmpdir, "input_video.mp4")
                with open(video_path, "wb") as f:
                    f.write(video_path_or_bytes)
            else:
                video_path = video_path_or_bytes

            frame_path = output_path or os.path.join(tmpdir, "extracted_frame.jpg")

            # Get video duration
            duration = _probe_duration(video_path)

            # Calculate timestamp
            timestamp = duration * min(max(position, 0.0), 0.999)  # Clamp to valid range

            # Extract frame at timestamp
            extract_cmd = [
                'ffmpeg',
                '-y',
                '-ss', str(timestamp),
                '-i', video_path,
                '-vframes', '1',
                '-q:v', '2',
                frame_path
            ]

            _run_cmd(extract_cmd, timeout=60)

            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                with open(frame_path, 'rb') as f:
                    return f.read()

            raise RuntimeError(f"Failed to extract frame at position {position}")

    @staticmethod
    def _concat_simple(video_files: List[str], output_path: str, tmpdir: str):
        """Fast stream-copy concatenation (no re-encode, no transitions)."""
        list_file = os.path.join(tmpdir, "filelist.txt")
        with open(list_file, 'w') as f:
            for video_file in video_files:
                # Échapper les apostrophes pour ffmpeg
                escaped_path = video_file.replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")

        print(f"🎬 Running ffmpeg to concatenate {len(video_files)} videos (stream copy)...")
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'concat',
            '-safe', '0',
            '-i', list_file,
            '-c', 'copy',
            output_path
        ]
        _run_cmd(cmd, timeout=300)

    @staticmethod
    def _concat_with_transitions(
        video_files: List[str],
        output_path: str,
        transition_duration: float
    ):
        """Concatenate with real crossfade transitions (F-23).

        Uses xfade for video AND acrossfade for audio, with per-clip durations
        measured via ffprobe (F-24: no hardcoded 8s offsets).
        """
        n = len(video_files)

        # Measure real durations (F-24)
        durations = [_probe_duration(p) for p in video_files]
        print(f"📊 Clip durations: {[f'{d:.2f}s' for d in durations]}")

        audio_flags = [_has_audio_stream(p) for p in video_files]
        all_audio = all(audio_flags)
        if not all_audio and any(audio_flags):
            # Mixed audio presence: acrossfade chain would fail mid-graph
            raise RuntimeError(
                "Clips have mixed audio presence (some with audio, some without); "
                "cannot build acrossfade chain"
            )

        # Clamp transition so it never exceeds half of the shortest clip
        t = max(0.05, min(transition_duration, min(durations) / 2.0))
        if t != transition_duration:
            print(f"⚠️ Transition duration clamped from {transition_duration}s to {t:.2f}s")

        inputs = []
        for vf in video_files:
            inputs.extend(['-i', vf])

        filter_parts = []

        # Video xfade chain with cumulative offsets based on measured durations
        current_v = "[0:v]"
        cumulative = durations[0]
        for i in range(1, n):
            out_label = f"[vx{i}]" if i < n - 1 else "[outv]"
            offset = max(0.0, cumulative - t)
            filter_parts.append(
                f"{current_v}[{i}:v]xfade=transition=fade:duration={t:.3f}:offset={offset:.3f}{out_label}"
            )
            current_v = out_label
            cumulative = cumulative + durations[i] - t

        maps = ['-map', '[outv]']

        # Audio acrossfade chain (F-23: audio must crossfade too)
        if all_audio:
            current_a = "[0:a]"
            for i in range(1, n):
                a_label = f"[ax{i}]" if i < n - 1 else "[outa]"
                filter_parts.append(
                    f"{current_a}[{i}:a]acrossfade=d={t:.3f}:c1=tri:c2=tri{a_label}"
                )
                current_a = a_label
            maps.extend(['-map', '[outa]'])
        else:
            print("ℹ️ No audio streams detected in any clip — video-only crossfade")

        cmd = [
            'ffmpeg', '-y',
            *inputs,
            '-filter_complex', ";".join(filter_parts),
            *maps,
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '18',
            '-pix_fmt', 'yuv420p',
        ]
        if all_audio:
            cmd.extend(['-c:a', 'aac', '-b:a', '192k'])
        cmd.append(output_path)

        print(f"🎬 Running ffmpeg with {n - 1} crossfade transition(s) of {t:.2f}s...")
        _run_cmd(cmd, timeout=600)

    @staticmethod
    def _concat_files(
        video_files: List[str],
        output_path: str,
        tmpdir: str,
        add_transitions: bool,
        transition_duration: float
    ) -> bytes:
        """Shared concat core: transitions if requested (with fallback), then read result."""
        if add_transitions and len(video_files) > 1:
            print(f"✨ Transitions enabled: {transition_duration}s crossfade")
            try:
                VideoEditor._concat_with_transitions(video_files, output_path, transition_duration)
            except Exception as e:
                print(f"⚠️ Crossfade concat failed ({e}), falling back to simple concat...")
                VideoEditor._concat_simple(video_files, output_path, tmpdir)
        else:
            VideoEditor._concat_simple(video_files, output_path, tmpdir)

        # Vérifier que le fichier existe et n'est pas vide
        if not os.path.exists(output_path):
            raise RuntimeError(f"Output file was not created: {output_path}")
        file_size = os.path.getsize(output_path)
        if file_size == 0:
            raise RuntimeError("Output file is empty (0 bytes)")

        print(f"✅ Concatenated video created: {output_path} ({file_size} bytes)")

        with open(output_path, 'rb') as f:
            video_data = f.read()

        if len(video_data) != file_size:
            raise RuntimeError(
                f"File size mismatch: read {len(video_data)} bytes, expected {file_size}"
            )

        print(f"✅ Video data loaded into memory ({len(video_data)} bytes)")
        return video_data

    @staticmethod
    def concatenate_videos(
        video_urls: List[str],
        output_filename: str,
        add_transitions: bool = False,
        transition_duration: float = 0.3
    ) -> bytes:
        """
        Concatène plusieurs vidéos en une seule, optionnellement avec des transitions crossfade.

        Args:
            video_urls: Liste des URLs de vidéos à concaténer
            output_filename: Nom du fichier de sortie
            add_transitions: Si True, ajoute des crossfades (xfade vidéo + acrossfade audio)
            transition_duration: Durée du crossfade en secondes (0.3-0.5 recommandé)

        Returns:
            Bytes de la vidéo concaténée
        """
        ensure_ffmpeg()
        # Tous les fichiers temporaires vivent dans ce TemporaryDirectory
        # et sont nettoyés automatiquement, même en cas d'exception.
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"🎞️ Starting concatenation of {len(video_urls)} videos...")

            # 1. Download toutes les vidéos
            video_files = []
            for i, url in enumerate(video_urls):
                video_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
                VideoEditor.download_video(url, video_path)
                video_files.append(video_path)

            print(f"✅ All {len(video_files)} clips downloaded successfully")

            output_path = os.path.join(tmpdir, output_filename)
            return VideoEditor._concat_files(
                video_files, output_path, tmpdir, add_transitions, transition_duration
            )

    @staticmethod
    def concatenate_video_bytes(
        video_bytes_list: List[bytes],
        output_filename: str,
        add_transitions: bool = False,
        transition_duration: float = 0.3
    ) -> bytes:
        """
        Concatène plusieurs vidéos depuis leurs bytes (pas d'URLs).
        Utile pour le traitement séquentiel où les vidéos sont déjà en mémoire.

        Args:
            video_bytes_list: Liste des bytes de vidéos à concaténer
            output_filename: Nom du fichier de sortie
            add_transitions: Si True, ajoute des crossfades (xfade vidéo + acrossfade audio)
            transition_duration: Durée du crossfade

        Returns:
            Bytes de la vidéo concaténée
        """
        ensure_ffmpeg()
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"🎞️ Concatenating {len(video_bytes_list)} video segments from memory...")

            # Save bytes to temp files
            video_files = []
            for i, vb in enumerate(video_bytes_list):
                video_path = os.path.join(tmpdir, f"segment_{i:02d}.mp4")
                with open(video_path, 'wb') as f:
                    f.write(vb)
                video_files.append(video_path)
                print(f"  📁 Segment {i + 1}: {len(vb)} bytes")

            output_path = os.path.join(tmpdir, output_filename)
            return VideoEditor._concat_files(
                video_files, output_path, tmpdir, add_transitions, transition_duration
            )
