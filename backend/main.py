from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import speech_recognition as sr
import requests as req
import os
import uuid
import tempfile
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

HF_API_TOKEN = os.getenv("HF_API_TOKEN")
if not HF_API_TOKEN:
    raise RuntimeError("HF_API_TOKEN is not set in your .env file.")

HF_API_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
HEADERS = {"Authorization": f"Bearer {HF_API_TOKEN}"}

OUTPUTS_DIR = "outputs"
os.makedirs(OUTPUTS_DIR, exist_ok=True)

app = FastAPI()

app.mount("/outputs", StaticFiles(directory=OUTPUTS_DIR), name="outputs")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Voice to Sketch API Running 🎨"}

@app.get("/gallery/")
def get_gallery():
    files = []
    for fname in sorted(os.listdir(OUTPUTS_DIR), reverse=True):
        if fname.endswith(".png"):
            fpath = os.path.join(OUTPUTS_DIR, fname)
            files.append({
                "filename": fname,
                "url": f"http://127.0.0.1:8000/outputs/{fname}",
                "created_at": datetime.fromtimestamp(
                    os.path.getctime(fpath)
                ).strftime("%Y-%m-%d %H:%M:%S")
            })
    return {"images": files}

@app.post("/generate-sketch/")
async def generate_sketch(
    audio: UploadFile = File(...),
    style: str = "pencil sketch"
):
    content_type = audio.content_type or ""
    if not content_type.startswith("audio/"):
        raise HTTPException(
            status_code=400,
            detail=f"Expected audio file, got: {content_type}"
        )

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            tmp.write(await audio.read())
            tmp_path = tmp.name

        recognizer = sr.Recognizer()
        with sr.AudioFile(tmp_path) as source:
            audio_data = recognizer.record(source)

        try:
            text = recognizer.recognize_google(audio_data)
        except sr.UnknownValueError:
            return {"error": "Could not understand audio. Please speak clearly and try again."}
        except sr.RequestError as e:
            return {"error": f"Speech recognition service unavailable: {str(e)}"}

        prompt = f"{text}, {style}, highly detailed, high quality"

        try:
            hf_response = req.post(
                HF_API_URL,
                headers=HEADERS,
                json={"inputs": prompt},
                timeout=60
            )
        except req.exceptions.Timeout:
            return {"error": "Image generation timed out. Please try again."}
        except req.exceptions.ConnectionError:
            return {"error": "Could not connect to Hugging Face API. Check your internet."}

        if hf_response.status_code == 503:
            return {"error": "Model is loading on Hugging Face. Please wait 20 seconds and try again."}
        elif hf_response.status_code == 401:
            return {"error": "Invalid Hugging Face API token. Please check your .env file."}
        elif hf_response.status_code != 200:
            return {"error": f"Hugging Face API error {hf_response.status_code}: {hf_response.text}"}

        content_type_hf = hf_response.headers.get("content-type", "")
        if "image" not in content_type_hf:
            return {"error": f"HF returned non-image response: {hf_response.text[:200]}"}

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:6]
        filename = f"sketch_{timestamp}_{unique_id}.png"
        save_path = os.path.join(OUTPUTS_DIR, filename)

        with open(save_path, "wb") as img_file:
            img_file.write(hf_response.content)

        image_url = f"http://127.0.0.1:8000/outputs/{filename}"

        return {
            "transcribed_text": text,
            "prompt_used": prompt,
            "image_url": image_url,
            "filename": filename
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)