"""
Content Generator for YouTube Shorts
Generates clickbait titles, descriptions, and handles scheduling
"""

import os
import random
import re
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
import pytz


class ContentGenerator:
    """
    Generates optimized content for YouTube Shorts uploads.
    """
    
    # Emojis for clickbait titles
    CLICKBAIT_EMOJIS = ['😱', '🔥', '❌', '✅', '💰', '🎯', '⚡', '🚀', '💡', '😲', '🤯', '👀', '⭐', '🏆', '💥']
    
    # Clickbait patterns (French-focused for Vykso)
    CLICKBAIT_PATTERNS = [
        "😱 {subject} {verb} {complement} !",
        "🔥 {action} en {time} ! (la {thing} que tout le monde cherche)",
        "💰 Cette {thing} m'a fait {result} !",
        "❌ PERSONNE ne connaît cette {thing} !",
        "✅ Comment {action} (résultat INCROYABLE)",
        "🚀 {subject} : le secret que PERSONNE ne te dit",
        "😲 {subject} : tu ne vas pas y croire !",
        "⚡ {number} façons de {action} (la #{best} est FOLLE)",
        "🎯 J'ai testé {subject} et... (résultat choquant)",
        "💡 L'astuce SECRÈTE pour {action}",
    ]
    
    # Default hashtags
    DEFAULT_HASHTAGS = ['#Shorts', '#Viral', '#Trending', '#AI', '#Vykso']
    DEFAULT_TAGS = ['Shorts', 'AI', 'Vykso', 'Viral', 'Trending']
    
    def __init__(self, gemini_client=None):
        """
        Initialize the content generator.
        
        Args:
            gemini_client: Optional GeminiClient for AI-powered content generation
        """
        self.gemini_client = gemini_client
    
    def generate_clickbait_title(self, prompt: str, max_length: int = 100) -> str:
        """
        Generates a clickbait title for YouTube Shorts based on the user's prompt.
        
        Args:
            prompt: The original user prompt for the video
            max_length: Maximum title length (YouTube limit is 100 chars)
            
        Returns:
            A clickbait title ending with " #Shorts"
        """
        # Try AI-powered generation first
        if self.gemini_client:
            try:
                title = self._generate_title_with_ai(prompt, max_length)
                if title:
                    return self._ensure_shorts_tag(title, max_length)
            except Exception as e:
                print(f"⚠️ AI title generation failed: {e}, using fallback")
        
        # Fallback to pattern-based generation
        return self._generate_title_fallback(prompt, max_length)
    
    def _generate_title_with_ai(self, prompt: str, max_length: int) -> Optional[str]:
        """
        Uses Gemini to generate a clickbait title.
        """
        from google.genai import types
        
        system_instruction = """
        Tu es un expert en titres YouTube clickbait. Génère UN SEUL titre accrocheur
        pour une vidéo YouTube Shorts.
        
        Règles STRICTES:
        1. Utilise des émojis pertinents (😱, 🔥, ❌, ✅, 💰, 🎯)
        2. Transforme le sujet en question ou affirmation choquante
        3. Utilise des chiffres si pertinent ("3 façons de...", "En 30 secondes...")
        4. Crée du suspense ("Personne ne connaît...", "Le secret de...")
        5. Capitalise stratégiquement les mots importants (INCROYABLE, ATTENTION, etc.)
        6. NE PAS inclure #Shorts (sera ajouté automatiquement)
        7. Maximum 90 caractères (pour laisser place à #Shorts)
        8. Retourne UNIQUEMENT le titre, rien d'autre
        
        Exemples de bonnes transformations:
        - "Un chat qui joue du piano" → "😱 Ce chat joue du BEETHOVEN ! (incroyable)"
        - "Recette de gâteau rapide" → "🔥 Gâteau prêt en 5 minutes ! (la recette que tout le monde cherche)"
        - "Astuce pour économiser" → "💰 Cette ASTUCE m'a fait économiser 500€ par mois !"
        """
        
        response = self.gemini_client.client.models.generate_content(
            model="gemini-2.0-flash",
            contents=f"Génère un titre clickbait pour cette vidéo: {prompt}",
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
            )
        )
        
        title = response.text.strip()
        # Remove any markdown or quotes
        title = re.sub(r'^["\']|["\']$', '', title)
        title = re.sub(r'^\*+|\*+$', '', title)
        
        return title[:90] if title else None
    
    def _generate_title_fallback(self, prompt: str, max_length: int) -> str:
        """
        Generates a title using pattern-based approach.
        """
        # Clean and extract key words from prompt
        words = prompt.lower().split()
        key_words = [w for w in words if len(w) > 3][:5]
        
        # Pick a random emoji and create a simple but effective title
        emoji = random.choice(self.CLICKBAIT_EMOJIS)
        
        # Simple patterns based on prompt length
        prompt_clean = prompt.strip()[:60]
        
        patterns = [
            f"{emoji} {prompt_clean.upper()[:30]} ! (INCROYABLE)",
            f"{emoji} Tu ne vas PAS y croire : {prompt_clean[:40]}",
            f"{emoji} REGARDE ça : {prompt_clean[:45]} !",
            f"{emoji} {prompt_clean[:50]} (résultat FOU)",
        ]
        
        title = random.choice(patterns)
        return self._ensure_shorts_tag(title, max_length)
    
    def _ensure_shorts_tag(self, title: str, max_length: int) -> str:
        """
        Ensures the title ends with #Shorts and fits within max_length.
        """
        shorts_tag = " #Shorts"
        
        # If title already has #Shorts, return as is (truncated if needed)
        if "#shorts" in title.lower():
            return title[:max_length]
        
        # Calculate available space
        available_length = max_length - len(shorts_tag)
        
        # Truncate title if needed and add #Shorts
        if len(title) > available_length:
            title = title[:available_length - 3] + "..."
        
        return f"{title}{shorts_tag}"
    
    def generate_description(self, prompt: str, custom_description: Optional[str] = None, max_length: int = 5000) -> str:
        """
        Generates a description for YouTube Shorts.
        
        Args:
            prompt: The original user prompt
            custom_description: Optional custom description from user
            max_length: Maximum description length (YouTube limit is 5000 chars)
            
        Returns:
            A formatted description with hashtags
        """
        if custom_description:
            # Use custom description, but ensure it has #Shorts somewhere
            return self._ensure_shorts_in_description(custom_description, max_length)
        
        # Generate default description
        lines = [
            prompt,
            "",
            "👉 Abonne-toi pour plus de contenu !",
            "",
            " ".join(self.DEFAULT_HASHTAGS)
        ]
        
        description = "\n".join(lines)
        return description[:max_length]
    
    def _ensure_shorts_in_description(self, description: str, max_length: int) -> str:
        """
        Ensures #Shorts appears in the description.
        """
        if "#shorts" in description.lower():
            return description[:max_length]
        
        # Add hashtags at the end
        hashtags = "\n\n#Shorts #Viral #Trending"
        available = max_length - len(hashtags)
        
        if len(description) > available:
            description = description[:available - 3] + "..."
        
        return f"{description}{hashtags}"
    
    def get_default_tags(self, custom_tags: Optional[List[str]] = None) -> List[str]:
        """
        Returns tags for the video.
        
        Args:
            custom_tags: Optional custom tags from user
            
        Returns:
            List of tags
        """
        if custom_tags and len(custom_tags) > 0:
            # Ensure 'Shorts' is in tags
            tags = list(custom_tags)
            if 'Shorts' not in tags and 'shorts' not in [t.lower() for t in tags]:
                tags.insert(0, 'Shorts')
            return tags
        
        return self.DEFAULT_TAGS.copy()
    
    def check_shorts_tag_present(self, title: str, description: str) -> Tuple[str, str]:
        """
        Ensures #Shorts is present in either title or description.
        If not present in either, adds it to the description.
        
        Args:
            title: The video title
            description: The video description
            
        Returns:
            Tuple of (title, description) with #Shorts guaranteed to be present
        """
        has_shorts_in_title = "#shorts" in title.lower()
        has_shorts_in_description = "#shorts" in description.lower()
        
        if has_shorts_in_title or has_shorts_in_description:
            return title, description
        
        # Add #Shorts to description
        if description:
            description = f"{description}\n\n#Shorts"
        else:
            description = "#Shorts"
        
        return title, description


class ScheduleCalculator:
    """
    Calculates optimal scheduling times for YouTube Shorts uploads.
    """
    
    # Optimal hours (Paris time) - between 15h and 20h
    OPTIMAL_HOURS = [15, 16, 17, 18, 19, 20]
    
    # Optimal days (Wednesday=2, Thursday=3, Friday=4)
    OPTIMAL_DAYS = [2, 3, 4]  # Wednesday, Thursday, Friday
    
    # Days to avoid
    AVOID_DAYS = [0, 5, 6]  # Monday (morning), Saturday, Sunday
    
    def __init__(self, timezone: str = "Europe/Paris"):
        """
        Initialize the scheduler.
        
        Args:
            timezone: The target timezone for scheduling
        """
        self.tz = pytz.timezone(timezone)
        self.utc = pytz.UTC
    
    def calculate_optimal_publish_time(self) -> datetime:
        """
        Calculates the optimal time to publish a YouTube Short.
        
        Returns:
            A datetime object in UTC representing the optimal publish time
        """
        now = datetime.now(self.tz)
        
        # Start searching from tomorrow
        candidate = now + timedelta(days=1)
        candidate = candidate.replace(hour=17, minute=0, second=0, microsecond=0)  # Default 17h
        
        # Find the next optimal slot
        for _ in range(14):  # Search up to 2 weeks
            day_of_week = candidate.weekday()
            
            # Check if it's an optimal day
            if day_of_week in self.OPTIMAL_DAYS:
                # Pick a random optimal hour for variety
                optimal_hour = random.choice(self.OPTIMAL_HOURS)
                candidate = candidate.replace(hour=optimal_hour, minute=random.randint(0, 30))
                break
            
            # Skip to next day if not optimal
            candidate += timedelta(days=1)
        
        # Convert to UTC for YouTube API
        return candidate.astimezone(self.utc)
    
    def get_next_available_slot(self, preferred_hour: Optional[int] = None) -> datetime:
        """
        Gets the next available scheduling slot.
        
        Args:
            preferred_hour: Optional preferred hour (in Paris timezone)
            
        Returns:
            A datetime in UTC
        """
        now = datetime.now(self.tz)
        
        # If preferred hour is set and valid
        if preferred_hour and 15 <= preferred_hour <= 20:
            hour = preferred_hour
        else:
            hour = random.choice(self.OPTIMAL_HOURS)
        
        # Start with tomorrow
        candidate = now + timedelta(days=1)
        candidate = candidate.replace(hour=hour, minute=random.randint(0, 30), second=0, microsecond=0)
        
        # Find next good day
        while candidate.weekday() not in self.OPTIMAL_DAYS:
            candidate += timedelta(days=1)
            # Don't go more than 7 days out
            if (candidate - now).days > 7:
                break
        
        return candidate.astimezone(self.utc)
    
    def format_for_youtube_api(self, dt: datetime) -> str:
        """
        Formats a datetime for the YouTube API.
        YouTube expects ISO 8601 format.
        
        Args:
            dt: The datetime to format (should be in UTC)
            
        Returns:
            ISO 8601 formatted string
        """
        # Ensure it's in UTC
        if dt.tzinfo is None:
            dt = self.utc.localize(dt)
        else:
            dt = dt.astimezone(self.utc)
        
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    
    def format_for_display(self, dt: datetime, target_tz: str = "Europe/Paris") -> str:
        """
        Formats a datetime for display to the user.
        
        Args:
            dt: The datetime to format
            target_tz: The timezone to display in
            
        Returns:
            Human-readable formatted string
        """
        tz = pytz.timezone(target_tz)
        local_dt = dt.astimezone(tz)
        
        # French day names
        days = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']
        day_name = days[local_dt.weekday()]
        
        return f"{day_name} {local_dt.strftime('%d/%m/%Y à %H:%M')} (heure de Paris)"
