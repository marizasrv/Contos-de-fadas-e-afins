
import os
import re
import io
import json
import base64
import tempfile
from pathlib import Path

import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from openai import OpenAI
from pydub import AudioSegment
from pydub.generators import Sine, WhiteNoise

st.set_page_config(
    page_title="Contos Mágicos IA",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
.block-container {
    padding-top: 1rem;
    padding-bottom: 4rem;
    max-width: 1100px;
}
.hero {
    padding: 1.2rem 1.2rem;
    border-radius: 24px;
    background: linear-gradient(135deg, rgba(105,76,255,.20), rgba(255,105,180,.14));
    border: 1px solid rgba(150,150,180,.20);
    margin-bottom: 1rem;
}
.card {
    border: 1px solid rgba(150,150,180,.18);
    padding: 1rem;
    border-radius: 18px;
    margin: .7rem 0;
}
.stButton > button {
    min-height: 52px;
    border-radius: 14px;
    font-weight: 700;
}
@media (max-width: 700px) {
    .block-container {padding-left: .8rem; padding-right: .8rem;}
    .hero h1 {font-size: 1.8rem;}
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="hero">
<h1>✨ Contos Mágicos IA</h1>
<p>Crie histórias infantis completas para YouTube pelo celular.</p>
</div>
""", unsafe_allow_html=True)

DEFAULTS = {
    "roteiro": None,
    "imagens": {},
    "audios": {},
    "video_path": None,
    "capa": None,
    "personagens_salvos": [],
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

VOZES = [
    "marin", "cedar", "coral", "nova", "shimmer", "sage",
    "alloy", "ash", "ballad", "echo", "fable", "onyx", "verse"
]

def obter_api_key():
    # 1) Secret do Streamlit Cloud
    try:
        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
    except Exception:
        pass

    # 2) Variável de ambiente (Render/Docker/local)
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key

    return None

API_KEY = obter_api_key()

def get_client():
    if not API_KEY:
        st.error(
            "A chave OPENAI_API_KEY ainda não foi configurada no servidor. "
            "Veja o README para publicar o app com segurança."
        )
        st.stop()
    return OpenAI(api_key=API_KEY)

with st.sidebar:
    st.header("⚙️ Configurações")
    formato = st.selectbox("Formato", ["YouTube 16:9", "Shorts 9:16"])
    num_cenas = st.slider("Cenas", 4, 10, 6)
    voz_narradora = st.selectbox("Voz da narradora", VOZES, index=0)
    qualidade = st.selectbox("Qualidade das imagens", ["low", "medium", "high"], index=1)
    usar_musica = st.toggle("Música de fundo", value=True)
    usar_efeitos = st.toggle("Efeitos sonoros", value=True)
    musica_upload = st.file_uploader(
        "Música própria (opcional)",
        type=["mp3", "wav", "m4a", "aac", "ogg"]
    )
    st.caption("A API pode gerar cobrança conforme o uso.")

tab_criar, tab_personagens, tab_resultado = st.tabs(
    ["✨ Criar", "👧 Personagens", "🎬 Resultado"]
)

with tab_criar:
    tema = st.text_input(
        "🌟 Tema da história",
        placeholder="Ex.: Lili e a Floresta Encantada"
    )
    c1, c2 = st.columns(2)
    with c1:
        idade = st.selectbox("Faixa etária", ["3–5 anos", "6–8 anos", "9–11 anos"])
    with c2:
        estilo = st.selectbox(
            "Estilo",
            ["Conto de fadas mágico", "Aventura leve", "Mistério infantil", "Conto sombrio suave"]
        )

    tipo_final = st.selectbox(
        "Final",
        ["Feliz", "Reconfortante", "Com pequena lição"]
    )

def parse_json(texto):
    texto = texto.strip()
    texto = re.sub(r"^```json\s*", "", texto)
    texto = re.sub(r"\s*```$", "", texto)
    return json.loads(texto)

def texto_personagens_salvos():
    if not st.session_state.personagens_salvos:
        return "Nenhum."
    return "\n".join(
        f'- {p["nome"]}: {p["aparencia"]}; voz: {p["voz"]}'
        for p in st.session_state.personagens_salvos
    )

def criar_roteiro():
    c = get_client()
    prompt = f"""
Crie um roteiro infantil em português do Brasil para um vídeo.

Tema: {tema}
Faixa etária: {idade}
Estilo: {estilo}
Final: {tipo_final}
Formato: {formato}
Número exato de cenas: {num_cenas}

Personagens salvos:
{texto_personagens_salvos()}

Retorne SOMENTE JSON válido:
{{
  "titulo": "título",
  "descricao_youtube": "descrição curta",
  "texto_capa": "até 5 palavras",
  "prompt_capa": "descrição visual da thumbnail, sem texto",
  "personagens": [
    {{
      "nome": "nome",
      "aparencia": "descrição visual detalhada e fixa",
      "personalidade_voz": "descrição curta da voz"
    }}
  ],
  "cenas": [
    {{
      "numero": 1,
      "titulo": "título curto",
      "descricao_visual": "descrição da cena",
      "narracao": "narração curta",
      "falas": [
        {{"personagem": "Nome", "texto": "fala"}}
      ],
      "efeito": "nenhum|magia|vento|passos|porta|suspense|passaros",
      "prompt_imagem": "prompt detalhado sem texto na imagem"
    }}
  ]
}}

Regras:
- exatamente {num_cenas} cenas;
- conteúdo apropriado para crianças;
- sem violência gráfica;
- aparência consistente dos personagens;
- sem texto escrito dentro das imagens;
- final {tipo_final.lower()}.
"""
    with st.spinner("📖 Criando história..."):
        r = c.responses.create(model="gpt-5-mini", input=prompt)
        st.session_state.roteiro = parse_json(r.output_text)
        st.session_state.imagens = {}
        st.session_state.audios = {}
        st.session_state.video_path = None
        st.session_state.capa = None

def salvar_personagens():
    if not st.session_state.roteiro:
        return
    atuais = {p["nome"].lower(): p for p in st.session_state.personagens_salvos}
    for i, p in enumerate(st.session_state.roteiro.get("personagens", [])):
        anterior = atuais.get(p["nome"].lower(), {})
        atuais[p["nome"].lower()] = {
            "nome": p["nome"],
            "aparencia": p["aparencia"],
            "voz": anterior.get("voz", VOZES[(i + 1) % len(VOZES)]),
        }
    st.session_state.personagens_salvos = list(atuais.values())

def mapa_vozes():
    mapa = {}
    for i, p in enumerate(st.session_state.roteiro.get("personagens", [])):
        salvo = next(
            (x for x in st.session_state.personagens_salvos
             if x["nome"].lower() == p["nome"].lower()),
            None
        )
        mapa[p["nome"].lower()] = (
            salvo["voz"] if salvo else VOZES[(i + 1) % len(VOZES)]
        )
    return mapa

def tts(texto, voz, instrucao):
    c = get_client()
    r = c.audio.speech.create(
        model="gpt-4o-mini-tts",
        voice=voz,
        input=texto[:4096],
        instructions=instrucao,
        response_format="mp3",
    )
    return AudioSegment.from_file(io.BytesIO(r.read()), format="mp3")

def efeito_sonoro(nome):
    nome = (nome or "nenhum").lower()
    if nome == "magia":
        return (
            Sine(880).to_audio_segment(duration=160).fade_out(150)
            + Sine(1175).to_audio_segment(duration=220).fade_out(210)
        ) - 16
    if nome == "vento":
        return WhiteNoise().to_audio_segment(duration=1000).low_pass_filter(900).fade_in(180).fade_out(300) - 29
    if nome == "passos":
        base = AudioSegment.silent(duration=900)
        for pos in [100, 380, 660]:
            base = base.overlay(
                Sine(95).to_audio_segment(duration=90).fade_out(80) - 19,
                position=pos
            )
        return base
    if nome == "porta":
        return Sine(120).to_audio_segment(duration=400).fade_out(380) - 20
    if nome == "suspense":
        return Sine(175).to_audio_segment(duration=950).fade_in(180).fade_out(350) - 26
    if nome == "passaros":
        base = AudioSegment.silent(duration=950)
        for pos, freq in [(100, 1500), (350, 1850), (650, 1600)]:
            base = base.overlay(
                Sine(freq).to_audio_segment(duration=90).fade_out(70) - 24,
                position=pos
            )
        return base
    return AudioSegment.silent(duration=100)

def gerar_audio_cena(cena):
    blocos = []

    if cena.get("narracao", "").strip():
        blocos.append(
            tts(
                cena["narracao"],
                voz_narradora,
                "Fale em português do Brasil como narradora de conto de fadas infantil, suave, clara e expressiva."
            )
        )

    vozes = mapa_vozes()
    personalidades = {
        p["nome"].lower(): p.get("personalidade_voz", "voz infantil natural")
        for p in st.session_state.roteiro.get("personagens", [])
    }

    for fala in cena.get("falas", []):
        nome = fala.get("personagem", "")
        texto = fala.get("texto", "")
        if not texto.strip():
            continue
        blocos.append(
            tts(
                texto,
                vozes.get(nome.lower(), "cedar"),
                f"Fale em português do Brasil. Personagem: {nome}. "
                + personalidades.get(nome.lower(), "voz suave e expressiva")
            )
        )

    audio = AudioSegment.silent(duration=150)
    for bloco in blocos:
        audio += bloco + AudioSegment.silent(duration=160)

    if usar_efeitos:
        audio = audio.overlay(efeito_sonoro(cena.get("efeito")), position=180)

    st.session_state.audios[cena["numero"]] = audio.export(format="mp3").read()

def gerar_imagem(cena):
    c = get_client()
    ficha = "; ".join(
        f'{p["nome"]}: {p["aparencia"]}'
        for p in st.session_state.roteiro.get("personagens", [])
    )
    size = "1536x1024" if formato == "YouTube 16:9" else "1024x1536"
    prompt = f"""
Ilustração infantil cinematográfica.
Personagens consistentes: {ficha}
Cena: {cena["descricao_visual"]}
Detalhes: {cena["prompt_imagem"]}
Sem letras, sem legenda, sem texto e sem marca d'água.
Apropriado para crianças.
"""
    r = c.images.generate(
        model="gpt-image-1",
        prompt=prompt,
        size=size,
        quality=qualidade,
    )
    st.session_state.imagens[cena["numero"]] = base64.b64decode(r.data[0].b64_json)

def gerar_capa():
    c = get_client()
    roteiro = st.session_state.roteiro
    ficha = "; ".join(
        f'{p["nome"]}: {p["aparencia"]}'
        for p in roteiro.get("personagens", [])
    )
    r = c.images.generate(
        model="gpt-image-1",
        prompt=f"""
Thumbnail infantil horizontal 16:9 para YouTube.
Personagens: {ficha}
Cena: {roteiro["prompt_capa"]}
Composição limpa e chamativa.
Deixe espaço no alto para título.
Sem texto, letras, logos ou marca d'água.
""",
        size="1536x1024",
        quality=qualidade,
    )

    raw = base64.b64decode(r.data[0].b64_json)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 78)
    except Exception:
        font = ImageFont.load_default()

    texto = roteiro["texto_capa"].upper()
    bbox = draw.textbbox((0, 0), texto, font=font, stroke_width=6)
    largura = bbox[2] - bbox[0]
    x = max(30, (img.width - largura) // 2)
    draw.text(
        (x, 55), texto, font=font,
        fill="white", stroke_width=7, stroke_fill="black"
    )

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92)
    st.session_state.capa = out.getvalue()

def musica_embutida(duracao):
    notas = [261.63, 329.63, 392.00, 523.25]
    bloco = AudioSegment.silent(duration=0)
    for freq in notas:
        bloco += Sine(freq).to_audio_segment(duration=650).fade_in(80).fade_out(180) - 34
    return (bloco * (duracao // max(1, len(bloco)) + 2))[:duracao]

def obter_musica(duracao):
    if not usar_musica:
        return AudioSegment.silent(duration=duracao)

    if musica_upload is not None:
        musica_upload.seek(0)
        music = AudioSegment.from_file(io.BytesIO(musica_upload.read()))
        return (music * (duracao // max(1, len(music)) + 2))[:duracao] - 23

    return musica_embutida(duracao)

def montar_video():
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips

    cenas = st.session_state.roteiro["cenas"]
    if any(c["numero"] not in st.session_state.imagens for c in cenas):
        st.warning("Ainda faltam imagens.")
        return
    if any(c["numero"] not in st.session_state.audios for c in cenas):
        st.warning("Ainda faltam vozes.")
        return

    work = Path(tempfile.mkdtemp(prefix="contos_magicos_online_"))
    segmentos = [
        AudioSegment.from_file(
            io.BytesIO(st.session_state.audios[c["numero"]]),
            format="mp3"
        )
        for c in cenas
    ]

    voz_total = AudioSegment.silent(duration=0)
    for seg in segmentos:
        voz_total += seg

    audio_final = voz_total.overlay(obter_musica(len(voz_total)))
    audio_path = work / "audio_final.mp3"
    audio_final.export(audio_path, format="mp3", bitrate="160k")

    clips = []
    for cena, seg in zip(cenas, segmentos):
        n = cena["numero"]
        img_path = work / f"cena_{n:02d}.png"
        img_path.write_bytes(st.session_state.imagens[n])
        duracao = len(seg) / 1000.0
        clips.append(ImageClip(str(img_path), duration=duracao))

    visual = concatenate_videoclips(clips, method="compose")
    aud = AudioFileClip(str(audio_path))
    final = visual.with_audio(aud)

    video_path = work / "conto_magico_online.mp4"
    final.write_videofile(
        str(video_path),
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    final.close()
    visual.close()
    aud.close()
    for clip in clips:
        clip.close()

    st.session_state.video_path = str(video_path)

def criar_tudo():
    if not tema.strip():
        st.warning("Digite o tema da história.")
        return

    criar_roteiro()
    salvar_personagens()

    cenas = st.session_state.roteiro["cenas"]
    barra = st.progress(0, text="Criando seu vídeo...")

    total_etapas = len(cenas) * 2 + 2
    etapa = 0

    for cena in cenas:
        with st.spinner(f'🎨 Imagem da cena {cena["numero"]}...'):
            gerar_imagem(cena)
        etapa += 1
        barra.progress(etapa / total_etapas)

        with st.spinner(f'🎙️ Voz da cena {cena["numero"]}...'):
            gerar_audio_cena(cena)
        etapa += 1
        barra.progress(etapa / total_etapas)

    with st.spinner("🖼️ Criando capa..."):
        gerar_capa()
    etapa += 1
    barra.progress(etapa / total_etapas)

    with st.spinner("🎬 Montando MP4..."):
        montar_video()
    barra.progress(1.0, text="✅ Vídeo pronto!")

with tab_criar:
    if st.button("✨ CRIAR VÍDEO COMPLETO", type="primary", use_container_width=True):
        criar_tudo()

    st.caption(
        "O app cria história, imagens, personagens, vozes, efeitos, música, capa e MP4."
    )

with tab_personagens:
    if st.session_state.personagens_salvos:
        for i, p in enumerate(st.session_state.personagens_salvos):
            st.markdown(f"### {p['nome']}")
            st.caption(p["aparencia"])
            nova = st.selectbox(
                f"Voz de {p['nome']}",
                VOZES,
                index=VOZES.index(p["voz"]) if p["voz"] in VOZES else 0,
                key=f"v_{i}"
            )
            st.session_state.personagens_salvos[i]["voz"] = nova
    else:
        st.info("Os personagens aparecerão aqui depois da primeira história.")

with tab_resultado:
    if st.session_state.roteiro:
        r = st.session_state.roteiro
        st.subheader(r["titulo"])
        st.write(r["descricao_youtube"])
        st.write("**Texto da capa:**", r["texto_capa"])

        st.download_button(
            "⬇️ Baixar roteiro",
            json.dumps(r, ensure_ascii=False, indent=2),
            file_name="roteiro.json",
            mime="application/json",
            use_container_width=True,
        )

    if st.session_state.capa:
        st.subheader("🖼️ Capa")
        st.image(st.session_state.capa)
        st.download_button(
            "⬇️ Baixar capa JPEG",
            st.session_state.capa,
            file_name="capa_youtube.jpg",
            mime="image/jpeg",
            use_container_width=True,
        )

    if st.session_state.video_path:
        path = Path(st.session_state.video_path)
        if path.exists():
            data = path.read_bytes()
            st.subheader("🎉 Vídeo pronto")
            st.video(data)
            st.download_button(
                "⬇️ BAIXAR VÍDEO MP4",
                data,
                file_name="conto_magico.mp4",
                mime="video/mp4",
                use_container_width=True,
            )
    elif not st.session_state.roteiro:
        st.info("Crie um vídeo na aba ✨ Criar.")

st.divider()
st.caption("Contos Mágicos IA V5 • feito para funcionar também no celular.")
