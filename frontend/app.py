import streamlit as st
import requests
import tempfile
import os

st.set_page_config(page_title="Voice to Sketch AI", page_icon="🎨", layout="wide")

st.title("🎨 Voice to Sketch AI")
st.markdown("Speak your idea — watch it turn into a sketch!")

BACKEND_URL = "http://127.0.0.1:8000"

with st.sidebar:
    st.header("⚙️ Settings")

    style = st.selectbox(
        "Choose Sketch Style",
        ["pencil sketch", "cartoon", "watercolor painting", "oil painting", "charcoal drawing"]
    )

    st.markdown("---")
    st.markdown("### 🔗 Backend Status")
    try:
        ping = requests.get(f"{BACKEND_URL}/", timeout=3)
        if ping.status_code == 200 and "Voice to Sketch" in ping.json().get("message", ""):
            st.success("✅ Backend Connected")
        else:
            st.error("❌ Backend Error — Unexpected response")
    except Exception:
        st.error("❌ Backend Offline — Start FastAPI first!")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("🎙️ Record Your Idea")

    audio_value = st.audio_input("Click the mic button below to record your idea")

    if audio_value is not None:
        st.audio(audio_value)

        if st.button("🎨 Generate Sketch from Recording", use_container_width=True):
            tmp_path = None
            try:
                with st.spinner("🎨 Generating your sketch via Hugging Face..."):
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
                        tmp.write(audio_value.getvalue())
                        tmp_path = tmp.name

                    with open(tmp_path, "rb") as f:
                        try:
                            response = requests.post(
                                f"{BACKEND_URL}/generate-sketch/?style={style}",
                                files={"audio": ("audio.wav", f, "audio/wav")},
                                timeout=90
                            )
                        except requests.exceptions.ConnectionError:
                            st.error("❌ Cannot connect to backend. Is FastAPI running?")
                            st.stop()
                        except requests.exceptions.Timeout:
                            st.error("❌ Request timed out. Try again.")
                            st.stop()

                if response.status_code == 200:
                    data = response.json()
                    if "error" in data:
                        st.error(f"⚠️ {data['error']}")
                    else:
                        st.session_state["last_result"] = data
                        st.success("🎉 Sketch generated successfully!")
                        st.rerun()
                else:
                    st.error(f"Backend error (status {response.status_code}): {response.text}")

            except Exception as e:
                st.error(f"Unexpected error: {e}")

            finally:
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

    if "last_result" in st.session_state:
        data = st.session_state["last_result"]
        st.markdown(f"**🗣️ You said:** {data['transcribed_text']}")
        st.markdown(f"**✏️ Prompt used:** {data['prompt_used']}")

with col2:
    st.subheader("🖼️ Generated Sketch")

    if "last_result" in st.session_state:
        data = st.session_state["last_result"]
        st.image(data["image_url"], caption=data["transcribed_text"], use_container_width=True)

        try:
            img_bytes = requests.get(data["image_url"], timeout=15).content
            st.download_button(
                label="⬇️ Download Sketch",
                data=img_bytes,
                file_name=data.get("filename", "sketch.png"),
                mime="image/png",
                use_container_width=True
            )
        except Exception:
            st.warning("Could not load image for download.")
    else:
        st.info("Your generated sketch will appear here.")

st.markdown("---")
st.subheader("🗂️ Saved Sketches Gallery")

if st.button("🔄 Refresh Gallery"):
    st.rerun()

try:
    gallery_response = requests.get(f"{BACKEND_URL}/gallery/", timeout=5)
    if gallery_response.status_code == 200:
        images = gallery_response.json().get("images", [])
        if images:
            cols = st.columns(3)
            for i, item in enumerate(images):
                with cols[i % 3]:
                    st.image(item["url"], use_container_width=True)
                    st.caption(f"🕐 {item['created_at']}")
                    try:
                        img_bytes = requests.get(item["url"], timeout=10).content
                        st.download_button(
                            label="⬇️ Download",
                            data=img_bytes,
                            file_name=item["filename"],
                            mime="image/png",
                            key=f"dl_{item['filename']}"
                        )
                    except Exception:
                        pass
        else:
            st.info("No sketches saved yet. Generate your first one above!")
    else:
        st.warning("Could not load gallery from backend.")
except Exception:
    st.warning("Backend offline — gallery unavailable.")