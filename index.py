# api/index.py

import json
import os
import requests # NOVO IMPORT AQUI
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from fastapi.responses import Response, RedirectResponse 

# --- 1. DEFINIÇÃO DA ESTRUTURA DE DADOS (Pydantic Models) ---

class Episode(BaseModel):
    episode_number: str
    title: str
    player_urls: List[str]

class SeasonDetail(BaseModel):
    season_name: str
    episodes: List[Episode]

class AnimeSummary(BaseModel):
    id: str
    title: str
    slug: str
    release: str
    imdb_rating: str
    time: str

class Anime(AnimeSummary):
    genre: str
    image: str
    details: dict
    synopsis: str
    genres: List[str]
    cover_url: str
    seasons: List[SeasonDetail]


# --- 2. CARREGAMENTO DOS DADOS ---

DATA_FILE_NAME = 'animes.json'
anime_data: List[Anime] = []
load_status = "PENDING"
error_detail = None
final_path_used = "N/A"

try:
    path_attempt_1 = Path(__file__).parent.parent / DATA_FILE_NAME
    path_attempt_2 = Path(os.getcwd()) / DATA_FILE_NAME

    if path_attempt_1.exists():
        final_path_used = path_attempt_1
    elif path_attempt_2.exists():
        final_path_used = path_attempt_2
    else:
        raise FileNotFoundError(f"O arquivo '{DATA_FILE_NAME}' não foi encontrado.")
        
    with open(final_path_used, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        anime_data = [Anime.parse_obj(item) for item in data if 'seasons' in item]
        load_status = "SUCCESS"
        
except FileNotFoundError as e:
    load_status = "FILE_NOT_FOUND"
    error_detail = str(e)
except json.JSONDecodeError:
    load_status = "JSON_INVALID"
    error_detail = "O arquivo animes.json está mal formatado (JSON inválido)."
except Exception as e:
    load_status = "UNKNOWN_ERROR"
    error_detail = str(e)

ANIME_SLUG_MAP = {anime.slug: anime for anime in anime_data}


# --- 3. INICIALIZAÇÃO DA API ---

app = FastAPI(
    title="Anime Database API",
    description="API simples para acesso aos dados de animes, temporadas e episódios.",
    version="1.0.0"
)


# --- 4. DEFINIÇÃO DAS ROTAS (Endpoints) ---

@app.get("/", summary="Root: Status e Diagnóstico")
def read_root():
    return {
        "status": "ok" if load_status == "SUCCESS" else "ERROR", 
        "message": "API de Animes funcionando.",
        "load_status": load_status,
        "error_detail": error_detail,
        "data_count": len(anime_data)
    }

@app.get("/animes", response_model=List[AnimeSummary], summary="Lista todos os animes")
def list_animes():
    return list(ANIME_SLUG_MAP.values())

@app.get("/animes/{anime_slug}", response_model=Anime, summary="Obtém detalhes de um anime específico")
def get_anime_details(anime_slug: str):
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    return ANIME_SLUG_MAP[anime_slug]

@app.get(
    "/animes/{anime_slug}/seasons/{season_index}", 
    response_model=SeasonDetail, 
    summary="Obtém os detalhes e episódios de uma temporada específica"
)
def get_season_episodes(anime_slug: str, season_index: int):
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    
    anime = ANIME_SLUG_MAP[anime_slug]
    list_index = season_index - 1
    
    if list_index < 0 or list_index >= len(anime.seasons):
        raise HTTPException(status_code=404, detail=f"Temporada {season_index} não encontrada para o anime '{anime.title}'.")
        
    return anime.seasons[list_index]

# ROTA MODIFICADA: PROXY ROBUSTO PARA MANTER O LINK LIMPO
@app.get(
    "/animes/{anime_slug}/seasons/{season_index}/{episode_number}", 
    # Use Response como tipo de retorno para servir o conteúdo bruto do vídeo/playlist
    response_class=Response, 
    summary="Proxy que serve o conteúdo do player sob esta URL limpa."
)
def serve_episode_content(anime_slug: str, season_index: int, episode_number: str):
    """
    Busca o link do player e retorna o conteúdo do arquivo (M3U8, MP4, etc.),
    mantendo a URL limpa no player.
    """
    # 1. Encontra o episódio
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    anime = ANIME_SLUG_MAP[anime_slug]
    
    list_index = season_index - 1
    if list_index < 0 or list_index >= len(anime.seasons):
        raise HTTPException(status_code=404, detail=f"Temporada {season_index} não encontrada.")
    season = anime.seasons[list_index]
    
    episode = next(
        (ep for ep in season.episodes if ep.episode_number == episode_number), 
        None
    )
            
    if not episode or not episode.player_urls:
        raise HTTPException(status_code=404, detail=f"Episódio {episode_number} não encontrado ou sem links de player.")
        
    player_url = episode.player_urls[0]
    
    # 2. Faz a requisição externa e configura o proxy
    try:
        # Abre o stream da resposta externa
        with requests.get(player_url, stream=True, timeout=30) as r:
            r.raise_for_status() # Lança exceção se for 4xx ou 5xx
            
            # Cabeçalhos a serem copiados do link externo para o seu link
            # Isso é CRUCIAL para compatibilidade com players (Content-Type, Content-Length)
            proxy_headers = {}
            for header in ['Content-Type', 'Content-Length', 'Accept-Ranges', 'Transfer-Encoding']:
                if header in r.headers:
                    proxy_headers[header] = r.headers[header]
            
            # Retorna o conteúdo da resposta externa
            # Retorna r.content (todo o conteúdo) ou r.iter_content (streaming chunked)
            # Para vídeos, o iter_content é melhor, mas no Vercel é mais seguro pegar o conteúdo (se o arquivo não for muito grande)
            
            # Tentativa de Proxy 2.0: Usar Response com o conteúdo como bytes
            return Response(
                content=r.content,
                media_type=r.headers.get('Content-Type', 'application/octet-stream'), # Usa o Content-Type real
                headers=proxy_headers
            )
        
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=504, 
            detail="O servidor do player externo demorou muito para responder (Timeout)."
        )
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar URL do player ({player_url}): {e}")
        raise HTTPException(
            status_code=503, 
            detail=f"Não foi possível buscar o conteúdo do player (Erro: {str(e)})."
        )
