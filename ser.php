 <?php
header('Content-Type: application/json; charset=utf-8');

// ================== CONFIG ==================
$tmdb_api_key = "6360eb433f3020d94a5de4f0fb52c720";
$CURL_TIMEOUT = 10;         // seg. por requisição
$CURL_CONNECT_TIMEOUT = 5;  // seg. para conectar

// ================== INPUT ==================
$nome             = $_GET['nome'] ?? '';
$series_id        = $_GET['series_id'] ?? '';
$iptv_category_id = $_GET['category_id'] ?? '';
$iptv_poster      = $_GET['iptv_poster'] ?? '';
$iptv_stream_url  = $_GET['iptv_stream_url'] ?? '';

if (empty($nome) || empty($series_id)) {
    echo json_encode(["error" => "Parâmetros obrigatórios ausentes (nome, series_id)"], JSON_UNESCAPED_UNICODE);
    exit;
}

// ================== HELPERS ==================
function http_get_json($url, $timeout = 10, $connect_timeout = 5) {
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => true,
        CURLOPT_MAXREDIRS => 3,
        CURLOPT_TIMEOUT => $timeout,
        CURLOPT_CONNECTTIMEOUT => $connect_timeout,
        CURLOPT_ENCODING => "", // aceita gzip/deflate
        CURLOPT_USERAGENT => "Mozilla/5.0 (compatible; IPTV-Collector/1.0)"
    ]);
    $resp = curl_exec($ch);
    $err  = curl_error($ch);
    $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);

    if ($resp === false || $code >= 400) {
        return ["_error" => $err ?: ("HTTP ".$code), "_raw" => $resp];
    }
    $json = json_decode($resp, true);
    return $json ?? ["_error" => "JSON inválido", "_raw" => $resp];
}

function iconv_safe($s) {
    $t = @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $s);
    return $t !== false ? $t : $s;
}

/** Normaliza para comparação (sem acentos, minúsculo, sem pontuação/stopwords) */
function normalize_title($s) {
    $s = iconv_safe($s);
    $s = strtolower($s);

    // substitui símbolos comuns
    $s = str_replace(['&', '+'], ' ', $s);

    // remove pontuação
    $s = preg_replace('/[^\p{L}\p{N}\s]/u', ' ', $s);

    // remove stopwords simples
    $stop = [
        'a','o','os','as','de','da','do','das','dos','the','and','e',
        'um','uma','para','por','com','sem','em','na','no','nos','nas'
    ];
    $tokens = preg_split('/\s+/', trim($s));
    $tokens = array_filter($tokens, function($t) use ($stop) {
        return $t !== '' && !in_array($t, $stop);
    });

    return implode(' ', $tokens);
}

/** Limpa o título para busca (remove tags e ruído comum) */
function clean_query_title($title) {
    $t = trim($title);

    // remove conteúdo entre colchetes/parênteses/chaves
    $t = preg_replace('/[\(\[\{][^\)\]\}]*[\)\]\}]/u', ' ', $t);

    // remove termos comuns de “release”
    $t = preg_replace('/\b(temporada|season|dublado|legendado|dual|nacional|original|completo|torrent|1080p|720p|4k|s\d{1,2}e?\d{0,2})\b/iu', ' ', $t);

    // se houver “: temporada x” etc, trunca
    $t = preg_replace('/\b(temporada|season)\b.*$/iu', ' ', $t);

    // normaliza espaços
    $t = preg_replace('/\s+/u', ' ', $t);
    return trim($t);
}

/** Tenta extrair um ano do título (ex.: "Dark (2017)") */
function guess_year_from_title($title) {
    if (preg_match('/\b(19|20)\d{2}\b/', $title, $m)) {
        $y = intval($m[0]);
        if ($y >= 1900 && $y <= intval(date('Y')) + 1) return $y;
    }
    return null;
}

/** Busca no TMDb com idioma e (opcional) ano */
function tmdb_search_with_lang($title, $lang, $api_key, $year = null, $timeout = 10, $connect_timeout = 5) {
    $url = "https://api.themoviedb.org/3/search/tv?api_key={$api_key}&language={$lang}&query=" . urlencode($title);
    if ($year) $url .= "&first_air_date_year=" . intval($year);
    return http_get_json($url, $timeout, $connect_timeout);
}

/** Estratégia de busca robusta: pt-BR → en-US; original → limpo; com/sem ano */
function tmdb_search_series($title, $api_key, $timeout = 10, $connect_timeout = 5) {
    $clean = clean_query_title($title);
    $year  = guess_year_from_title($title);

    $candidates = [];

    // 1) pt-BR, original
    $candidates[] = tmdb_search_with_lang($title, 'pt-BR', $api_key, $year, $timeout, $connect_timeout);
    // 2) en-US, original
    $candidates[] = tmdb_search_with_lang($title, 'en-US', $api_key, $year, $timeout, $connect_timeout);
    // 3) pt-BR, limpo
    if ($clean !== $title) $candidates[] = tmdb_search_with_lang($clean, 'pt-BR', $api_key, $year, $timeout, $connect_timeout);
    // 4) en-US, limpo
    if ($clean !== $title) $candidates[] = tmdb_search_with_lang($clean, 'en-US', $api_key, $year, $timeout, $connect_timeout);
    // 5) pt-BR, limpo, sem ano (caso o ano esteja atrapalhando)
    if ($year) $candidates[] = tmdb_search_with_lang($clean, 'pt-BR', $api_key, null, $timeout, $connect_timeout);
    // 6) en-US, limpo, sem ano
    if ($year) $candidates[] = tmdb_search_with_lang($clean, 'en-US', $api_key, null, $timeout, $connect_timeout);

    // Consolida primeiros resultados válidos
    foreach ($candidates as $res) {
        if (!empty($res['results'])) {
            return $res;
        }
    }

    // Retorna a última resposta (para debug) se nada encontrado
    return end($candidates) ?: ["results" => []];
}

/** Melhor escore de similaridade + popularidade + penalidade por ano */
function score_candidate($query, $cand, $year_guess = null) {
    $qnorm   = normalize_title($query);
    $name    = normalize_title($cand['name'] ?? '');
    $oname   = normalize_title($cand['original_name'] ?? '');

    $p1 = 0; $p2 = 0;
    if ($name !== '' && $qnorm !== '') {
        similar_text($qnorm, $name, $pct1);
        $p1 = $pct1;
    }
    if ($oname !== '' && $qnorm !== '') {
        similar_text($qnorm, $oname, $pct2);
        $p2 = $pct2;
    }
    $sim = max($p1, $p2);

    $pop = floatval($cand['popularity'] ?? 0);

    $score = $sim * 1.2 + $pop; // peso maior para similaridade

    // Penaliza distância de ano (se soubermos)
    if ($year_guess && !empty($cand['first_air_date'])) {
        $y = intval(substr($cand['first_air_date'], 0, 4));
        if ($y > 0) {
            $score -= abs($y - $year_guess) * 2.0;
        }
    }
    return $score;
}

function tmdb_get_details_series($tv_id, $api_key, $timeout = 10, $connect_timeout = 5) {
    $url = "https://api.themoviedb.org/3/tv/{$tv_id}?api_key={$api_key}&language=pt-BR&append_to_response=credits,videos,content_ratings";
    return http_get_json($url, $timeout, $connect_timeout);
}

function tmdb_get_seasons_parallel($tv_id, $seasons, $api_key, $timeout = 10, $connect_timeout = 5) {
    $mh = curl_multi_init();
    $chs = [];
    $responses = [];

    foreach ($seasons as $s) {
        $sn = intval($s['season_number'] ?? 0);
        if ($sn <= 0) continue; // ignora "Specials"

        $url = "https://api.themoviedb.org/3/tv/{$tv_id}/season/{$sn}?api_key={$api_key}&language=pt-BR";
        $ch = curl_init();
        curl_setopt_array($ch, [
            CURLOPT_URL => $url,
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_FOLLOWLOCATION => true,
            CURLOPT_MAXREDIRS => 3,
            CURLOPT_TIMEOUT => $timeout,
            CURLOPT_CONNECTTIMEOUT => $connect_timeout,
            CURLOPT_ENCODING => "",
            CURLOPT_USERAGENT => "Mozilla/5.0 (compatible; IPTV-Collector/1.0)"
        ]);
        curl_multi_add_handle($mh, $ch);
        $chs[$sn] = $ch;
    }

    $running = null;
    do {
        $mrc = curl_multi_exec($mh, $running);
        if ($running) {
            // evita busy loop
            curl_multi_select($mh, 1.0);
        }
    } while ($running && $mrc == CURLM_OK);

    foreach ($chs as $sn => $ch) {
        $raw = curl_multi_getcontent($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $data = ($raw !== false && $code < 400) ? json_decode($raw, true) : null;
        $responses[$sn] = $data ?: [];
        curl_multi_remove_handle($mh, $ch);
        curl_close($ch);
    }
    curl_multi_close($mh);

    return $responses;
}

function get_classification_series($details) {
    if (!empty($details['content_ratings']['results'])) {
        foreach ($details['content_ratings']['results'] as $r) {
            if (($r['iso_3166_1'] ?? '') === 'BR') return $r['rating'] ?? "";
        }
        return $details['content_ratings']['results'][0]['rating'] ?? "";
    }
    return "";
}

/* ================== [ADICIONADO] Helpers IPTV ================== */
/**
 * Extrai domínio (com porta), username e password do iptv_stream_url (player_api.php?username=...&password=...)
 * Retorna array: ['domain' => 'http://host[:port]', 'username' => 'xxx', 'password' => 'yyy']
 */
function xtream_extract_from_player_api($iptv_stream_url) {
    $out = ['domain' => 'http://sinalprivado.info', 'username' => '430214', 'password' => '430214'];
    if (!$iptv_stream_url) return $out;

    $u = parse_url($iptv_stream_url);
    if (!empty($u['scheme']) && !empty($u['host'])) {
        $out['domain'] = $u['scheme'].'://'.$u['host'].(!empty($u['port']) ? ':'.$u['port'] : '');
    }
    if (!empty($u['query'])) {
        parse_str($u['query'], $q);
        if (!empty($q['username'])) $out['username'] = $q['username'];
        if (!empty($q['password'])) $out['password'] = $q['password'];
    }
    return $out;
}

/**
 * Busca na API IPTV (player_api.php) e cria mapa season_episode => id_original
 * Ex.: "1_3" => "655624"
 */
function iptv_build_episode_id_map($iptv_stream_url, $timeout = 10, $connect_timeout = 5) {
    $map = [];
    if (!$iptv_stream_url) return $map;

    $data = http_get_json($iptv_stream_url, $timeout, $connect_timeout);
    if (!empty($data['episodes']) && is_array($data['episodes'])) {
        foreach ($data['episodes'] as $seasonKey => $eps) {
            if (!is_array($eps)) continue;
            foreach ($eps as $ep) {
                $snum = intval($ep['season'] ?? $seasonKey);
                $enum = intval($ep['episode_num'] ?? 0);
                $id   = $ep['id'] ?? null;
                if ($id && $enum > 0) {
                    $map["{$snum}_{$enum}"] = $id;
                }
            }
        }
    }
    return $map;
}
// ================== FIM [ADICIONADO] ==================

// ================== BUSCA TMDB ==================
$search_results = tmdb_search_series($nome, $tmdb_api_key, $CURL_TIMEOUT, $CURL_CONNECT_TIMEOUT);
$results = $search_results['results'] ?? [];

if (empty($results)) {
    echo json_encode([
        "error" => "Série não encontrada no TMDb",
        "debug" => [
            "query_enviada" => $nome,
            "query_limpa"   => clean_query_title($nome),
        ]
    ], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// Matching avançado
$year_guess = guess_year_from_title($nome);
$best = null;
$best_score = -INF;
foreach ($results as $cand) {
    $sc = score_candidate($nome, $cand, $year_guess);
    if ($sc > $best_score) {
        $best_score = $sc;
        $best = $cand;
    }
}

if (!$best || empty($best['id'])) {
    echo json_encode(["error" => "Não foi possível determinar o melhor resultado no TMDb"], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// Detalhes da série
$details = tmdb_get_details_series($best['id'], $tmdb_api_key, $CURL_TIMEOUT, $CURL_CONNECT_TIMEOUT);
if (isset($details['_error'])) {
    echo json_encode(["error" => "Falha ao obter detalhes da série no TMDb", "tmdb_error" => $details['_error']], JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT);
    exit;
}

// Trailer (primeiro "Trailer")
$trailer = "";
foreach ($details['videos']['results'] ?? [] as $v) {
    if (($v['type'] ?? '') === 'Trailer' && !empty($v['key'])) {
        $trailer = "https://www.youtube.com/watch?v=" . $v['key'];
        break;
    }
}

// iptv_stream_url automático (se não enviado)
if (empty($iptv_stream_url)) {
    $iptv_stream_url = "http://sinalprivado.info/player_api.php?username=430214&password=430214&action=get_series_info&series_id={$series_id}";
}

// [ADICIONADO] Carrega config Xtream (domínio/credenciais) e mapa de IDs originais de episódio
$xtream_conf       = xtream_extract_from_player_api($iptv_stream_url);
$iptv_episode_map  = iptv_build_episode_id_map($iptv_stream_url, $CURL_TIMEOUT, $CURL_CONNECT_TIMEOUT);

// Map de gêneros para fallback
$tmdb_genres_map = [
    10759 => "Ação & Aventura", 16 => "Animação", 35 => "Comédia", 80 => "Crime", 99 => "Documentário",
    18 => "Drama", 10751 => "Família", 10762 => "Infantil", 9648 => "Mistério", 10763 => "Notícias",
    10764 => "Reality", 10765 => "Ficção Científica & Fantasia", 10766 => "Soap", 10767 => "Talk",
    10768 => "Guerra & Política", 37 => "Faroeste"
];

if (empty($details['genres']) && !empty($best['genre_ids'])) {
    $details['genres'] = [];
    foreach ($best['genre_ids'] as $gid) {
        $details['genres'][] = ["id" => $gid, "name" => $tmdb_genres_map[$gid] ?? "Desconhecido"];
    }
}

// ================== MONTAGEM DO JSON ==================
// 1) Info geral
$serie = [
    "iptv_series_id"         => $series_id,
    "iptv_category_id"       => $iptv_category_id,
    "iptv_name"              => $nome,
    "iptv_poster"            => $iptv_poster ?: "",

    "titulo_usado"           => $nome,
    "tmdb_id"                => $details['id'] ?? 0,
    "tmdb_name"              => $details['name'] ?? "",
    "tmdb_first_air_date"    => $details['first_air_date'] ?? "",
    "tmdb_popularity"        => $details['popularity'] ?? 0,
    "tmdb_vote_count"        => $details['vote_count'] ?? 0,

    "titulo"                 => $details['name'] ?? "",
    "titulo_original"        => $details['original_name'] ?? "",
    "sinopse"                => $details['overview'] ?? "Descrição não disponível",
    "nota"                   => $details['vote_average'] ?? 0,
    "lancamento"             => $details['first_air_date'] ?? "",
    "numero_temporadas"      => $details['number_of_seasons'] ?? 0,
    "numero_episodios"       => $details['number_of_episodes'] ?? 0,
    "classificacao_indicativa" => get_classification_series($details),
    "poster"                 => !empty($details['poster_path']) ? "https://image.tmdb.org/t/p/w500".$details['poster_path'] : "",
    "backdrop"               => !empty($details['backdrop_path']) ? "https://image.tmdb.org/t/p/w500".$details['backdrop_path'] : "",
    "trailer"                => $trailer
];

// Gêneros como string única
$generos = [];
foreach ($details['genres'] ?? [] as $g) {
    if (!empty($g['name'])) $generos[] = $g['name'];
}
$serie['generos'] = implode(", ", $generos);

// Elenco (até 10)
$elenco = [];
foreach (array_slice($details['credits']['cast'] ?? [], 0, 10) as $c) {
    $elenco[] = [
        "name" => $c['name'] ?? "",
        "foto" => !empty($c['profile_path']) ? "https://image.tmdb.org/t/p/w200".$c['profile_path'] : ""
    ];
}
$serie['elenco'] = $elenco;

// 2) Temporadas (básico)
$temporadas = [];
foreach ($details['seasons'] ?? [] as $s) {
    $temporadas[] = [
        "season_number"  => $s['season_number'] ?? 0,
        "name"           => $s['name'] ?? "",
        "episodios_count"=> $s['episode_count'] ?? 0,
        "poster"         => !empty($s['poster_path']) ? "https://image.tmdb.org/t/p/w500".$s['poster_path'] : ""
    ];
}

// 3) Episódios (detalhado, paralelo)
$episodios = [];
$season_details_all = tmdb_get_seasons_parallel($details['id'], $details['seasons'] ?? [], $tmdb_api_key, $CURL_TIMEOUT, $CURL_CONNECT_TIMEOUT);
foreach ($season_details_all as $season_number => $season_data) {
    foreach ($season_data['episodes'] ?? [] as $ep) {
        $ep_num  = $ep['episode_number'] ?? 0;

        // [ADICIONADO] monta URL usando ID ORIGINAL do IPTV
        $iptv_id = $iptv_episode_map["{$season_number}_{$ep_num}"] ?? null;
        $play_url = "";
        if ($iptv_id) {
            $play_url = $xtream_conf['domain'] . "/series/" . $xtream_conf['username'] . "/" . $xtream_conf['password'] . "/{$iptv_id}.mp4";
        }

        $episodios[] = [
            "season_number"  => $season_number,
            "episode_number" => $ep_num,
            "name"           => $ep['name'] ?? "",
            "overview"       => $ep['overview'] ?? "",
            "air_date"       => $ep['air_date'] ?? "",
            "still_path"     => !empty($ep['still_path']) ? "https://image.tmdb.org/t/p/w300".$ep['still_path'] : "",
            "url"            => $play_url // [ADICIONADO]
        ];
    }
}

$response = [
    "serie"      => $serie,
    "temporadas" => $temporadas,
    "episodios"  => $episodios
];

echo json_encode($response, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT)