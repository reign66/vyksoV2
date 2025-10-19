import os
import subprocess
import tempfile
import httpx
from typing import List

class VideoEditor:
    """Concaténation de vidéos avec ffmpeg"""
    
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
    def concatenate_videos(video_urls: List[str], output_filename: str) -> bytes:
        """
        Concatène plusieurs vidéos en une seule
        
        Args:
            video_urls: Liste des URLs de vidéos à concaténer
            output_filename: Nom du fichier de sortie
        
        Returns:
            Bytes de la vidéo concaténée
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            print(f"🎞️ Starting concatenation of {len(video_urls)} videos...")
            
            # 1. Download toutes les vidéos
            video_files = []
            for i, url in enumerate(video_urls):
                video_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
                VideoEditor.download_video(url, video_path)
                video_files.append(video_path)
            
            print(f"✅ All {len(video_files)} clips downloaded successfully")
            
            # 2. Créer le fichier de liste pour ffmpeg
            list_file = os.path.join(tmpdir, "filelist.txt")
            with open(list_file, 'w') as f:
                for video_file in video_files:
                    # Échapper les apostrophes pour ffmpeg
                    escaped_path = video_file.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            print(f"📝 Created filelist with {len(video_files)} entries")
            
            # 3. Concaténer avec ffmpeg
            output_path = os.path.join(tmpdir, output_filename)
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
                    timeout=300  # 5 minutes max
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
                raise Exception(f"Video concatenation failed: {error_msg}")
            
            except subprocess.TimeoutExpired:
                print(f"❌ FFmpeg timeout after 5 minutes")
                raise Exception("Video concatenation timed out")
            
            except Exception as e:
                print(f"❌ Concatenation error: {type(e).__name__}: {e}")
                import traceback
                traceback.print_exc()
                raise
