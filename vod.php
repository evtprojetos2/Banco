 <?php
header('Content-Type: application/json; charset=utf-8');

$tmdb_api_key = "6360eb433f3020d94a5de4f0fb52c720";

// Recebe parâmetros via GET
$nome = $_GET['nome'] ?? '';
$stream_id = $_GET['stream_id'] ?? '';
$iptv_category_id = $_GET['category_id'] ?? '';
$iptv_poster = $_GET['iptv_poster'] ?? '';
$iptv_stream_url = $_GET['iptv_stream_url'] ?? '';

if (empty($nome) || empty($stream_id)) {
    echo json_encode(["error" => "Parâmetros obrigatórios ausentes (nome, stream_id)"]);
    exit;
}

// ---------------- Funções ----------------
function extract_year_from_name($name) {
    if (preg_match('/(19\d{2}|20\d{2})/', $name, $matches)) return intval($matches[1]);
    return null;
}

function normalize_title($s) {
    $s = strtolower(iconv('UTF-8', 'ASCII//TRANSLIT', $s));
    $s = preg_replace('/[\[\]\(\)\{\}\-_:;.,!?\|\/]/', ' ', $s);
    $s = preg_replace('/\s+/', ' ', $s);
    return trim($s);
}

function tmdb_search($title, $year = null, $api_key) {
    $url = "https://api.themoviedb.org/3/search/movie?api_key=$api_key&language=pt-BR&query=" . urlencode($title);
    if ($year) $url .= "&year=" . intval($year);
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp, true);
}

function tmdb_get_details($movie_id, $api_key) {
    $url = "https://api.themoviedb.org/3/movie/$movie_id?api_key=$api_key&language=pt-BR&append_to_response=credits,videos,release_dates";
    $ch = curl_init();
    curl_setopt($ch, CURLOPT_URL, $url);
    curl_setopt($ch, CURLOPT_RETURNTRANSFER, 1);
    $resp = curl_exec($ch);
    curl_close($ch);
    return json_decode($resp, true);
}

function format_runtime($minutes) {
    if (!$minutes) return "0min";
    $h = floor($minutes / 60);
    $m = $minutes % 60;
    return ($h > 0 ? "{$h}h " : "") . ($m > 0 ? "{$m}min" : "0min");
}

// Função reforçada para classificação indicativa
function get_classification($details) {
    $release_dates = $details['release_dates'] ?? [];
    if (!empty($release_dates['results'])) {
        // 1️⃣ Tenta BR
        foreach ($release_dates['results'] as $release) {
            if ($release['iso_3166_1'] === 'BR') {
                foreach ($release['release_dates'] as $r) {
                    if (!empty($r['certification'])) return $r['certification'];
                }
            }
        }
        // 2️⃣ Tenta US
        foreach ($release_dates['results'] as $release) {
            if ($release['iso_3166_1'] === 'US') {
                foreach ($release['release_dates'] as $r) {
                    if (!empty($r['certification'])) return $r['certification'];
                }
            }
        }
        // 3️⃣ Qualquer outro país
        foreach ($release_dates['results'] as $release) {
            foreach ($release['release_dates'] as $r) {
                if (!empty($r['certification'])) return $r['certification'];
            }
        }
    }
    return "";
}

// ---------------- Processo ----------------
$year = extract_year_from_name($nome);

// Busca filmes no TMDb
$search_results = tmdb_search($nome, $year, $tmdb_api_key);
if (empty($search_results['results'])) {
    echo json_encode(["error" => "Filme não encontrado no TMDb"]);
    exit;
}

// ---------------- Matching avançado ----------------
$nome_norm = normalize_title($nome);
$best_score = -1;
$best_movie = null;

foreach ($search_results['results'] as $movie) {
    $score = 0;
    similar_text($nome_norm, normalize_title($movie['title'] ?? ''), $percent);
    $score += $percent;
    if ($year && !empty($movie['release_date'])) {
        $movie_year = intval(substr($movie['release_date'],0,4));
        $score += ($year == $movie_year) ? 20 : 0;
    }
    $score += $movie['popularity'] ?? 0;
    if ($score > $best_score) {
        $best_score = $score;
        $best_movie = $movie;
    }
}

if (!$best_movie) {
    echo json_encode(["error" => "Não foi possível determinar o melhor resultado no TMDb"]);
    exit;
}

// Detalhes completos do melhor filme
$details = tmdb_get_details($best_movie['id'], $tmdb_api_key);

// Campos principais
$sinopse = !empty($details['overview']) ? $details['overview'] : "Descrição não disponível";
$duracao = !empty($details['runtime']) ? $details['runtime'] : 0;
$duracao_formatada = format_runtime($duracao);
$classificacao = get_classification($details);

// Trailer
$trailer = "";
foreach ($details['videos']['results'] ?? [] as $v) {
    if ($v['type'] === 'Trailer') { $trailer = "https://www.youtube.com/watch?v=".$v['key']; break; }
}

// ---------------- iptv_stream_url automático ----------------
if (empty($iptv_stream_url)) {
    $iptv_stream_url = "http://sinalprivado.info:80/movie/430214/430214/{$stream_id}.mp4";
}

// ---------------- JSON Final ----------------
$response = [
    "iptv_stream_id" => $stream_id,
    "iptv_category_id" => $iptv_category_id,
    "iptv_name" => $nome,
    "iptv_poster" => $iptv_poster ?: "",
    "iptv_stream_url" => $iptv_stream_url,

    "titulo_usado" => $nome,
    "ano_usado" => $year ?: "",
    "tmdb_id" => $details['id'] ?? 0,
    "tmdb_title" => $details['title'] ?? "",
    "tmdb_release_date" => $details['release_date'] ?? "",
    "tmdb_popularity" => $details['popularity'] ?? 0,
    "tmdb_vote_count" => $details['vote_count'] ?? 0,

    "titulo" => $details['title'] ?? "",
    "titulo_original" => $details['original_title'] ?? "",
    "sinopse" => $sinopse,
    "nota" => $details['vote_average'] ?? 0,
    "lancamento" => $details['release_date'] ?? "",
    "duracao" => $duracao,
    "duracao_formatada" => $duracao_formatada,
    "classificacao_indicativa" => $classificacao,
    "poster" => !empty($details['poster_path']) ? "https://image.tmdb.org/t/p/w500".$details['poster_path'] : "",
    "backdrop" => !empty($details['backdrop_path']) ? "https://image.tmdb.org/t/p/w500".$details['backdrop_path'] : "",
    "trailer" => $trailer
];

// Gêneros (no final)
$generos = [];
foreach ($details['genres'] ?? [] as $g) { $generos[] = ["name" => $g['name'] ?? ""]; }
$response['generos'] = $generos;

// Elenco (até 10 atores, com foto)
$elenco = [];
foreach (array_slice($details['credits']['cast'] ?? [], 0, 10) as $c) {
    $elenco[] = [
        "name" => $c['name'] ?? "",
        "foto" => !empty($c['profile_path']) ? "https://image.tmdb.org/t/p/w200".$c['profile_path'] : ""
    ];
}
$response['elenco'] = $elenco;

echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
?