import {
  AccountHealth,
  AccountItem,
  DownloadProfile,
  DownloadQueueItem,
  LogEntry,
  OTSConfig,
  PendingQueueItem,
  QueueBatchAction,
  SpotifyCompanionPairing,
  SystemDiagnostics,
  UpdateInfo,
  YouTubeAuthentication,
  YouTubeAuthenticationStatus
} from "../types";

function getInitialBackendUrl(): string {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  if (typeof window !== "undefined") {
    const origin = window.location.origin || "";
    // If running in Tauri or embedded desktop environment, target local backend
    if (
      origin.includes("tauri") ||
      origin.startsWith("tauri:") ||
      "__TAURI_INTERNALS__" in window ||
      "__TAURI__" in window
    ) {
      return "http://127.0.0.1:6767";
    }
    return origin;
  }
  return "http://127.0.0.1:6767";
}

const DEFAULT_URL = getInitialBackendUrl();
const STORAGE_KEY = "OTS_FASTAPI_URL";

const FALLBACK_CONFIG: OTSConfig = {
  version: "2.0.3",
  debug_mode: false,
  language_index: 0,
  language: "en_US",
  total_downloaded_items: 0,
  total_downloaded_data: 0,
  m3u_format: "m3u8",
  use_double_digit_path_numbers: false,
  ffmpeg_args: [],
  active_account_number: 0,
  accounts: [],
  use_webui_login: false,
  webui_username: "",
  webui_password: "",
  theme: "dark",
  explicit_label: "🅴",
  download_copy_btn: false,
  download_open_btn: false,
  download_locate_btn: true,
  download_delete_btn: true,
  show_search_thumbnails: true,
  show_download_thumbnails: true,
  thumbnail_size: 60,
  max_search_results: 10,
  disable_download_popups: false,
  windows_10_explorer_thumbnails: false,
  mirror_spotify_playback: false,
  close_to_tray: false,
  check_for_updates: false,
  illegal_character_replacement: "-",
  raw_media_download: false,
  rotate_active_account_number: false,
  download_delay: 10,
  download_delay_variance: 5,
  download_chunk_size: 50000,
  maximum_queue_workers: 1,
  maximum_download_workers: 1,
  enable_retry_worker: false,
  retry_worker_delay: 10,
  api_retry_max_attempts: 3,
  api_retry_base_delay: 2,
  api_retry_max_delay: 60,
  api_request_delay: 1,
  cache_api_calls: true,
  api_response_cache_ttl_seconds: 86400,
  spotify_metadata_cache_ttl_seconds: 604800,
  spotify_search_cache_ttl_seconds: 900,
  playlist_automation_cache_ttl_seconds: 60,
  spotify_connect_port: 6768,
  spotify_webapi_override_client_id: "",
  spotify_webapi_override_client_secret: "",
  cache_metadata_in_queue: true,
  fetch_genre_metadata: false,
  fetch_extended_album_metadata: false,
  fetch_audio_features: false,
  fetch_track_credits: false,
  enable_search_tracks: true,
  enable_search_albums: true,
  enable_search_playlists: true,
  enable_search_artists: true,
  enable_search_episodes: true,
  enable_search_podcasts: true,
  enable_search_audiobooks: true,
  f_search_tracks: false,
  f_search_albums: false,
  f_search_artists: false,
  f_search_playlists: false,
  search_prefix: "the",
  download_queue_show_waiting: true,
  download_queue_show_failed: true,
  download_queue_show_cancelled: true,
  download_queue_show_unavailable: true,
  download_queue_show_completed: true,
  audio_download_path: "",
  track_path_formatter: "{artist} - {name}",
  podcast_file_format: "mp3",
  podcast_path_formatter: "Episodes/{album}/{name}",
  use_playlist_path: false,
  playlist_path_formatter: "{artist} - {name}",
  create_m3u_file: false,
  m3u_path_formatter: "M3U/{playlist_name} by {playlist_owner}",
  extinf_separator: "; ",
  extinf_label: "{playlist_number}. {artist} - {name}",
  save_album_cover: false,
  album_cover_format: "png",
  file_hertz: 44100,
  use_custom_file_bitrate: false,
  normalize_audio: false,
  normalize_target_lufs: -14.0,
  normalize_target_tp: -1.0,
  normalize_target_lra: 11.0,
  use_source_format: false,
  prefer_best_source_format: true,
  download_lyrics: false,
  only_download_synced_lyrics: false,
  only_download_plain_lyrics: false,
  save_lrc_file: false,
  translate_file_path: false,
  metadata_separator: "; ",
  overwrite_existing_metadata: false,
  embed_branding: false,
  embed_cover: true,
  embed_artist: true,
  embed_album: true,
  embed_albumartist: true,
  embed_name: true,
  embed_year: true,
  embed_discnumber: true,
  embed_tracknumber: true,
  embed_genre: true,
  embed_performers: false,
  embed_producers: false,
  embed_writers: true,
  embed_composer: true,
  prefer_composer_as_album_artist: false,
  shorten_composer_tag: false,
  embed_label: true,
  embed_copyright: true,
  embed_description: true,
  embed_language: true,
  embed_isrc: true,
  embed_length: true,
  embed_url: true,
  embed_key: true,
  embed_bpm: true,
  embed_compilation: true,
  embed_lyrics: true,
  embed_explicit: false,
  embed_upc: false,
  embed_service_id: false,
  embed_timesignature: false,
  embed_acousticness: false,
  embed_danceability: false,
  embed_energy: false,
  embed_instrumentalness: false,
  embed_liveness: false,
  embed_loudness: false,
  embed_speechiness: false,
  embed_valence: false,
  video_download_path: "",
  movie_file_format: "mkv",
  movie_path_formatter: "Movies/{name} ({release_year})",
  show_file_format: "mkv",
  show_path_formatter: "Shows/{show_name}/Season {season_number}/{episode_number}. {name}",
  preferred_video_resolution: 1080,
  download_subtitles: false,
  download_chapters: false,
  preferred_audio_language: "en-US",
  preferred_subtitle_language: "en-US",
  download_all_available_audio: false,
  download_all_available_subtitles: false,
  v2a_enable: false,
  v2a_preferred_codec: "mp3",
  v2a_preferred_bitrate: 192,
  auto_fallback_search: true
};

const FALLBACK_PROFILES: DownloadProfile[] = [
  { id: "mp3-320", name: "MP3 · 320 kbps", format: "mp3", bitrate: 320, download_path: "" },
  { id: "flac", name: "FLAC · lossless", format: "flac", bitrate: 1411, download_path: "" }
];

export const DEFAULT_CONFIG: OTSConfig = await fetchOTSConfig().catch(() => FALLBACK_CONFIG);

// Default Download Profiles
export const DEFAULT_PROFILES: DownloadProfile[] = await fetchProfiles().catch(() => FALLBACK_PROFILES);

export function getTargetBackendUrl(): string {
  if (typeof window === "undefined") return DEFAULT_URL;
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && !stored.includes("tauri") && !stored.startsWith("tauri:")) {
    return stored;
  }
  return DEFAULT_URL;
}

export function setTargetBackendUrl(url: string): void {
  if (typeof window === "undefined") return;
  const cleaned = url.trim().replace(/\/$/, "");
  if (!cleaned) {
    localStorage.removeItem(STORAGE_KEY);
  } else {
    localStorage.setItem(STORAGE_KEY, cleaned);
  }
}

function getEndpoint(path: string): string {
  const base = getTargetBackendUrl().replace(/\/$/, "");
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${base}${cleanPath}`;
}

async function request(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const url = getEndpoint(path);
  const headers = new Headers(options.headers || {});
  if (
    !headers.has("Content-Type") &&
    options.body &&
    !(typeof FormData !== "undefined" && options.body instanceof FormData)
  ) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(url, { ...options, headers });
}

export async function checkServerHealth(): Promise<{
  status: "online" | "offline";
  version: string;
  target: string;
}> {
  const target = getTargetBackendUrl();
  if (target) {
    try {
      const res = await fetch(`${target}/config/get`, { signal: AbortSignal.timeout(2000) });
      if (res.ok) {
        const data = await res.json();
        return { status: "online", version: data.version || "FastAPI Engine", target };
      }
    } catch {
      // Offline
    }
  }
  return {
    status: "offline",
    version: "",
    target: target || "No target backend URL configured",
  };
}

export async function testBackendConnection(targetUrl: string): Promise<boolean> {
  const target = getTargetBackendUrl();
  if (!target) return false;
  try {
    const res = await fetch(`${target}/config/get`, { signal: AbortSignal.timeout(2500) });
    return res.ok;
  } catch {
    return false;
  }
}

export async function fetchOTSConfig(): Promise<OTSConfig> {
  const res = await request("/config/get");
  if (!res.ok) throw new Error("Failed to fetch configuration");
  return await res.json();
}

export async function saveOTSConfig(): Promise<boolean> {
  try {
    const res = await request("/config/save", { method: "POST" });
    return res.ok;
  } catch (err) {
    console.error("Save config failed:", err);
    return false;
  }
}

export async function resetOTSConfig(): Promise<OTSConfig> {
  const res = await request("/config/reset", { method: "POST" });
  if (!res.ok) throw new Error("Failed to reset configuration");
  return await res.json();
}

export async function browseFolder(key: string = "audio_download_path"): Promise<{ success: boolean; path: string }> {
  const res = await request("/config/browse-folder", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ key }),
  });
  if (!res.ok) throw new Error("Failed to open directory browser");
  return await res.json();
}
export async function updateOTSConfigValue<K extends keyof OTSConfig>(
  key: K,
  value: OTSConfig[K]
): Promise<boolean> {
  const payload = {
    [key]: value,
  };

  const response = await request(`/config/set`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json();
    console.error(
      errorData.detail 
        ? (typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail))
        : `Failed to update setting '${String(key)}' (Status ${response.status})`
    );
    return false
  } else {
    return response.ok
  }
}

export async function fetchDownloadQueue(): Promise<DownloadQueueItem[]> {
  const res = await request("/queue/downloads");
  if (!res.ok) throw new Error("Failed to fetch download queue");
  const data = await res.json();
  return Array.isArray(data) ? data : Object.values(data);
}

export async function addToQueue(
  item: string
): Promise<any> {

  const res = await request(`/query/url?q=${encodeURIComponent(item)}`, {
    method: "POST"
  });
  if (!res.ok) {
    let detail = "Failed to add to queue";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      // body was not JSON; keep the generic message
    }
    throw new Error(detail);
  }
  return res.body
}

export async function executeQueueAction(
  local_id: number,
  action: "cancel" | "delete" | "retry"
): Promise<void> {
  const res = await request(
    `/queue/downloads/action?lid=${encodeURIComponent(local_id)}&action=${encodeURIComponent(action)}`,
    { method: "POST" }
  );
  if (!res.ok) throw new Error("Failed to execute queue action");
}

export async function executeQueueBatchAction(
  local_ids: number[],
  action: QueueBatchAction,
  options?: { profile_id?: string }
): Promise<void> {
  const res = await request("/queue/downloads/batch", {
    method: "POST",
    body: JSON.stringify({ local_ids, action, ...options }),
  });
  if (!res.ok) throw new Error("Failed to execute batch action");
}

export async function clearCompletedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/clear?status=Downloaded");
  if (!res.ok) throw new Error("Failed to clear completed downloads");
}

export async function clearFailedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/clear?status=Failed");
  if (!res.ok) throw new Error("Failed to clear failed downloads");
}

export async function retryFailedDownloads(): Promise<void> {
  const res = await request("/queue/downloads/retryfailed");
  if (!res.ok) throw new Error("Failed to retry failed downloads");
}

export async function toggleQueuePause(): Promise<boolean> {
  throw new Error("Not implemented yet")
  const diag = await fetchSystemDiagnostics();
  const currentPaused = diag.queue.paused;
  const newPaused = !currentPaused;
  const res = await request(`/queue/downloads/pause?paused=${newPaused ? "true" : "false"}`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("Failed to toggle queue pause");
  return newPaused;
}

export async function fetchAccounts(): Promise<AccountItem[]> {
  const res = await request("/accounts/get");
  if (!res.ok) throw new Error("Failed to fetch accounts");
  return await res.json();
}

export async function addAccount(
  service: string,
  credentials: { username?: string; token?: string; password?: string }
): Promise<AccountItem> {
  if (credentials.password && !credentials.token) {
    credentials.token = credentials.password
  }
  const res = await request(`/accounts/add?service=${encodeURIComponent(service)}`, {
    method: "POST",
    body: JSON.stringify(credentials),
  });
  if (!res.ok) throw new Error("Failed to add account");
  const data = await res.json();
  return data.account || data;
}

export async function removeAccount(uuid: string): Promise<boolean> {
  const res = await request(`/accounts/remove?luuid=${encodeURIComponent(uuid)}`, {
    method: "POST",
  });
  return res.ok;
}

export async function reconnectAccounts(): Promise<boolean> {
  const res = await request("/accounts/reconnect", { method: "POST" });
  return res.ok;
}

export async function createSpotifyCompanionPairing(): Promise<SpotifyCompanionPairing | null> {
  const res = await request("/accounts/spotify/companion/pair", { method: "POST" });
  if (!res.ok) throw new Error("Failed to create companion pairing");
  return await res.json();
}

export async function fetchYouTubeAuthenticationStatus(): Promise<YouTubeAuthenticationStatus | null> {
  const res = await request("/accounts/youtube-auth/status");
  if (!res.ok) return null;
  return await res.json();
}

export async function configureYouTubeAuthentication(
  authentication: YouTubeAuthentication
): Promise<boolean> {
  const res = await request("/accounts/youtube-auth", {
    method: "POST",
    body: JSON.stringify(authentication),
  });
  return res.ok;
}

export async function uploadYouTubeCookies(
  file: File
): Promise<YouTubeAuthenticationStatus | null> {
  const form = new FormData();
  form.append("cookies", file);
  const res = await request("/accounts/youtube-auth/upload", {
    method: "POST",
    body: form,
  });
  if (!res.ok) throw new Error("Failed to upload YouTube cookies");
  return await res.json();
}

export async function fetchAccountHealth(): Promise<AccountHealth> {
  const res = await request("/accounts/health");
  if (!res.ok) throw new Error("Failed to fetch account health");
  return await res.json();
}

export async function fetchProfiles(): Promise<DownloadProfile[]> {
  const res = await request("/profiles");
  if (!res.ok) throw new Error("Failed to fetch download profiles");
  const data = await res.json();
  return Array.isArray(data) ? data : data.profiles || [];
}

export async function saveProfile(profile: DownloadProfile): Promise<DownloadProfile> {
  const res = await request("/profiles", {
    method: "POST",
    body: JSON.stringify(profile),
  });
  if (!res.ok) throw new Error("Failed to save profile");
  return await res.json();
}

export async function deleteProfile(profileId: string): Promise<boolean> {
  const res = await request(`/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE",
  });
  return res.ok;
}

export async function activateProfile(profileId: string): Promise<boolean> {
  const res = await request("/profiles/active", {
    method: "POST",
    body: JSON.stringify({ profile_id: profileId }),
  });
  return res.ok;
}

export async function fetchSystemDiagnostics(): Promise<SystemDiagnostics> {
  const res = await request("/system/diagnostics");
  if (!res.ok) throw new Error("Failed to fetch system diagnostics");
  return await res.json();
}

export async function fetchUpdateInfo(force = false): Promise<UpdateInfo> {
  const suffix = force ? "?force=true" : "";
  const res = await request(`/updates/check${suffix}`);
  if (!res.ok) throw new Error("Failed to check for updates");
  return await res.json();
}

export async function fetchLogs(): Promise<LogEntry[]> {
  const res = await request("/logs");
  if (!res.ok) throw new Error("Failed to fetch server logs");
  return await res.json();
}

export async function clearLogs(): Promise<void> {
  const res = await request("/logs/clear", { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear server logs");
}


export async function fetchPendingQueue(): Promise<PendingQueueItem[]> {
  const res = await request("/queue/pending");
  if (!res.ok) throw new Error("Failed to fetch pending queue");
  const data = await res.json();
  return Array.isArray(data.items) ? data.items : Object.values(data);
}


export async function removePendingItems(pendingIds: string[]): Promise<boolean> {
  const res = await request("/queue/pending/remove", {
    method: "POST",
    body: JSON.stringify({ pending_ids: pendingIds }),
  });
  return res.ok;
}

export async function clearAllPending(): Promise<void> {
  const res = await request("/queue/pending/clear", { method: "POST" });
  if (!res.ok) throw new Error("Failed to clear all pending items");
}
