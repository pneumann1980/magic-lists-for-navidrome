from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Artist(BaseModel):
    """Schema for Navidrome artist"""
    id: str
    name: str
    album_count: int = 0
    song_count: int = 0

class CreatePlaylistRequest(BaseModel):
    """Request schema for creating a playlist"""
    artist_ids: List[str]
    playlist_name: Optional[str] = None  # Optional, will auto-generate if not provided
    refresh_frequency: str = "none"  # "none", "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks

class CreateGenrePlaylistRequest(BaseModel):
    """Request schema for creating a genre mix playlist"""
    genre: str
    playlist_name: Optional[str] = None  # Optional, will auto-generate if not provided
    refresh_frequency: str = "none"  # "none", "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks
    discovery_ratio: float = 0.25  # 0.0 = all familiar, 0.75 = max discovery

class Playlist(BaseModel):
    """Schema for a stored playlist"""
    id: int
    artist_id: str
    playlist_name: str
    songs: List[str] = []
    reasoning: Optional[str] = None
    navidrome_playlist_id: Optional[str] = None
    library_ids: List[str] = []
    created_at: str
    updated_at: str

class Song(BaseModel):
    """Schema for a song"""
    id: str
    title: str
    artist: str
    album: str
    duration: Optional[int] = None
    track_number: Optional[int] = None

class PlaylistResponse(BaseModel):
    """Response schema for playlist operations"""
    playlist: Playlist
    message: str

class RediscoverTrack(BaseModel):
    """Schema for a Re-Discover Weekly track"""
    id: str
    title: str
    artist: str
    album: str
    score: float
    historical_plays: int
    days_since_last_play: str

class RediscoverWeeklyResponse(BaseModel):
    """Response schema for Re-Discover Weekly"""
    tracks: List[RediscoverTrack]
    total_tracks: int
    message: str

class RediscoverWeeklyV2Response(BaseModel):
    """Response schema for Re-Discover Weekly v2.0"""
    name: str
    tracks: List[Dict[str, Any]]
    theme: str
    mode: str
    reasoning: str
    user_id: str
    server_id: str
    generated_at: str
    is_fallback: Optional[bool] = False

class CreateRediscoverPlaylistRequest(BaseModel):
    """Request schema for creating a Re-Discover Weekly playlist"""
    refresh_frequency: str = "weekly"  # "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks

class ScheduledPlaylist(BaseModel):
    """Schema for a scheduled playlist"""
    id: int
    playlist_type: str  # "rediscover_weekly"
    navidrome_playlist_id: str
    refresh_frequency: str
    next_refresh: str
    created_at: str
    updated_at: str

class PlaylistWithScheduleInfo(BaseModel):
    """Schema for playlist with schedule information"""
    id: int
    artist_id: str
    playlist_name: str
    songs: List[str]
    created_at: str
    updated_at: str
    navidrome_playlist_id: Optional[str] = None
    refresh_frequency: Optional[str] = None
    next_refresh: Optional[str] = None
    playlist_type: Optional[str] = None

class UpdatePlaylistSettingsRequest(BaseModel):
    """Request schema for updating playlist refresh settings"""
    refresh_frequency: str  # "none", "daily", "weekly", "monthly"
    playlist_length: Optional[int] = None  # Number of tracks; None = no change
    discovery_ratio: Optional[float] = None  # 0.0–0.75; None = no change

class CreateMultiArtistRadioRequest(BaseModel):
    """Request schema for creating a Multi-Artist Radio Blend playlist"""
    artist_ids: List[str]
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 30
    library_ids: List[str] = []

class CreateMultiGenreMixRequest(BaseModel):
    """Request schema for creating a Multi-Genre Mix playlist"""
    genres: List[str]
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 30
    library_ids: List[str] = []
    discovery_ratio: float = 0.25  # 0.0 = all familiar, 0.75 = max discovery

class CreateDecadeDiscoveryRequest(BaseModel):
    """Request schema for creating a Decade & Discovery playlist"""
    decades: List[str]
    mode: str = "Blend"
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 30
    library_ids: List[str] = []
    discovery_ratio: float = 0.25  # 0.0 = all familiar, 0.75 = max discovery

class CreateSonicJourneyRequest(BaseModel):
    """Request schema for creating a Sonic Journey playlist"""
    start_artist_id: str
    end_artist_id: str
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 30
    library_ids: List[str] = []
    discovery_ratio: float = 0.20  # 0.0 = all familiar, 0.75 = max discovery

class CreateGenreArchaeologyRequest(BaseModel):
    """Request schema for creating a Genre Archaeology playlist"""
    genre: str
    dig_depth: str = "Medium"
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 30
    library_ids: List[str] = []
    discovery_ratio: float = 0.30  # 0.0 = all familiar, 0.75 = max discovery