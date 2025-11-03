import os
from supabase import create_client
import httpx

class SupabaseVideoUploader:
    """Upload vidéos vers Supabase Storage"""
    
    def __init__(self):
        self.supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_SERVICE_KEY")  # Service key pour bypass RLS
        )
        self.bucket = "vykso-videos"
    
    def upload_from_url(self, video_url: str, filename: str) -> str:
        """
        Download vidéo depuis URL et upload vers Supabase Storage
        
        Args:
            video_url: URL de la vidéo à télécharger
            filename: Nom du fichier sur Supabase (ex: job_id.mp4)
        
        Returns:
            URL publique de la vidéo
        """
        print(f"📥 Downloading video from {video_url}")
        
        # Download vidéo
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(video_url)
            response.raise_for_status()
            video_data = response.content
        
        print(f"📤 Uploading to Supabase Storage: {filename}")
        
        # Upload vers Supabase Storage
        self.supabase.storage.from_(self.bucket).upload(
            filename,
            video_data,
            {
                "content-type": "video/mp4",
                "cache-control": "public, max-age=31536000"
            }
        )
        
        # Générer l'URL publique
        public_url = self.supabase.storage.from_(self.bucket).get_public_url(filename)
        
        print(f"✅ Uploaded successfully: {public_url}")
        
        return public_url

    def upload_bytes(self, video_bytes: bytes, filename: str) -> str:
        """Upload raw MP4 bytes and return the public URL."""
        print(f"📤 Uploading bytes to Supabase Storage: {filename}")
        self.supabase.storage.from_(self.bucket).upload(
            filename,
            video_bytes,
            {
                "content-type": "video/mp4",
                "cache-control": "public, max-age=31536000",
            },
        )
        public_url = self.supabase.storage.from_(self.bucket).get_public_url(filename)
        print(f"✅ Uploaded successfully: {public_url}")
        return public_url
