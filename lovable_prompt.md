# Prompt for Lovable (Frontend Generation)

**Context**: You are building the frontend for "Vykso", a premium AI video generation SaaS. The backend is ready (FastAPI/Supabase).

**Goal**: Create a stunning, high-end dashboard where users can generate videos.

**Key Features to Implement**:

1.  **Video Generation Form**:
    *   **Inputs**:
        *   **Prompt**: Text area for the video description.
        *   **Images**: File upload (multiple allowed) to guide the generation.
        *   **Duration**: Slider or buttons (10s, 20s, 30s, 60s).
        *   **Model**: Dropdown (Veo 3 Fast, Veo 3, Sora 2).
    *   **Logic**:
        *   When "Generate" is clicked, upload images to Supabase Storage first (`video-images` bucket).
        *   Then call `POST /api/videos/generate-advanced` with:
            *   `custom_prompt`: The text.
            *   `image_urls`: List of uploaded image URLs.
            *   `duration`: Selected duration.
            *   `ai_model`: Selected model.
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
    *   Show cost estimate before generating (10s = X credits).

**Design Requirements**:
*   **Aesthetics**: Dark mode, glassmorphism, neon accents (purple/blue), smooth animations.
*   **Responsiveness**: Mobile-first but desktop optimized.
*   **Tech**: React, TailwindCSS, Lucide Icons, Shadcn UI (optional but recommended).

**API Base URL**: Use the provided backend URL (e.g., `http://localhost:8000` or production URL).
