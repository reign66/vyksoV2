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
        print(f"✅ Downloaded to {output_path}")
    
    @staticmethod
    def concatenate_videos(video_urls: List[str], output_filename: str) -> str:
        """
        Concatène plusieurs vidéos en une seule
        
        Args:
            video_urls: Liste des URLs de vidéos à concaténer
            output_filename: Nom du fichier de sortie
        
        Returns:
            Chemin du fichier vidéo final
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Download toutes les vidéos
            video_files = []
            for i, url in enumerate(video_urls):
                video_path = os.path.join(tmpdir, f"clip_{i:02d}.mp4")
                VideoEditor.download_video(url, video_path)
                video_files.append(video_path)
            
            # 2. Créer le fichier de liste pour ffmpeg
            list_file = os.path.join(tmpdir, "filelist.txt")
            with open(list_file, 'w') as f:
                for video_file in video_files:
                    f.write(f"file '{video_file}'\n")
            
            # 3. Concaténer avec ffmpeg
            output_path = os.path.join(tmpdir, output_filename)
            print(f"🎬 Concatenating {len(video_files)} videos...")
            
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', list_file,
                '-c', 'copy',
                output_path
            ]
            
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                print(f"✅ Video concatenated: {output_path}")
                
                # Lire le fichier pour le retourner
                with open(output_path, 'rb') as f:
                    video_data = f.read()
                
                return video_data
            
            except subprocess.CalledProcessError as e:
                print(f"❌ FFmpeg error: {e.stderr.decode()}")
                raise Exception(f"Video concatenation failed: {e.stderr.decode()}")
