import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path

# --- 1. DEFINIÇÃO DA ESTRUTURA DE DADOS (Pydantic Models) ---

# Define a estrutura de um Episódio
class Episode(BaseModel):
    episode_number: str
    title: str
    player_urls: List[str]

# Define a estrutura de uma Temporada (com os episódios completos)
class SeasonDetail(BaseModel):
    season_name: str
    episodes: List[Episode]

# Define a estrutura resumida de um Anime (para listagem)
class AnimeSummary(BaseModel):
    id: str
    title: str
    slug: str
    release: str
    imdb_rating: str
    time: str

# Define a estrutura completa de um Anime
class Anime(AnimeSummary):
    genre: str
    image: str
    details: dict
    synopsis: str
    genres: List[str]
    cover_url: str
    seasons: List[SeasonDetail]


# --- 2. CARREGAMENTO DOS DADOS (DIAGNÓSTICO ROBUSTO) ---

DATA_FILE_NAME = 'animes.json'
anime_data: List[Anime] = []
load_status = "PENDING"
error_detail = None
final_path_used = "N/A"

# Tenta encontrar e carregar o arquivo
try:
    path_attempt_1 = Path(__file__).parent.parent / DATA_FILE_NAME
    path_attempt_2 = Path(os.getcwd()) / DATA_FILE_NAME

    if path_attempt_1.exists():
        final_path_used = path_attempt_1
    elif path_attempt_2.exists():
        final_path_used = path_attempt_2
    else:
        raise FileNotFoundError(f"O arquivo '{DATA_FILE_NAME}' não foi encontrado. Tentativas: [{path_attempt_1}, {path_attempt_2}]")
        
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


# Cria o mapa de busca rápida por slug
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
    """Retorna o status da API e detalhes do carregamento de dados para diagnóstico."""
    return {
        "status": "ok" if load_status == "SUCCESS" else "ERROR", 
        "message": "Verifique 'load_status' e 'error_detail' para diagnosticar o problema.",
        "load_status": load_status,
        "error_detail": error_detail,
        "data_count": len(anime_data),
        "path_used": str(final_path_used),
        "current_working_directory": os.getcwd()
    }

@app.get("/animes", response_model=List[AnimeSummary], summary="Lista todos os animes")
def list_animes():
    """Retorna uma lista resumida de todos os animes disponíveis."""
    return list(ANIME_SLUG_MAP.values())

@app.get("/animes/{anime_slug}", response_model=Anime, summary="Obtém detalhes de um anime específico")
def get_anime_details(anime_slug: str):
    """Retorna os detalhes completos de um anime usando o seu slug (ex: 'gakuen-babysitters')."""
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    
    return ANIME_SLUG_MAP[anime_slug]

@app.get(
    "/animes/{anime_slug}/seasons/{season_index}", 
    response_model=SeasonDetail, 
    summary="Obtém os detalhes e episódios de uma temporada específica"
)
def get_season_episodes(anime_slug: str, season_index: int):
    """
    Retorna a lista de episódios de uma temporada específica de um anime.
    """
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    
    anime = ANIME_SLUG_MAP[anime_slug]
    
    list_index = season_index - 1
    
    if list_index < 0 or list_index >= len(anime.seasons):
        raise HTTPException(status_code=404, detail=f"Temporada {season_index} não encontrada para o anime '{anime.title}'.")
        
    return anime.seasons[list_index]

# ROTA NOVA E FINAL: Episódio Específico
@app.get(
    "/animes/{anime_slug}/seasons/{season_index}/{episode_number}", 
    response_model=Episode, 
    summary="Obtém os detalhes de um episódio específico"
)
def get_specific_episode(anime_slug: str, season_index: int, episode_number: str):
    """
    Retorna um episódio específico de uma temporada.
    
    - **anime_slug**: Slug do anime (ex: 'gakuen-babysitters').
    - **season_index**: Índice da temporada, começando em **1**.
    - **episode_number**: Número do episódio (ex: '1' ou '12').
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
    for episode in season.episodes:
        # Compara o 'episode_number' da URL (string) com o valor no JSON (string)
        if episode.episode_number == episode_number:
            return episode
            
    # 4. Episódio não encontrado
    raise HTTPException(status_code=404, detail=f"Episódio {episode_number} não encontrado na Temporada {season_index}.")
