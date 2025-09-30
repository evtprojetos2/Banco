# api/index.py

import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional

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
    # O 'seasons' é o campo chave para suas rotas de temporada/episódio
    seasons: List[SeasonDetail]


# --- 2. CARREGAMENTO DOS DADOS ---

# Obtém o caminho absoluto para o arquivo JSON (assumindo animes.json está na raiz)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# O 'os.path.join(BASE_DIR, '..', 'animes.json')' retorna ao diretório raiz
DATA_FILE_PATH = os.path.join(BASE_DIR, '..', 'animes.json')

anime_data: List[Anime] = []

try:
    # Tenta carregar os dados usando o caminho calculado
    with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        # O Pydantic valida e carrega apenas itens com a chave 'seasons'
        anime_data = [Anime.parse_obj(item) for item in data if 'seasons' in item]
except FileNotFoundError:
    print(f"ERRO: O arquivo '{DATA_FILE_PATH}' não foi encontrado.")
except json.JSONDecodeError:
    print("ERRO: O arquivo 'animes.json' está mal formatado (JSON inválido).")
except Exception as e:
    print(f"ERRO ao carregar dados: {e}")


# Cria um dicionário para busca rápida por 'slug' (URL amigável)
ANIME_SLUG_MAP = {anime.slug: anime for anime in anime_data}


# --- 3. INICIALIZAÇÃO DA API ---

app = FastAPI(
    title="Anime Database API",
    description="API simples para acesso aos dados de animes, temporadas e episódios, hospedada no Vercel.",
    version="1.0.0"
)


# --- 4. DEFINIÇÃO DAS ROTAS (Endpoints) ---

@app.get("/", summary="Root: Status da API")
def read_root():
    return {"status": "ok", "message": "API de Animes funcionando. Acesse /docs para a documentação interativa."}

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

# ROTA PRINCIPAL SOLICITADA: Temporadas e Episódios
@app.get(
    "/animes/{anime_slug}/seasons/{season_index}", 
    response_model=SeasonDetail, 
    summary="Obtém os detalhes e episódios de uma temporada específica"
)
def get_season_episodes(anime_slug: str, season_index: int):
    """
    Retorna a lista de episódios de uma temporada específica de um anime.
    
    - **anime_slug**: O slug do anime (ex: 'gakuen-babysitters').
    - **season_index**: O índice da temporada, começando em **1**.
    """
    if anime_slug not in ANIME_SLUG_MAP:
        raise HTTPException(status_code=404, detail="Anime não encontrado.")
    
    anime = ANIME_SLUG_MAP[anime_slug]
    
    # O índice da lista é season_index - 1
    list_index = season_index - 1
    
    if list_index < 0 or list_index >= len(anime.seasons):
        raise HTTPException(status_code=404, detail=f"Temporada {season_index} não encontrada para o anime '{anime.title}'.")
        
    return anime.seasons[list_index]
