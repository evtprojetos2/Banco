import json
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path # Importação adicionada para gerenciamento de caminho robusto

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


# --- 2. CARREGAMENTO DOS DADOS (CORRIGIDO PARA VERCEL) ---

# Usa pathlib para encontrar o arquivo de dados de forma confiável.
# BASE_DIR é 'api/'
BASE_DIR = Path(__file__).parent
# DATA_FILE_PATH é o arquivo na raiz do projeto '../animes.json'
DATA_FILE_PATH = BASE_DIR.parent / 'animes.json'

anime_data: List[Anime] = []

try:
    # Tenta ler o arquivo usando o caminho absoluto
    with open(DATA_FILE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
        # O Pydantic valida e carrega apenas itens que possuem a chave 'seasons'
        anime_data = [Anime.parse_obj(item) for item in data if 'seasons' in item]
        
except FileNotFoundError:
    print(f"ERRO CRÍTICO: Arquivo de dados não encontrado em {DATA_FILE_PATH}. Confirme se 'animes.json' está na RAIZ do seu repositório.")
except json.JSONDecodeError:
    print("ERRO: O arquivo 'animes.json' está mal formatado (JSON inválido).")
except Exception as e:
    print(f"ERRO desconhecido ao carregar dados: {e}")


# Cria um dicionário para busca rápida por 'slug' (URL amigável)
ANIME_SLUG_MAP = {anime.slug: anime for anime in anime_data}


# --- 3. INICIALIZAÇÃO DA API ---

app = FastAPI(
    title="Anime Database API",
    description="API simples para acesso aos dados de animes, temporadas e episódios.",
    version="1.0.0"
)


# --- 4. DEFINIÇÃO DAS ROTAS (Endpoints) ---

@app.get("/", summary="Root: Status da API")
def read_root():
    # Verifica se os dados foram carregados
    if not anime_data:
        return {"status": "erro", "message": "API de Animes funcionando, mas NENHUM dado foi carregado do animes.json.", "data_count": 0}

    return {"status": "ok", "message": "API de Animes funcionando. Acesse /docs para a documentação interativa.", "data_count": len(anime_data)}

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
