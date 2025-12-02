# Prompt for Lovable (Frontend Generation)

**Context**: You are building the frontend for "Vykso", a premium AI video generation SaaS. The backend is ready (FastAPI/Supabase).

**Goal**: Create a stunning, high-end dashboard where users can generate videos.

**Key Features to Implement**:

1.  **Video Generation Form**:
    *   **Inputs**:
        *   **Prompt**: Text area for the video description.
        *   **Images**: File upload (up to 3 images allowed) to guide the generation. Veo 3.1 supports up to 3 reference images.
        *   **Duration**: Slider or buttons (8s, 16s, 24s, 32s, 40s, 48s, 56s). Must be multiples of 8s for Veo 3.1.
        *   **Model**: Dropdown with options:
            - **Veo 3.1** (default) - Google's latest video generation model with reference image support
            - **Sora 2** - OpenAI's video generation model
    *   **Logic**:
        *   When "Generate" is clicked, upload images to Supabase Storage first (`video-images` bucket).
        *   Then call `POST /api/videos/generate-advanced` with:
            *   `custom_prompt`: The text.
            *   `image_urls`: List of uploaded image URLs (max 3 for Veo 3.1).
            *   `duration`: Selected duration (must be multiple of 8 for Veo 3.1).
            *   `ai_model`: "veo3.1" (default), "veo3.1-fast" (faster generation), "sora2", or "sora2-pro".
            *   `model_type`: "text-to-video" (default) or "image-to-video" (if images present).

2.  **YouTube Integration**:
    *   Add a "Connect YouTube" button in the user settings or dashboard.
    *   Flow:
        *   Call `GET /api/auth/youtube/url` -> Redirect user to the returned URL.
        *   (The backend handles the callback).
    *   **Video Action**: On a generated video card, add an "Upload to YouTube" button.
        *   Call `POST /api/videos/{job_id}/upload-youtube`.

3.  **Credit System**:
    *   Display user credits (fetch from `/api/users/{id}/info`).
    *   Show cost estimate before generating (8s = 1 credit per segment).

**Veo 3.1 Specifications**:
*   **Duration**: 4s, 6s, or 8s per clip. Total video duration should be multiple of 8s.
*   **Aspect Ratio**: 16:9 or 9:16 (vertical for TikTok/Shorts).
*   **Resolution**: 720p (default) or 1080p (only for 8s clips).
*   **Reference Images**: Up to 3 images for style/content guidance.
*   **Image Generation**: Uses gemini-3-pro-image-preview for high-quality images with native image generation support.
*   **Prompt Enrichment**: All prompts are automatically enriched before generation for professional quality.

**Design Requirements**:
*   **Aesthetics**: Dark mode, glassmorphism, neon accents (purple/blue), smooth animations.
*   **Responsiveness**: Mobile-first but desktop optimized.
*   **Tech**: React, TailwindCSS, Lucide Icons, Shadcn UI (optional but recommended).

**API Base URL**: Use the provided backend URL (e.g., `http://localhost:8000` or production URL).
