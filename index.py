# api/index.py

import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

# Usaremos apenas RedirectResponse para garantir a reprodução
from fastapi.responses import RedirectResponse 

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

# ROTA MODIFICADA: Redireciona para garantir a reprodução.
@app.get(
    "/animes/{anime_slug}/seasons/{season_index}/{episode_number}", 
    summary="Redireciona o player diretamente para o link de reprodução real."
)
def get_specific_episode_redirect(anime_slug: str, season_index: int, episode_number: str):
    """
    Busca o link do player no JSON e retorna um redirecionamento 307.
    Esta é a forma mais confiável de garantir a reprodução em qualquer player.
    """
    # 1. Encontra o anime
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    anime = ANIME_SLUG_MAP[anime_slug]
    
    # 2. Encontra a temporada
    list_index = season_index - 1
    if list_index < 0 or list_index >= len(anime.seasons):
        raise HTTPException(status_code=404, detail=f"Temporada {season_index} não encontrada.")
    season = anime.seasons[list_index]
    
    # 3. Encontra o episódio
    episode = next(
        (ep for ep in season.episodes if ep.episode_number == episode_number), 
        None
    )
            
    if not episode or not episode.player_urls:
        raise HTTPException(status_code=404, detail=f"Episódio {episode_number} não encontrado ou sem links de player.")
        
    # 4. Redirecionamento (Ação Principal)
    if episode.player_urls:
        # Pega o PRIMEIRO link da lista 'player_urls'
        player_url = episode.player_urls[0]
        # Retorna a resposta de redirecionamento 307 (Temporary Redirect)
        # O player seguirá este link e iniciará a reprodução.
        return RedirectResponse(url=player_url, status_code=307)
    else:
        raise HTTPException(status_code=404, detail=f"Episódio {episode_number} encontrado, mas sem links de player disponíveis.")
        
