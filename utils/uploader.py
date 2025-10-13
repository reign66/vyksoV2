import os
import boto3
import httpx
from io import BytesIO

class R2Uploader:
    """Upload vers Cloudflare R2"""
    
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            endpoint_url=os.getenv("R2_ENDPOINT"),
            aws_access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            region_name='auto'
        )
        self.bucket = os.getenv("R2_BUCKET")
        self.public_base = os.getenv("R2_PUBLIC_BASE")
    
    def upload_from_url(self, video_url: str, filename: str) -> str:
        """
        Download vidéo depuis URL et upload vers R2
        
        Args:
            video_url: URL de la vidéo à télécharger
            filename: Nom du fichier sur R2
        
        Returns:
            URL publique de la vidéo
        """
        print(f"📥 Downloading video from {video_url}")
        
        # Download vidéo
        with httpx.Client(timeout=120.0, follow_redirects=True) as client:
            response = client.get(video_url)
            response.raise_for_status()
            video_data = BytesIO(response.content)
        
        print(f"📤 Uploading to R2: {filename}")
        
        # Upload vers R2
        self.s3.upload_fileobj(
            video_data,
            self.bucket,
            filename,
            ExtraArgs={
                'ContentType': 'video/mp4',
                'CacheControl': 'public, max-age=31536000',
                'ACL': 'public-read'
            }
        )
        
        public_url = f"{self.public_base}/{filename}"
        print(f"✅ Uploaded successfully: {public_url}")
        
        return public_url
