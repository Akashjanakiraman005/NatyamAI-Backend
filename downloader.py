import asyncio
import os
import cv2
import sys
import shutil
import subprocess
from pathlib import Path


async def download_youtube_video(url: str, output_dir: str) -> str:
    """Download YouTube video using pytubefix (bypasses 429/PO-token) with yt-dlp fallback."""
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "reference.mp4")

    if os.path.exists(output_path):
        try:
            os.remove(output_path)
        except Exception:
            pass

    # Method 1: Try pytubefix with WEB client (bypasses datacenter 429 blocks)
    try:
        def _download_pytubefix():
            from pytubefix import YouTube
            yt = YouTube(url, client="WEB")
            # Select 360p or 480p video stream (visual only, ideal for pose estimation)
            stream = (
                yt.streams.filter(only_video=True, resolution="360p").first()
                or yt.streams.filter(only_video=True, resolution="480p").first()
                or yt.streams.filter(only_video=True).order_by("resolution").asc().first()
                or yt.streams.filter(progressive=True).first()
            )
            if not stream:
                raise RuntimeError("No suitable video stream found via pytubefix")
            out_file = stream.download(output_path=output_dir, filename="reference.mp4")
            return out_file

        result = await asyncio.to_thread(_download_pytubefix)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        print(f"pytubefix attempt failed ({e}), falling back to yt-dlp...")

    # Method 2: yt-dlp fallback
    has_ffmpeg = bool(shutil.which("ffmpeg") or shutil.which("ffmpeg.exe"))
    format_selector = (
        "bestvideo[height<=480][ext=mp4]/best[height<=480][ext=mp4]/best[height<=480]"
    )

    node_path = shutil.which("node") or shutil.which("node.exe")
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "--extractor-args",
        "youtube:player_client=android,ios,mweb",
        "--no-check-certificates",
        "--no-playlist",
        "-f",
        format_selector,
        "-o",
        output_path,
        url,
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
        raise RuntimeError(f"Video download failed. Please select the video from your phone Gallery.")

    return output_path


async def extract_frames(video_path: str, fps: int = 15, max_seconds: int = 60) -> list:
    """Extract frames from video at specified FPS."""
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
            frame = cv2.resize(frame, (640, 480))
            frames.append(frame)
        frame_idx += 1

    cap.release()
    return frames
