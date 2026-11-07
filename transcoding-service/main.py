import os
import re
import shutil
import uuid
import boto3
import subprocess
import requests
import json
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pathlib import Path
from dotenv import load_dotenv
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from schemas import TranscodeRequest



project_path = Path(__file__).resolve().parent
env_path = project_path / ".env"
load_dotenv(dotenv_path=env_path)


app = FastAPI()

alowed_origins = os.environ.get("ALLOWED_ORIGINS")
# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[alowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


s3_client = boto3.client(
    "s3",
    endpoint_url=os.environ.get("R2_ENDPOINT_URL"),
    aws_access_key_id=os.environ.get("R2_ACCESS_KEY_ID"),
    aws_secret_access_key=os.environ.get("R2_SECRET_ACCESS_KEY"),
    region_name="auto",
)


def send_callback(url, course_id, lesson_id, **kwargs):
    try:
        response = requests.post(
            url, 
            json={"course_id": course_id, "lesson_id": lesson_id, **kwargs}
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to send callback: {e}")



def generate_thumbnail(input_path: str, output_path: str):
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-ss",
        "00:00:10.000",
        "-vframes",
        "1",
        output_path,
    ]
    subprocess.run(cmd, check=True)


def upload_directory(local_dir, s3_prefix):
    bucket = os.environ.get("R2_BUCKET_NAME", "evolveu-content")
    for root, _, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, local_dir)
            s3_key = f"{s3_prefix}/{relative_path}"
            print(f"Uploading {local_path} to {s3_key}")
            s3_client.upload_file(local_path, bucket, s3_key)


def get_video_info(input_path: str):
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=width,height,codec_type",
        "-of",
        "json",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(result.stdout)["streams"]


def get_duration(input_path: str) -> int:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return int(float(result.stdout.strip()))
    except Exception:
        return 0


def transcode_to_hls(input_path: str, output_dir: str):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    streams = get_video_info(input_path)
    video_stream = next((s for s in streams if s["codec_type"] == "video"), None)
    audio_stream = next((s for s in streams if s["codec_type"] == "audio"), None)

    if not video_stream:
        raise Exception("No video stream found")

    # --- FIX 1: DEFINE TARGETS ---
    targets = [
        {"name": "1080p", "w": 1920, "h": 1080, "crf": "23", "maxrate": "4000k"}, # Slightly better quality for 1080p
        {"name": "720p", "w": 1280, "h": 720, "crf": "24", "maxrate": "2000k"},
        {"name": "480p", "w": 854, "h": 480, "crf": "26", "maxrate": "1000k"},
    ]

    active = targets
    count = len(active)

    filter_complex = (
        f"[0:v]split={count}" + "".join([f"[v{i}]" for i in range(count)]) + ";"
    )
    for i, t in enumerate(active):
        filter_complex += f"[v{i}]scale={t['w']}:{t['h']}[out{i}];"

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        input_path,
        "-filter_complex",
        filter_complex.rstrip(";"),
    ]

    var_stream_map = []
    for i, t in enumerate(active):
        cmd += ["-map", f"[out{i}]"]

        if audio_stream:
            cmd += ["-map", "0:a"]

        # libx264 with CRF and Maxrate to prevent bloating
        cmd += [
            f"-c:v:{i}", "libx264",
            "-preset", "veryfast",
            f"-crf:{i}", t["crf"],
            f"-maxrate:{i}", t["maxrate"],
            f"-bufsize:{i}", str(int(t["maxrate"].replace("k","")) * 2) + "k",
        ]

        if audio_stream:
            cmd += [f"-c:a:{i}", "aac", f"-b:a:{i}", "128k"]
            var_stream_map.append(f"v:{i},a:{i},name:{t['name']}")
        else:
            var_stream_map.append(f"v:{i},name:{t['name']}")

    cmd += [
        "-f", "hls",
        "-hls_time", "6",
        "-hls_playlist_type", "vod",
        "-master_pl_name", "master.m3u8",
        "-var_stream_map", " ".join(var_stream_map),
        "-hls_segment_filename", os.path.join(output_dir, "v%v/fileSequence%d.ts"),
        os.path.join(output_dir, "v%v/prog_index.m3u8"),
    ]

    print(f"Processing {count} variants...")
    subprocess.run(cmd, check=True)
    return [t["name"] for t in active]  


def process_transcode(
    Prefix: str,
    lesson_id: Optional[str] = None,
    course_id: Optional[str] = None,
):
    bucket = os.environ.get("R2_BUCKET_NAME", "evolveu-content")
    output_prefix = str(Path(Prefix).with_suffix(""))
    work_dir = project_path / "temp" / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        print(f"Downloading {Prefix}")
        input_path = work_dir / "original.mp4"
        s3_client.download_file(bucket, Prefix, str(input_path))

        print("Starting transcoding...")
        qualities = transcode_to_hls(str(input_path), str(work_dir))
        duration = get_duration(str(input_path))  # Get duration

        print("Generating thumbnail...")
        thumbnail_path = work_dir / "thumbnail.jpg"
        generate_thumbnail(str(input_path), str(thumbnail_path))

        if input_path.exists():
            os.remove(input_path)  # Remove input before upload

        print(f"Uploading output to {output_prefix}")
        upload_directory(str(work_dir), output_prefix)

        base_media_url = os.environ.get("R2_MEDIA_URL")
        master_url = f"{base_media_url}/{output_prefix}/master.m3u8"
        thumbnail_url = f"{base_media_url}/{output_prefix}/thumbnail.jpg"

        send_callback(
            os.getenv("TRANSCODING_CALLBACK_URL"),
            course_id,
            lesson_id,
            status="COMPLETED",
            master_key=master_url,
            thumbnail_url=thumbnail_url,
            duration=duration,
            qualities=qualities,
        )

    except Exception as e:
        print(f"Transcoding failed: {e}")
        send_callback(
            os.getenv("TRANSCODING_CALLBACK_URL"),
            course_id,
            lesson_id,
            status="FAILED",
            error=str(e),
        )
    finally:
        if "work_dir" in locals() and work_dir.exists():
            shutil.rmtree(work_dir)


@app.post("/transcode")
async def transcode(request: TranscodeRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(
        process_transcode,
        request.Prefix,
        request.lesson_id,
        request.course_id,
    )
    return {"message": "Transcoding started"}


@app.get("/health")
def health():
    return {"status": "ok"}
