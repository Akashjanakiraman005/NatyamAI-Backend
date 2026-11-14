import asyncio
import os
import cv2
import sys
import shutil
import re
import subprocess
from pathlib import Path


def normalize_youtube_url(url: str) -> str:
    """Normalize any YouTube URL (Shorts, mobile, youtu.be, query params) to standard watch format."""
    match = re.search(r'(?:v=|youtu\.be/|shorts/|embed/|watch\?v=)([a-zA-Z0-9_-]{11})', url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


async def download_youtube_video(url: str, output_dir: str) -> str:
    """Download YouTube video or Shorts using pytubefix with yt-dlp fallback."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "reference.mp4")

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    clean_url = normalize_youtube_url(url)
    print(f"Downloading normalized YouTube URL: {clean_url}")

    pytubefix_errors = []
    proc = None

    # Method 1: Try pytubefix with multiple clients
    for client_type in ["WEB", "ANDROID", "IOS"]:
        try:
            def _download_pytubefix():
                from pytubefix import YouTube
                yt = YouTube(clean_url, client=client_type)
                # Select visual stream (360p or 480p)
                stream = (
                    yt.streams.filter(only_video=True, resolution="360p").first()
                    or yt.streams.filter(only_video=True, resolution="480p").first()
                    or yt.streams.filter(only_video=True).order_by("resolution").asc().first()
                    or yt.streams.filter(progressive=True).first()
                )
                if not stream:
                    raise RuntimeError("No suitable video stream found")
                out_file = stream.download(output_path=output_dir, filename="reference.mp4")
                return out_file

            result = await asyncio.to_thread(_download_pytubefix)
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                print(f"pytubefix ({client_type}) download succeeded: {os.path.getsize(output_path)} bytes")
                return output_path
        except Exception as e:
            print(f"pytubefix ({client_type}) failed: {e}")
            pytubefix_errors.append(f"{client_type}: {e}")

    # Method 2: yt-dlp fallback with safari and android_creator clients
    has_ffmpeg = bool(shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))
    format_selector = (
        "bestvideo[height<=480][ext=mp4]+bestaudio/best[height<=480][ext=mp4]/best"
    )

    node_path = shutil.which("node") or shutil.which("node.exe")
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--extractor-args",
        "youtube:player_client=safari,android_creator,android",
        "--no-check-certificates",
        "--no-playlist",
        "-f",
        format_selector,
        "-o",
        output_path,
        clean_url,
    ]

    if node_path:
        cmd.extend(["--js-runtimes", f"node:{node_path}"])

    if has_ffmpeg:
        cmd.extend(["--download-sections", "*0-60", "--merge-output-format", "mp4"])

    proc = await asyncio.to_thread(
        subprocess.run,
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        err_msg = f"Download failed. pytubefix: {'; '.join(pytubefix_errors)}. yt-dlp: {proc.stderr[:200] if proc else 'none'}"
        raise RuntimeError(err_msg)

    return output_path


async def extract_frames(video_path: str, fps: int = 5, max_seconds: int = 30) -> list:
    """Extract frames from video at memory-safe FPS for cloud containers."""
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 30
    frame_interval = max(1, int(video_fps / fps))
    max_frames = max_seconds * fps

    frames = []
    frame_idx = 0

    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        if frame_idx % frame_interval == 0:
            frame = cv2.resize(frame, (320, 240))
            frames.append(frame)
        frame_idx += 1

    cap.release()
    return frames
