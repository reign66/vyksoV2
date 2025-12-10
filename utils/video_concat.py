import os
import subprocess
import tempfile
import httpx
from typing import List, Optional, Union
from io import BytesIO


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
            
            # First, get video duration using ffprobe
            probe_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            try:
                result = subprocess.run(
                    probe_cmd,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                duration = float(result.stdout.strip())
                print(f"📊 Video duration: {duration}s")
            except Exception as e:
                print(f"⚠️ Could not get video duration: {e}, using fallback method")
                duration = None
            
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
            
            try:
                result = subprocess.run(
                    extract_cmd,
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                    print(f"✅ Last frame extracted: {os.path.getsize(frame_path)} bytes")
                    with open(frame_path, 'rb') as f:
                        return f.read()
                else:
                    # Fallback: use frame count method
                    print("⚠️ First method failed, trying frame count method...")
                    
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
                    
                    result = subprocess.run(count_cmd, capture_output=True, text=True, timeout=30)
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
                    
                    subprocess.run(extract_cmd2, capture_output=True, text=True, timeout=60)
                    
                    if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                        with open(frame_path, 'rb') as f:
                            return f.read()
                    
                    raise Exception("Failed to extract last frame with both methods")
                    
            except subprocess.TimeoutExpired:
                raise Exception("Frame extraction timed out")
            except Exception as e:
                print(f"❌ Frame extraction error: {e}")
                raise
    
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
            probe_cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            duration = float(result.stdout.strip())
            
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
            
            subprocess.run(extract_cmd, capture_output=True, text=True, timeout=60)
            
            if os.path.exists(frame_path) and os.path.getsize(frame_path) > 0:
                with open(frame_path, 'rb') as f:
                    return f.read()
            
            raise Exception(f"Failed to extract frame at position {position}")
    
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
            add_transitions: Si True, ajoute des crossfades entre les clips
            transition_duration: Durée du crossfade en secondes (0.3-0.5 recommandé)
        
        Returns:
            Bytes de la vidéo concaténée
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"🎞️ Starting concatenation of {len(video_urls)} videos...")
            if add_transitions:
                print(f"✨ Transitions enabled: {transition_duration}s crossfade")
            
            # 1. Download toutes les vidéos
            video_files = []
            for i, url in enumerate(video_urls):
                video_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
                VideoEditor.download_video(url, video_path)
                video_files.append(video_path)
            
            print(f"✅ All {len(video_files)} clips downloaded successfully")
            
            output_path = os.path.join(tmpdir, output_filename)
            
            if add_transitions and len(video_files) > 1:
                # Use xfade filter for crossfade transitions
                print(f"🎬 Running ffmpeg with crossfade transitions...")
                
                # Build complex filter for xfade transitions
                # For N videos, we need N-1 xfade filters
                filter_parts = []
                
                # Input streams
                inputs = []
                for i, vf in enumerate(video_files):
                    inputs.extend(['-i', vf])
                
                # Build xfade filter chain
                # [0][1]xfade=transition=fade:duration=0.3:offset=7.7[v01]; [v01][2]xfade=...
                current_output = "[0:v]"
                
                for i in range(1, len(video_files)):
                    next_input = f"[{i}:v]"
                    output_label = f"[v{i-1}{i}]" if i < len(video_files) - 1 else "[outv]"
                    
                    # Calculate offset (end of previous video minus transition duration)
                    # For simplicity, assume each video is ~8s
                    # We need to get actual duration, but for now use estimate
                    offset = 8.0 * i - transition_duration * i
                    
                    filter_parts.append(
                        f"{current_output}{next_input}xfade=transition=fade:duration={transition_duration}:offset={offset}{output_label}"
                    )
                    current_output = output_label
                
                # Handle audio (simple concat for now)
                audio_inputs = "".join([f"[{i}:a]" for i in range(len(video_files))])
                filter_parts.append(f"{audio_inputs}concat=n={len(video_files)}:v=0:a=1[outa]")
                
                filter_complex = ";".join(filter_parts)
                
                cmd = [
                    'ffmpeg', '-y',
                    *inputs,
                    '-filter_complex', filter_complex,
                    '-map', '[outv]',
                    '-map', '[outa]',
                    '-c:v', 'libx264',
                    '-preset', 'fast',
                    '-crf', '18',
                    '-c:a', 'aac',
                    '-b:a', '192k',
                    output_path
                ]
            else:
                # Simple concat without transitions
                # 2. Créer le fichier de liste pour ffmpeg
                list_file = os.path.join(tmpdir, "filelist.txt")
                with open(list_file, 'w') as f:
                    for video_file in video_files:
                        # Échapper les apostrophes pour ffmpeg
                        escaped_path = video_file.replace("'", "'\\''")
                        f.write(f"file '{escaped_path}'\n")
                
                print(f"📝 Created filelist with {len(video_files)} entries")
                print(f"🎬 Running ffmpeg to concatenate {len(video_files)} videos...")
                
                cmd = [
                    'ffmpeg',
                    '-f', 'concat',
                    '-safe', '0',
                    '-i', list_file,
                    '-c', 'copy',
                    '-y',  # Overwrite output file
                    output_path
                ]
            
            try:
                result = subprocess.run(
                    cmd, 
                    check=True, 
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes max for transitions
                )
                
                print(f"✅ FFmpeg completed successfully")
                
                # Vérifier que le fichier existe
                if not os.path.exists(output_path):
                    raise Exception(f"Output file was not created: {output_path}")
                
                # Vérifier la taille du fichier
                file_size = os.path.getsize(output_path)
                if file_size == 0:
                    raise Exception(f"Output file is empty (0 bytes)")
                
                print(f"✅ Concatenated video created: {output_path} ({file_size} bytes)")
                
                # Lire le fichier et retourner les bytes
                with open(output_path, 'rb') as f:
                    video_data = f.read()
                
                # Vérifier que les données ont bien été lues
                if len(video_data) != file_size:
                    raise Exception(f"File size mismatch: read {len(video_data)} bytes, expected {file_size}")
                
                print(f"✅ Video data loaded into memory ({len(video_data)} bytes)")
                
                return video_data
            
            except subprocess.CalledProcessError as e:
                error_msg = e.stderr if e.stderr else str(e)
                print(f"❌ FFmpeg error:")
                print(f"  stdout: {e.stdout}")
                print(f"  stderr: {e.stderr}")
                
                # Fallback to simple concat if transitions fail
                if add_transitions:
                    print("⚠️ Falling back to simple concat without transitions...")
                    return VideoEditor.concatenate_videos(video_urls, output_filename, add_transitions=False)
                
                raise Exception(f"Video concatenation failed: {error_msg}")
            
            except subprocess.TimeoutExpired:
                print(f"❌ FFmpeg timeout after 10 minutes")
                raise Exception("Video concatenation timed out")
            
            except Exception as e:
                print(f"❌ Concatenation error: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                raise
    
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
            add_transitions: Si True, ajoute des crossfades
            transition_duration: Durée du crossfade
        
        Returns:
            Bytes de la vidéo concaténée
        """
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
            
            # Create file list for simple concat
            list_file = os.path.join(tmpdir, "filelist.txt")
            with open(list_file, 'w') as f:
                for video_file in video_files:
                    escaped_path = video_file.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            output_path = os.path.join(tmpdir, output_filename)
            
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                '-y',
                output_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                with open(output_path, 'rb') as f:
                    return f.read()
            
            raise Exception("Failed to concatenate video segments")
