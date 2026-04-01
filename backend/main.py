from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse
from fastapi import Query
import uvicorn
import os
import logging
import logging.handlers
from typing import List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# Load environment variables first
load_dotenv()

# Get log level from environment (ERROR=minimal, INFO=normal, DEBUG=verbose)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging for scheduler activities with rotation
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'scheduler.log',
            maxBytes=5*1024*1024,  # 5MB per file
            backupCount=2,         # Keep 2 old files (total ~10MB)
            encoding='utf-8'
        ),
        logging.StreamHandler()  # Also log to console
    ]
)

# Create a specific logger for scheduler activities
scheduler_logger = logging.getLogger('scheduler')

# Reduce httpx logging verbosity to avoid cluttering scheduler.log
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

from .navidrome_client import NavidromeClient
from .ai_client import AIClient, _distribute_by_artist
from .database import DatabaseManager, get_db
from .schemas import CreatePlaylistRequest, CreateGenrePlaylistRequest, Playlist, RediscoverWeeklyResponse, RediscoverWeeklyV2Response, CreateRediscoverPlaylistRequest, PlaylistWithScheduleInfo, UpdatePlaylistSettingsRequest, CreateMultiArtistRadioRequest, CreateMultiGenreMixRequest, CreateDecadeDiscoveryRequest, CreateSonicJourneyRequest, CreateGenreArchaeologyRequest
from .recipe_manager import recipe_manager
from .rediscover import RediscoverWeekly, ReDiscoverV2Processor
from .track_scoring import filter_tracks_for_this_is_playlist
# SYSTEM CHECK FEATURE - START
from .services.health_check_service import HealthCheckService
# SYSTEM CHECK FEATURE - END

app = FastAPI(title="MagicLists Navidrome MVP")

@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup"""
    global scheduler, system_check_passed, system_check_results
    scheduler = AsyncIOScheduler()
    scheduler.start()
    scheduler_logger.info("✅ Scheduler started successfully")
    # Auto-start the cron job
    await start_scheduler_job()
    scheduler_logger.info("✅ Cron job auto-started on application startup")
    
    # SYSTEM CHECK FEATURE - START
    # Run system checks on startup
    try:
        health_service = HealthCheckService()
        system_check_results = await health_service.run_checks()
        system_check_passed = system_check_results.get("all_passed", False)
        
        if system_check_passed:
            scheduler_logger.info("✅ System health checks passed on startup")
        else:
            scheduler_logger.warning("⚠️ System health checks failed on startup - user will be redirected to system check page")
            
        # Log individual check results with enhanced AI provider logging
        for check in system_check_results.get("checks", []):
            status_emoji = "✅" if check["status"] == "success" else "⚠️" if check["status"] == "warning" else "ℹ️" if check["status"] == "info" else "❌"
            
            # Enhanced logging for AI Provider checks
            if "AI Provider" in check["name"]:
                ai_provider = os.getenv("AI_PROVIDER", "openrouter")
                if check["status"] == "success":
                    # Extract model from success message (e.g., "service reachable (model: llama3.2)")
                    if "model:" in check["message"]:
                        model_part = check["message"].split("model: ")[1].rstrip(")")
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} with model '{model_part}' - Ready")
                    else:
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} - Ready")
                elif check["status"] == "warning":
                    if "not set" in check["message"]:
                        scheduler_logger.info(f"🤖 AI Provider: {ai_provider.title()} - No API key (using fallback algorithms)")
                    else:
                        scheduler_logger.warning(f"🤖 AI Provider: {ai_provider.title()} - {check['message']}")
                elif check["status"] == "error":
                    scheduler_logger.error(f"🤖 AI Provider: {ai_provider.title()} - {check['message']}")
            else:
                # Standard logging for other checks
                scheduler_logger.info(f"{status_emoji} {check['name']}: {check['status']}")
            
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to run system checks on startup: {e}")
        system_check_passed = False
        system_check_results = {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error", 
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
    # SYSTEM CHECK FEATURE - END

@app.on_event("shutdown") 
async def shutdown_event():
    """Cleanup scheduler on app shutdown"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler_logger.info("🛑 Scheduler shutdown completed")

# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")

# Initialize clients (lazy loading)
navidrome_client = None
ai_client = None

# Initialize scheduler (will be started on app startup)
scheduler = None

# SYSTEM CHECK FEATURE - START
# App state to track system check results
system_check_passed = False
system_check_results = None
# SYSTEM CHECK FEATURE - END

def get_navidrome_client():
    global navidrome_client
    if navidrome_client is None:
        navidrome_client = NavidromeClient()
    return navidrome_client

def get_ai_client():
    global ai_client
    if ai_client is None:
        ai_client = AIClient()
    return ai_client

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main HTML page"""
    # SYSTEM CHECK FEATURE - START
    # Redirect to system check if checks haven't passed
    if not system_check_passed:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/system-check", status_code=302)
    # SYSTEM CHECK FEATURE - END
    
    return templates.TemplateResponse(request, "index.html")

# SYSTEM CHECK FEATURE - START
@app.get("/system-check", response_class=HTMLResponse)
async def system_check_page(request: Request):
    """Serve the system check page"""
    return templates.TemplateResponse(request, "index.html")
# SYSTEM CHECK FEATURE - END

@app.get("/api/artists")
async def get_artists(library_id: List[str] = Query(None)):
    """Get list of artists from Navidrome"""
    try:
        client = get_navidrome_client()
        artists = await client.get_artists(library_id)
        return artists
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch artists: {error_msg}")

@app.get("/api/genres")
async def get_genres(library_id: List[str] = Query(None)):
    """Get list of genres from Navidrome"""
    try:
        client = get_navidrome_client()
        genres = await client.get_genres(library_id)
        return genres
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch genres: {error_msg}")

@app.get("/api/music-folders")
async def get_music_folders():
    """Get list of music folders/libraries from Navidrome"""
    try:
        client = get_navidrome_client()
        folders = await client.get_music_folders()
        return folders
    except Exception as e:
        error_msg = str(e)
        # Check if it's an authentication error and return appropriate status code
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch music folders: {error_msg}")


# SYSTEM CHECK FEATURE - START
@app.get("/api/health-check")
async def get_health_check():
    """Get system health check results"""
    global system_check_passed, system_check_results
    
    try:
        # Run fresh health checks
        health_service = HealthCheckService()
        fresh_results = await health_service.run_checks()
        
        # Update app state with fresh results
        system_check_passed = fresh_results.get("all_passed", False)
        system_check_results = fresh_results
        
        # Log the result
        if system_check_passed:
            scheduler_logger.info("✅ System health checks passed via API")
        else:
            scheduler_logger.warning("⚠️ System health checks failed via API")
        
        return fresh_results
        
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to run health checks via API: {e}")
        error_results = {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error",
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
        return error_results
# SYSTEM CHECK FEATURE - END


@app.post("/api/create_playlist", response_model=Playlist)
async def create_playlist(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'This Is' playlist for a single artist"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Get artist info
        all_artists = await nav_client.get_artists()
        selected_artists = [a for a in all_artists if a["id"] in request.artist_ids]
        
        if not selected_artists:
            raise HTTPException(status_code=404, detail="Artists not found")
        
        # Limit to single artist only - use first artist from the request
        if request.artist_ids:
            first_artist_id = request.artist_ids[0]
            selected_artists = [a for a in all_artists if a["id"] == first_artist_id]
            artist_names = [a["name"] for a in selected_artists]
        else:
            raise HTTPException(status_code=400, detail="At least one artist must be selected")

        # Generate playlist name if not provided - for single artist
        playlist_name = request.playlist_name or f"This Is: {artist_names[0]}"
        
        # Get tracks for only the first artist
        all_tracks = []
        tracks = await nav_client.get_tracks_by_artist(first_artist_id, request.library_ids)
        if tracks:
            all_tracks.extend(tracks)
        
        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found for the selected artists")
        
        # NEW: Apply smart filtering for "This Is" playlists to optimize LLM payload
        library_stats = await nav_client.get_library_stats()
        
        filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
            source_tracks=all_tracks,
            target_playlist_size=request.playlist_length,
            library_stats=library_stats
        )
        
        # Log filtering results for analytics/debugging
        if filter_metadata['filtered']:
            scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks (multiplier: {filter_metadata['threshold_multiplier']}x)")
            scheduler_logger.info(f"📊 Score range: {filter_metadata['score_range']['highest']:.1f} - {filter_metadata['score_range']['lowest']:.1f} (cutoff: {filter_metadata['score_range']['cutoff']:.1f})")
        else:
            scheduler_logger.info(f"✅ No filtering needed: {filter_metadata['source_count']} tracks below threshold")
        
        # Use filtered tracks for LLM processing
        tracks_for_llm = filtered_tracks
        
        # Use AI to curate the playlist (always include reasoning for new recipe format)
        curation_result = await ai_client_instance.curate_this_is(
            artist_name=', '.join(artist_names),
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        
        # Handle both old and new return formats
        if isinstance(curation_result, tuple):
            curated_track_ids, reasoning = curation_result
        else:
            curated_track_ids = curation_result
            reasoning = ""

        # Check for validation failures or empty results
        if not curated_track_ids:
            if reasoning and "Playlist generation failed" in reasoning:
                # This is a validation failure - don't create playlist
                scheduler_logger.error(f"❌ Playlist creation aborted: {reasoning}")
                raise HTTPException(status_code=400, detail=f"Playlist generation failed: {reasoning}")
            else:
                # This is an empty result without explanation
                scheduler_logger.error(f"❌ AI curation returned no tracks for {', '.join(artist_names)}")
                raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        # Log the AI reasoning for debugging (truncated)
        if reasoning:
            reasoning_preview = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            scheduler_logger.info(f"🎵 AI curation applied for {', '.join(artist_names)} (reasoning length: {len(reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ No AI reasoning provided for {', '.join(artist_names)}")

        # Create playlist in Navidrome with AI reasoning as comment
        comment_to_use = reasoning if reasoning else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=comment_to_use
        )
        
        # Get track titles for database storage - PRESERVE AI CURATION ORDER
        # Note: Use all_tracks for mapping since AI might reference tracks from full set
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:  # Iterate in AI-curated order
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])
        
        
        # Store playlist in local database (using the first artist_id for now)
        playlist = await db.create_playlist(
            artist_id=request.artist_ids[0],
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )
        
        # Handle scheduling if not "none" or "never"
        if request.refresh_frequency not in ["none", "never"]:
            next_refresh = calculate_next_refresh(request.refresh_frequency)
            
            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="this_is",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )
            
            # Schedule the refresh job
            schedule_playlist_refresh()
            scheduler_logger.info(f"📅 Scheduled {request.refresh_frequency} refresh for This Is playlist: {playlist_name}")
        
        # Add Navidrome playlist ID to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["refresh_frequency"] = request.refresh_frequency
        
        if request.refresh_frequency != "none":
            playlist_dict["next_refresh"] = calculate_next_refresh(request.refresh_frequency).isoformat()
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist: {str(e)}")

@app.post("/api/create_playlist_with_reasoning")
async def create_playlist_with_reasoning(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'This Is' playlist with AI reasoning explanation"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Get artist info - use first artist from the array
        artists = await nav_client.get_artists()
        if not request.artist_ids or len(request.artist_ids) == 0:
            raise HTTPException(status_code=400, detail="At least one artist must be selected")
        first_artist_id = request.artist_ids[0]
        artist = next((a for a in artists if a["id"] == first_artist_id), None)
        
        if not artist:
            raise HTTPException(status_code=404, detail="Artist not found")
        
        artist_name = artist["name"]
        
        # Generate playlist name if not provided
        playlist_name = getattr(request, 'playlist_name', None) or f"This Is: {artist_name}"
        
        # Get tracks for the artist
        tracks = await nav_client.get_tracks_by_artist(first_artist_id)
        
        if not tracks:
            raise HTTPException(status_code=404, detail="No tracks found for this artist")
        
        # Use AI to curate the playlist WITH reasoning
        curated_track_ids, reasoning = await ai_client_instance.curate_this_is(
            artist_name=artist_name,
            tracks_json=tracks,
            num_tracks=20,
            include_reasoning=True
        )

        # Create playlist in Navidrome with AI reasoning as comment
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=reasoning if reasoning else None
        )
        
        # Get track titles for database storage
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in tracks}
        for track_id in curated_track_ids:
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])
        
        # Store playlist in local database
        playlist = await db.create_playlist(
            artist_id=first_artist_id,
            playlist_name=playlist_name,
            songs=track_titles,
            navidrome_playlist_id=navidrome_playlist_id
        )
        
        # Add Navidrome playlist ID and AI reasoning to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["ai_reasoning"] = reasoning
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist with reasoning: {str(e)}")

@app.post("/api/create_genre_playlist", response_model=Playlist)
async def create_genre_playlist(
    request: CreateGenrePlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated 'Genre Mix' playlist for a specific genre"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        # Generate playlist name if not provided
        playlist_name = request.playlist_name or f"Genre Mix: {request.genre}"

        # Get tracks for the genre
        all_tracks = await nav_client.get_tracks_by_genre(request.genre, request.library_ids)
        scheduler_logger.info(f"🎵 Found {len(all_tracks)} total tracks for genre '{request.genre}'")

        if not all_tracks:
            raise HTTPException(status_code=404, detail=f"No tracks found for genre: {request.genre}")

        # NEW: Apply smart filtering for "Genre Mix" playlists to optimize LLM payload
        library_stats = await nav_client.get_library_stats()

        filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
            source_tracks=all_tracks,
            target_playlist_size=request.playlist_length,
            library_stats=library_stats
        )

        # Log filtering results for analytics/debugging
        if filter_metadata['filtered']:
            scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks (multiplier: {filter_metadata['threshold_multiplier']}x)")
            scheduler_logger.info(f"📊 Score range: {filter_metadata['score_range']['highest']:.1f} - {filter_metadata['score_range']['lowest']:.1f} (cutoff: {filter_metadata['score_range']['cutoff']:.1f})")
        else:
            scheduler_logger.info(f"✅ No filtering needed: {filter_metadata['source_count']} tracks below threshold")

        # Use filtered tracks for LLM processing
        tracks_for_llm = filtered_tracks

        # Use AI to curate the playlist (always include reasoning for new recipe format)
        curation_result = await ai_client_instance.curate_genre_mix(
            genre=request.genre,
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )

        # Handle both old and new return formats
        if isinstance(curation_result, tuple):
            curated_track_ids, reasoning = curation_result
        else:
            curated_track_ids = curation_result
            reasoning = ""

        # Check for validation failures or empty results
        if not curated_track_ids:
            if reasoning and "Playlist generation failed" in reasoning:
                # This is a validation failure - don't create playlist
                scheduler_logger.error(f"❌ Playlist creation aborted: {reasoning}")
                raise HTTPException(status_code=400, detail=f"Playlist generation failed: {reasoning}")
            else:
                # This is an empty result without explanation
                scheduler_logger.error(f"❌ AI curation returned no tracks for {request.genre}")
                raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        # Log the AI reasoning for debugging (truncated)
        if reasoning:
            reasoning_preview = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            scheduler_logger.info(f"🎵 AI curation applied for {request.genre} (reasoning length: {len(reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ No AI reasoning provided for {request.genre}")

        # Create playlist in Navidrome with AI reasoning as comment
        comment_to_use = reasoning if reasoning else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=curated_track_ids,
            comment=comment_to_use
        )

        # Get track titles for database storage
        track_titles = []
        track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
        for track_id in curated_track_ids:  # Iterate in AI-curated order
            if track_id in track_id_to_title:
                track_titles.append(track_id_to_title[track_id])


        # Store playlist in local database (using genre as identifier)
        playlist = await db.create_playlist(
            artist_id=request.genre,  # Using genre as artist_id for now
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        # Handle scheduling if not "none" or "never"
        if request.refresh_frequency not in ["none", "never"]:
            next_refresh = calculate_next_refresh(request.refresh_frequency)

            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="genre_mix",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create genre playlist: {str(e)}")


@app.post("/api/create-multi-artist-radio", response_model=Playlist)
async def create_multi_artist_radio(
    request: CreateMultiArtistRadioRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated Multi-Artist Radio Blend playlist"""
    try:
        import json as _json
        if len(request.artist_ids) < 2 or len(request.artist_ids) > 6:
            raise HTTPException(status_code=400, detail="Please select 2-6 artists")

        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        all_artists = await nav_client.get_artists(request.library_ids)
        selected_artists = [a for a in all_artists if a["id"] in request.artist_ids]
        if not selected_artists:
            raise HTTPException(status_code=404, detail="Artists not found")

        artist_names = [next((a["name"] for a in selected_artists if a["id"] == aid), aid) for aid in request.artist_ids]

        all_tracks = []
        seen_ids = set()
        for artist_id in request.artist_ids:
            tracks = await nav_client.get_tracks_by_artist(artist_id, request.library_ids)
            for t in tracks:
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    all_tracks.append(t)

        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found for selected artists")

        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(all_tracks, request.playlist_length, library_stats)

        curation_result = await ai_client_instance.curate_multi_artist_radio(
            artist_names=artist_names,
            tracks_json=filtered_tracks,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if not curated_track_ids:
            raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        playlist_name = request.playlist_name or f"Radio: {' & '.join(artist_names)}"
        navidrome_playlist_id = await nav_client.create_playlist(name=playlist_name, track_ids=curated_track_ids, comment=reasoning or None)

        track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
        track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

        artist_id_value = _json.dumps({"artist_ids": request.artist_ids, "artist_names": artist_names})
        playlist = await db.create_playlist(
            artist_id=artist_id_value,
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if request.refresh_frequency not in ["none", "never"]:
            await db.create_scheduled_playlist(
                playlist_type="multi_artist_radio",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create multi-artist radio: {str(e)}")


@app.post("/api/create-multi-genre-mix", response_model=Playlist)
async def create_multi_genre_mix(
    request: CreateMultiGenreMixRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated Multi-Genre Mix playlist"""
    try:
        import json as _json
        if len(request.genres) < 2 or len(request.genres) > 5:
            raise HTTPException(status_code=400, detail="Please select 2-5 genres")

        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        all_tracks = await nav_client.get_tracks_for_multiple_genres(request.genres, request.library_ids)
        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found for selected genres")

        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(all_tracks, request.playlist_length, library_stats)

        curation_result = await ai_client_instance.curate_multi_genre_mix(
            genre_names=request.genres,
            tracks_json=filtered_tracks,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if not curated_track_ids:
            raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        playlist_name = request.playlist_name or f"Genre Mix: {' & '.join(request.genres)}"
        navidrome_playlist_id = await nav_client.create_playlist(name=playlist_name, track_ids=curated_track_ids, comment=reasoning or None)

        track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
        track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

        artist_id_value = _json.dumps({"genres": request.genres})
        playlist = await db.create_playlist(
            artist_id=artist_id_value,
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if request.refresh_frequency not in ["none", "never"]:
            await db.create_scheduled_playlist(
                playlist_type="multi_genre_mix",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create multi-genre mix: {str(e)}")


DECADE_YEAR_MAP = {
    "60s": (1960, 1969),
    "70s": (1970, 1979),
    "80s": (1980, 1989),
    "90s": (1990, 1999),
    "00s": (2000, 2009),
    "10s": (2010, 2019),
    "20s": (2020, 2029),
}


@app.post("/api/create-decade-discovery", response_model=Playlist)
async def create_decade_discovery(
    request: CreateDecadeDiscoveryRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated Decade & Discovery playlist"""
    try:
        import json as _json
        unknown_decades = [d for d in request.decades if d not in DECADE_YEAR_MAP]
        if unknown_decades:
            raise HTTPException(status_code=400, detail=f"Unknown decades: {unknown_decades}")
        if request.mode not in ["Anthems", "Discovery", "Blend"]:
            raise HTTPException(status_code=400, detail="Mode must be Anthems, Discovery, or Blend")
        if not request.decades:
            raise HTTPException(status_code=400, detail="Please select at least one decade")

        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        year_start = min(DECADE_YEAR_MAP[d][0] for d in request.decades)
        year_end = max(DECADE_YEAR_MAP[d][1] for d in request.decades)

        all_tracks = await nav_client.get_tracks_by_year_range(year_start, year_end, request.library_ids)
        if not all_tracks:
            raise HTTPException(status_code=404, detail=f"No tracks found for selected decade(s)")

        if request.mode == "Discovery":
            tracks_for_llm = all_tracks
        else:
            library_stats = await nav_client.get_library_stats()
            tracks_for_llm, _ = filter_tracks_for_this_is_playlist(all_tracks, request.playlist_length, library_stats)

        curation_result = await ai_client_instance.curate_decade_discovery(
            decades=request.decades,
            mode=request.mode,
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if not curated_track_ids:
            raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        decade_label = " & ".join(request.decades)
        playlist_name = request.playlist_name or f"Decade: {decade_label} ({request.mode})"
        navidrome_playlist_id = await nav_client.create_playlist(name=playlist_name, track_ids=curated_track_ids, comment=reasoning or None)

        track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
        track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

        artist_id_value = _json.dumps({"decades": request.decades, "mode": request.mode})
        playlist = await db.create_playlist(
            artist_id=artist_id_value,
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if request.refresh_frequency not in ["none", "never"]:
            await db.create_scheduled_playlist(
                playlist_type="decade_discovery",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create decade discovery: {str(e)}")


@app.post("/api/create-sonic-journey", response_model=Playlist)
async def create_sonic_journey(
    request: CreateSonicJourneyRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated Sonic Journey playlist"""
    try:
        import json as _json
        if request.start_artist_id == request.end_artist_id:
            raise HTTPException(status_code=400, detail="Start and end artists must be different")

        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        all_artists = await nav_client.get_artists(request.library_ids)
        start_artist = next((a for a in all_artists if a["id"] == request.start_artist_id), None)
        end_artist = next((a for a in all_artists if a["id"] == request.end_artist_id), None)
        if not start_artist or not end_artist:
            raise HTTPException(status_code=404, detail="One or both artists not found")

        start_artist_name = start_artist["name"]
        end_artist_name = end_artist["name"]

        all_tracks = await nav_client.get_all_tracks(request.library_ids, max_tracks=3000)
        if not all_tracks:
            raise HTTPException(status_code=404, detail="No tracks found in library")

        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(all_tracks, request.playlist_length * 4, library_stats)

        curation_result = await ai_client_instance.curate_sonic_journey(
            start_artist=start_artist_name,
            end_artist=end_artist_name,
            tracks_json=filtered_tracks,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if not curated_track_ids:
            raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        playlist_name = request.playlist_name or f"Journey: {start_artist_name} → {end_artist_name}"
        navidrome_playlist_id = await nav_client.create_playlist(name=playlist_name, track_ids=curated_track_ids, comment=reasoning or None)

        track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
        track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

        artist_id_value = _json.dumps({
            "start_artist_id": request.start_artist_id,
            "start_artist_name": start_artist_name,
            "end_artist_id": request.end_artist_id,
            "end_artist_name": end_artist_name
        })
        playlist = await db.create_playlist(
            artist_id=artist_id_value,
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if request.refresh_frequency not in ["none", "never"]:
            await db.create_scheduled_playlist(
                playlist_type="sonic_journey",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create sonic journey: {str(e)}")


@app.post("/api/create-genre-archaeology", response_model=Playlist)
async def create_genre_archaeology(
    request: CreateGenreArchaeologyRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create an AI-curated Genre Archaeology playlist"""
    try:
        import json as _json
        if request.dig_depth not in ["Shallow", "Medium", "Deep"]:
            raise HTTPException(status_code=400, detail="dig_depth must be Shallow, Medium, or Deep")

        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        all_tracks = await nav_client.get_tracks_by_genre(request.genre, request.library_ids)
        if not all_tracks:
            raise HTTPException(status_code=404, detail=f"No tracks found for genre: {request.genre}")

        if request.dig_depth == "Deep":
            tracks_for_llm = all_tracks
        else:
            library_stats = await nav_client.get_library_stats()
            tracks_for_llm, _ = filter_tracks_for_this_is_playlist(all_tracks, request.playlist_length, library_stats)

        curation_result = await ai_client_instance.curate_genre_archaeology(
            genre=request.genre,
            dig_depth=request.dig_depth,
            tracks_json=tracks_for_llm,
            num_tracks=request.playlist_length,
            include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if not curated_track_ids:
            raise HTTPException(status_code=500, detail="AI curation failed to return any tracks")

        playlist_name = request.playlist_name or f"Archaeology: {request.genre} ({request.dig_depth})"
        navidrome_playlist_id = await nav_client.create_playlist(name=playlist_name, track_ids=curated_track_ids, comment=reasoning or None)

        track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
        track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

        artist_id_value = _json.dumps({"genre": request.genre, "dig_depth": request.dig_depth})
        playlist = await db.create_playlist(
            artist_id=artist_id_value,
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids
        )

        if request.refresh_frequency not in ["none", "never"]:
            await db.create_scheduled_playlist(
                playlist_type="genre_archaeology",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )

        return playlist

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create genre archaeology: {str(e)}")


@app.get("/api/rediscover-weekly", response_model=RediscoverWeeklyResponse)
async def get_rediscover_weekly():
    """Generate Re-Discover Weekly playlist based on listening history"""
    try:
        # Get Navidrome client
        nav_client = get_navidrome_client()
        
        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)
        
        # Generate the playlist with AI curation
        tracks = await rediscover.generate_rediscover_weekly(use_ai=True)
        
        # Extract AI curation info for response
        ai_curated = tracks[0].get("ai_curated", False) if tracks else False
        message = f"Generated Re-Discover Weekly with {len(tracks)} tracks"
        if ai_curated:
            message += " (AI curated)"
        else:
            message += " (algorithmic selection)"
        
        return RediscoverWeeklyResponse(
            tracks=tracks,
            total_tracks=len(tracks),
            message=message
        )
        
    except Exception as e:
        error_msg = str(e)
        if "No listening history found" in error_msg:
            raise HTTPException(status_code=404, detail="No listening history found. Make sure you've played some music in Navidrome.")
        elif "No tracks found for re-discovery" in error_msg:
            raise HTTPException(status_code=404, detail="No tracks found for re-discovery. Try listening to more music first.")
        elif "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate Re-Discover Weekly: {error_msg}")

@app.get("/api/rediscover-weekly-v2", response_model=RediscoverWeeklyV2Response)
async def get_rediscover_weekly_v2(library_ids: Optional[List[str]] = Query(None), db: DatabaseManager = Depends(get_db)):
    """Generate Re-Discover Weekly v2.0 playlist using temporal analysis and two-phase AI"""
    try:
        # Get clients
        nav_client = get_navidrome_client()
        ai_client = get_ai_client()

        # Get user and server IDs
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"  # Use base URL as server identifier

        # Create ReDiscoverV2Processor instance
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Generate the playlist
        result = await processor.generate_playlist(user_id, server_id, library_ids)

        return RediscoverWeeklyV2Response(**result)

    except Exception as e:
        error_msg = str(e)
        if "Insufficient listening history" in error_msg:
            raise HTTPException(status_code=404, detail="Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")
        elif "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate Re-Discover Weekly v2.0: {error_msg}")

@app.post("/api/create-rediscover-playlist-v2")
async def create_rediscover_playlist_v2(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a Re-Discover Weekly v2.0 playlist in Navidrome"""
    try:
        scheduler_logger.info(f"🎵 Starting Re-Discover v2.0 playlist creation with length {request.playlist_length}, library_ids: {request.library_ids}")

        # Get clients
        nav_client = get_navidrome_client()
        ai_client = get_ai_client()

        # Get user and server IDs
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"

        # Create ReDiscoverV2Processor instance
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Generate the playlist
        playlist_data = await processor.generate_playlist(user_id, server_id, request.library_ids)
        tracks = playlist_data.get("tracks", [])

        if not tracks:
            scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly v2.0")
            raise HTTPException(status_code=404, detail="No tracks found for Re-Discover Weekly v2.0")

        scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly v2.0")

        # Extract AI reasoning if available
        ai_reasoning = playlist_data.get("reasoning", "")
        ai_curated = any(track.get("ai_curated", False) for track in tracks)

        # If AI curated, get reasoning from the tracks instead of Phase 1
        if ai_curated:
            track_reasoning = next((track.get("ai_reasoning", "") for track in tracks if track.get("ai_curated", False) and track.get("ai_reasoning")), "")
            if track_reasoning:
                ai_reasoning = track_reasoning

        scheduler_logger.info(f"🎵 AI curated: {ai_curated}, reasoning length: {len(ai_reasoning)}")

        # Log the AI reasoning for debugging (truncated)
        if ai_reasoning and ai_curated:
            reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
            scheduler_logger.info(f"🎵 AI curation applied for Re-Discover Weekly v2.0 (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ Re-Discover Weekly v2.0 used fallback strategy")

        # Create playlist name based on refresh frequency
        frequency_names = {
            "daily": "Re-Discover Daily ✨",
            "weekly": "Re-Discover Weekly ✨",
            "monthly": "Re-Discover Monthly ✨",
            "never": "Re-Discover ✨"
        }
        playlist_name = frequency_names.get(request.refresh_frequency, "Re-Discover Weekly ✨")
        if playlist_data.get("is_fallback"):
            playlist_name += " (Fallback)"
        scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

        # Extract track IDs
        track_ids = [track["id"] for track in tracks]
        scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

        # Create playlist in Navidrome with reasoning as comment
        comment_to_use = ai_reasoning if ai_reasoning else f"Theme: {playlist_data.get('theme', 'Mixed')}"
        comment_preview = comment_to_use[:200] + "..." if len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating Re-Discover v2.0 playlist with comment (length: {len(comment_to_use)}): {comment_preview}")

        scheduler_logger.info("🎵 Calling nav_client.create_playlist...")
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=track_ids,
            comment=comment_to_use
        )
        scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")

        # Get track titles for database storage
        track_titles = [track.get("title", "Unknown") for track in tracks]
        scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

        # Store playlist in local database (using a synthetic artist_id for rediscover playlists)
        playlist_record = await db.create_playlist(
            artist_id="rediscover_v2",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=ai_reasoning,
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=len(tracks),
            library_ids=request.library_ids
        )
        scheduler_logger.info(f"💾 Database playlist created: {playlist_record}")

        # Set up scheduling if requested
        if request.refresh_frequency != "never":
            scheduler_logger.info(f"⏰ Setting up {request.refresh_frequency} refresh schedule")
            scheduled_playlist = await db.create_scheduled_playlist(
                playlist_type="rediscover_weekly_v2",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=calculate_next_refresh(request.refresh_frequency)
            )
            scheduler_logger.info(f"✅ Scheduled playlist created: {scheduled_playlist}")
        else:
            scheduler_logger.info("⏰ No scheduling requested (refresh_frequency='never')")

        return {
            "message": f"Re-Discover Weekly v2.0 playlist created successfully with {len(tracks)} tracks",
            "playlist_id": navidrome_playlist_id,
            "track_count": len(tracks),
            "theme": playlist_data.get("theme", "Mixed"),
            "mode": playlist_data.get("mode", "Unknown"),
            "is_fallback": playlist_data.get("is_fallback", False)
        }

    except HTTPException:
        raise
    except Exception as e:
        scheduler_logger.error(f"❌ Failed to create Re-Discover Weekly v2.0 playlist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Re-Discover Weekly v2.0 playlist: {str(e)}")

@app.post("/api/create-rediscover-playlist")
async def create_rediscover_playlist(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Create a Re-Discover Weekly playlist in Navidrome"""
    try:
        scheduler_logger.info(f"🎵 Starting Re-Discover playlist creation with length {request.playlist_length}, library_ids: {request.library_ids}")

        # Get Navidrome client
        nav_client = get_navidrome_client()

        # Create RediscoverWeekly instance
        rediscover = RediscoverWeekly(nav_client)

        # Generate the playlist tracks with user-specified length and AI curation
        scheduler_logger.info("🎵 Generating rediscover tracks...")
        tracks = await rediscover.generate_rediscover_weekly(max_tracks=request.playlist_length, use_ai=True, library_id=request.library_ids[0] if request.library_ids else "", variety_context="")
        scheduler_logger.info(f"🎵 Generated {len(tracks) if tracks else 0} tracks")
        
        if not tracks:
            scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly")
            raise HTTPException(status_code=404, detail="No tracks found for Re-Discover Weekly")

        scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly")

        # Extract AI reasoning if available
        ai_reasoning = ""
        ai_curated = False
        if tracks:
            first_track = tracks[0]
            ai_reasoning = first_track.get("ai_reasoning", "")
            ai_curated = first_track.get("ai_curated", False)
            scheduler_logger.info(f"🎵 AI curated: {ai_curated}, reasoning length: {len(ai_reasoning)}")
        
        # Log the AI reasoning for debugging (truncated)
        if ai_reasoning and ai_curated:
            reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
            scheduler_logger.info(f"🎵 AI curation applied for Re-Discover Weekly (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
        else:
            scheduler_logger.info(f"⚠️ Re-Discover Weekly used algorithmic selection (no AI reasoning)")
        
        # Create playlist name based on frequency
        frequency_names = {
            "daily": "Re-Discover Daily ✨",
            "weekly": "Re-Discover Weekly ✨",
            "monthly": "Re-Discover Monthly ✨",
            "never": "Re-Discover ✨"
        }
        playlist_name = frequency_names.get(request.refresh_frequency, "Re-Discover Weekly ✨")
        scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

        # Extract track IDs
        track_ids = [track["id"] for track in tracks]
        scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

        # Create playlist in Navidrome with AI reasoning as comment if available
        comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else None
        comment_preview = comment_to_use[:200] + "..." if comment_to_use and len(comment_to_use) > 200 else comment_to_use
        scheduler_logger.info(f"💬 Creating Re-Discover playlist with comment (length: {len(comment_to_use) if comment_to_use else 0}): {comment_preview}")

        scheduler_logger.info("🎵 Calling nav_client.create_playlist...")
        navidrome_playlist_id = await nav_client.create_playlist(
            name=playlist_name,
            track_ids=track_ids,
            comment=comment_to_use
        )
        scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")
        
        # Get track titles for database storage
        track_titles = [track["title"] for track in tracks]
        scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

        # Store playlist in local database (using a synthetic artist_id for rediscover playlists)
        scheduler_logger.info("💾 Creating playlist in database...")
        playlist = await db.create_playlist(
            artist_id="rediscover",
            playlist_name=playlist_name,
            songs=track_titles,
            reasoning=ai_reasoning if ai_curated else "Algorithmic selection",
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_length=request.playlist_length
        )
        scheduler_logger.info(f"✅ Database playlist created: {playlist}")
        
        # Handle scheduling if not "never"
        if request.refresh_frequency != "never":
            next_refresh = calculate_next_refresh(request.refresh_frequency)
            
            # Store the scheduled playlist
            await db.create_scheduled_playlist(
                playlist_type="rediscover",
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency,
                next_refresh=next_refresh
            )
            
            # Schedule the refresh job
            schedule_playlist_refresh()
            scheduler_logger.info(f"📅 Scheduled {request.refresh_frequency} refresh for playlist: {playlist_name}")
        else:
            scheduler_logger.info(f"📅 No scheduling for playlist: {playlist_name} (refresh frequency: never)")
        
        # Add Navidrome playlist ID to response
        playlist_dict = playlist.dict() if hasattr(playlist, 'dict') else playlist.__dict__
        playlist_dict["navidrome_playlist_id"] = navidrome_playlist_id
        playlist_dict["tracks"] = tracks
        playlist_dict["refresh_frequency"] = request.refresh_frequency
        playlist_dict["next_refresh"] = calculate_next_refresh(request.refresh_frequency).isoformat()
        
        return playlist_dict
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Re-Discover Weekly playlist: {str(e)}")

def calculate_next_refresh(frequency: str) -> datetime:
    """Calculate the next refresh time based on frequency"""
    now = datetime.now()
    if frequency == "daily":
        # Next day at 1:00 AM
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "weekly":
        # Next Monday at 1:00 AM
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= 1:
            days_until_monday = 7  # If it's Monday after 1 AM, go to next Monday
        next_monday = now + timedelta(days=days_until_monday)
        return next_monday.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "monthly":
        # 1st of next month at 1:00 AM
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=1, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=1, minute=0, second=0, microsecond=0)
        return next_month
    else:
        return now  # Fallback


def _is_transient_fallback(reasoning: str) -> bool:
    """Return True when AI curation fell back due to a transient error (not a missing API key)."""
    return (
        reasoning.startswith("Fallback curation:")
        and "No AI API key configured" not in reasoning
    )


def schedule_playlist_refresh():
    """Schedule the playlist refresh job to run every 12 hours"""
    if not scheduler.get_job('playlist_refresh'):
        scheduler.add_job(
            refresh_scheduled_playlists,
            'cron',
            hour='1,13',  # Run at 1 AM and 1 PM
            minute=1,     # Run at 1 minute past (1:01 AM and 1:01 PM)
            id='playlist_refresh',
            replace_existing=True
        )
        scheduler_logger.info("🔄 Playlist refresh job scheduled to run every 12 hours (1:01 AM and 1:01 PM)")

async def refresh_scheduled_playlists():
    """Check for and refresh scheduled playlists that are due"""
    try:
        current_time = datetime.now()

        if LOG_LEVEL == "DEBUG":
            scheduler_logger.debug(f"🔄 Scheduler auto-run initiated at {current_time.strftime('%H:%M:%S')}")

        scheduler_logger.info("🔍 Checking for playlists due for refresh...")

        # Get database path from environment variable with smart defaults
        default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
        db_path = os.getenv("DATABASE_PATH", default_path)
        db = DatabaseManager(db_path)
        current_time = datetime.now()

        # Get playlists due for refresh (including 7-day catch-up window)
        scheduled_playlists = await db.get_scheduled_playlists_due(current_time, grace_hours=168)

        if not scheduled_playlists:
            if LOG_LEVEL == "DEBUG":
                scheduler_logger.debug("✅ No playlists due for refresh at this time")
            else:
                scheduler_logger.info("✅ No playlists due for refresh at this time")
            return

        # Group by navidrome_playlist_id to prevent duplicate processing.
        # Keep the most recent (highest id) record per playlist – this is the
        # canonical row whose next_refresh will be updated after the refresh.
        unique_playlists: dict = {}
        for playlist in scheduled_playlists:
            pid = playlist.navidrome_playlist_id
            if pid not in unique_playlists or playlist.id > unique_playlists[pid].id:
                unique_playlists[pid] = playlist

        final_playlists = list(unique_playlists.values())

        scheduler_logger.info(f"📋 Found {len(final_playlists)} playlist(s) due for refresh (deduplicated from {len(scheduled_playlists)} total)")

        for scheduled_playlist in final_playlists:
            # Clean up any stale duplicate rows before refreshing
            await db.delete_duplicate_scheduled_playlists(scheduled_playlist.navidrome_playlist_id)

            # Log catch-up info
            scheduled_time = datetime.fromisoformat(scheduled_playlist.next_refresh)
            if scheduled_time < current_time:
                overdue_hours = (current_time - scheduled_time).total_seconds() / 3600
                scheduler_logger.info(f"🕐 Catching up on overdue playlist {scheduled_playlist.navidrome_playlist_id} (missed by {overdue_hours:.1f} hours)")

            try:
                if scheduled_playlist.playlist_type in ("rediscover", "rediscover_weekly_v2"):
                    await refresh_rediscover_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "this_is":
                    await refresh_this_is_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "genre_mix":
                    await refresh_genre_mix_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "multi_artist_radio":
                    await refresh_multi_artist_radio_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "multi_genre_mix":
                    await refresh_multi_genre_mix_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "decade_discovery":
                    await refresh_decade_discovery_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "sonic_journey":
                    await refresh_sonic_journey_playlist(scheduled_playlist, db)
                elif scheduled_playlist.playlist_type == "genre_archaeology":
                    await refresh_genre_archaeology_playlist(scheduled_playlist, db)
                else:
                    scheduler_logger.warning(f"⚠️ Unknown playlist type '{scheduled_playlist.playlist_type}' for {scheduled_playlist.navidrome_playlist_id} – skipping")
            except Exception as playlist_err:
                scheduler_logger.error(f"❌ Failed to refresh playlist {scheduled_playlist.navidrome_playlist_id}: {playlist_err}")
                # Continue with remaining playlists even if one fails

    except Exception as e:
        scheduler_logger.error(f"❌ Error in refresh_scheduled_playlists: {e}")

async def refresh_rediscover_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific Re-Discover Weekly playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")
        
        # Get clients
        nav_client = get_navidrome_client()
        
        # Get original playlist to find user's preferred length
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return
        
        # Get original playlist length (MUST respect user's choice)
        original_length = original_playlist.get("playlist_length", 20)
        scheduler_logger.info(f"🎯 Using original playlist length: {original_length}")
        
        # Get previous playlist songs for variety context
        previous_songs = original_playlist.get("songs", [])[:10]
        variety_instruction = f"REFRESH CHALLENGE: The current playlist opens with these tracks in this order: {', '.join(previous_songs[:5])}. Your goal is to create a FRESH arrangement that tells a different musical story. You may include some of the same excellent tracks if they're rediscovery-worthy, but avoid replicating the same opening sequence or overall flow. Think creatively about re-ordering, substituting, or finding better transitions to ensure a genuinely refreshed listening experience." if previous_songs else ""
        
        # Get AI client for v2.0 processor
        ai_client = get_ai_client()

        # Get user and server IDs for v2.0 processor
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"

        # Create ReDiscoverV2Processor instance (improved fallback handling)
        processor = ReDiscoverV2Processor(nav_client, ai_client, db)

        # Prepare library IDs for v2.0 processor
        library_ids = [scheduled_playlist.library_id] if hasattr(scheduled_playlist, 'library_id') and scheduled_playlist.library_id else None

        # Log refresh context for debugging
        scheduler_logger.info(f"🔄 Re-Discover v2.0 refresh context - Previous tracks: {len(previous_songs)}, Library IDs: {library_ids}")

        # Generate new tracks using v2.0 processor with improved fallback handling
        result = await processor.generate_playlist(user_id, server_id, library_ids)

        # Extract tracks from v2.0 result format
        tracks = result.get("tracks", [])

        # Ensure tracks have the expected format for the rest of the refresh logic
        # The v2.0 tracks should already have ai_curated and ai_reasoning fields
        
        # The rediscover.generate_rediscover_weekly() method now uses the new recipe system internally
        
        if tracks:
            scheduler_logger.info(f"🎵 Generated {len(tracks)} new tracks for refresh")
            
            # VALIDATE: Ensure we got the expected number of tracks
            if len(tracks) != original_length:
                scheduler_logger.warning(f"⚠️ Generated {len(tracks)} tracks but user requested {original_length}")
            else:
                scheduler_logger.info(f"✅ Generated exact number of requested tracks: {len(tracks)}")
            
            # Extract AI reasoning if available
            ai_reasoning = ""
            ai_curated = False
            if tracks:
                first_track = tracks[0]
                ai_reasoning = first_track.get("ai_reasoning", "")
                ai_curated = first_track.get("ai_curated", False)
            
            # Skip update if AI had a transient error (keep existing playlist, retry in 1 h)
            if _is_transient_fallback(ai_reasoning):
                retry_at = datetime.now() + timedelta(hours=1)
                await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
                scheduler_logger.warning(
                    f"⚠️ AI error on Re-Discover refresh — keeping existing playlist unchanged. "
                    f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return

            # Log the AI reasoning for scheduled refresh (truncated)
            if ai_reasoning and ai_curated:
                reasoning_preview = ai_reasoning[:200] + "..." if len(ai_reasoning) > 200 else ai_reasoning
                scheduler_logger.info(f"🎵 AI curation applied for scheduled Re-Discover refresh (reasoning length: {len(ai_reasoning)} chars): {reasoning_preview}")
            else:
                scheduler_logger.info(f"⚠️ Scheduled Re-Discover refresh used algorithmic selection")
            
            # Update the existing playlist in Navidrome with reasoning
            track_ids = [track["id"] for track in tracks]
            comment_to_use = ai_reasoning if (ai_reasoning and ai_curated) else "Re-Discover Weekly v2.0 - Automatically refreshed"
            await nav_client.update_playlist(
                playlist_id=scheduled_playlist.navidrome_playlist_id,
                track_ids=track_ids,
                comment=comment_to_use
            )
            
            # Update the local database with new songs and reasoning
            track_titles = [track["title"] for track in tracks]
            reasoning_to_store = ai_reasoning if ai_curated else "Algorithmic selection"
            await db.update_playlist_content(
                navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                songs=track_titles,
                reasoning=reasoning_to_store
            )
            
            # Calculate next refresh time
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            
            # Update the scheduled playlist record
            await db.update_scheduled_playlist_next_refresh(
                scheduled_playlist.id, 
                next_refresh
            )
            
            scheduler_logger.info(f"✅ Successfully refreshed playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            scheduler_logger.warning(f"⚠️ No tracks generated for playlist {scheduled_playlist.navidrome_playlist_id}")
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing playlist {scheduled_playlist.navidrome_playlist_id}: {e}")

async def refresh_this_is_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific This Is playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for This Is playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")
        
        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()
        
        # Find the original playlist to get artist info
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return
        
        # Get artist IDs from the original playlist (we'll need to store this better in future)
        # For now, we'll use the artist_id field, but this limits us to single artists for refresh
        artist_id = original_playlist["artist_id"]
        
        # Get all artists to find the name
        all_artists = await nav_client.get_artists()
        artist = next((a for a in all_artists if a["id"] == artist_id), None)
        
        if not artist:
            scheduler_logger.error(f"❌ Could not find artist data for ID: {artist_id}")
            return
        
        artist_name = artist["name"]
        
        # FRESH DATA: Re-fetch ALL tracks for the artist (gets latest play counts, dates)
        tracks = await nav_client.get_tracks_by_artist(artist_id)
        
        if tracks:
            scheduler_logger.info(f"🎵 Found {len(tracks)} tracks for artist: {artist_name} (fresh data)")
            
            # ENFORCE original playlist length (MUST respect user's choice)
            original_length = original_playlist.get("playlist_length", 25)
            scheduler_logger.info(f"🎯 ENFORCING original playlist length: {original_length}")
            
            # Check if we have enough tracks
            if len(tracks) < original_length:
                scheduler_logger.warning(f"⚠️ Artist only has {len(tracks)} tracks, but user requested {original_length}. Using all available tracks.")
                original_length = len(tracks)
            
            # Get previous playlist songs for variety enforcement
            previous_songs = original_playlist.get("songs", [])
            previous_titles = set(previous_songs)

            # Exclude previously used tracks at the data layer when there are
            # enough remaining tracks to still fill the playlist.
            tracks_without_previous = [t for t in tracks if t.get("title", "") not in previous_titles]
            if len(tracks_without_previous) >= original_length:
                tracks_for_ai = tracks_without_previous
                scheduler_logger.info(f"🔄 Excluded {len(tracks) - len(tracks_without_previous)} previously-used tracks; {len(tracks_for_ai)} remaining")
            else:
                tracks_for_ai = tracks.copy()
                scheduler_logger.info(f"🔄 Library too small to fully exclude previous tracks; using full set of {len(tracks_for_ai)}")

            variety_instruction = (
                f"REFRESH: This replaces a previous playlist. Keep the listening experience fresh — "
                f"vary the mood, era mix, and track sequence significantly from last time."
                if previous_songs else "Create a fresh, engaging playlist arrangement."
            )
            
            # Use AI to curate a FRESH playlist with STRONG variety enforcement
            curation_result = await ai_client_instance.curate_this_is(
                artist_name=artist_name,
                tracks_json=tracks_for_ai,
                num_tracks=original_length,
                include_reasoning=True,
                variety_context=variety_instruction
            )
            
            # Handle both old and new return formats
            if isinstance(curation_result, tuple):
                curated_track_ids, reasoning = curation_result
            else:
                curated_track_ids = curation_result
                reasoning = ""

            # Skip update if AI had a transient error (keep existing playlist, retry in 1 h)
            if _is_transient_fallback(reasoning):
                retry_at = datetime.now() + timedelta(hours=1)
                await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
                scheduler_logger.warning(
                    f"⚠️ AI error on This Is refresh — keeping existing playlist unchanged. "
                    f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
                )
                return

            if curated_track_ids:
                # VALIDATE: Ensure we got the right number of tracks
                if len(curated_track_ids) < original_length and len(tracks) >= original_length:
                    scheduler_logger.warning(f"⚠️ AI returned only {len(curated_track_ids)} tracks but user requested {original_length}. Using fallback to fill gap.")
                    # Fill the gap with remaining tracks
                    used_ids = set(curated_track_ids)
                    remaining_tracks = [t for t in tracks if t["id"] not in used_ids]
                    additional_needed = original_length - len(curated_track_ids)
                    additional_tracks = remaining_tracks[:additional_needed]
                    curated_track_ids.extend([t["id"] for t in additional_tracks])
                
                scheduler_logger.info(f"🎯 Final track count: {len(curated_track_ids)} (requested: {original_length})")
                
                # Update the existing playlist in Navidrome with new reasoning
                await nav_client.update_playlist(
                    playlist_id=scheduled_playlist.navidrome_playlist_id,
                    track_ids=curated_track_ids,
                    comment=reasoning if reasoning else None
                )
                
                # Update the local database with new songs and reasoning
                track_titles = []
                track_id_to_title = {track["id"]: track["title"] for track in tracks}
                for track_id in curated_track_ids:
                    if track_id in track_id_to_title:
                        track_titles.append(track_id_to_title[track_id])
                
                await db.update_playlist_content(
                    navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                    songs=track_titles,
                    reasoning=reasoning
                )
                
                # Calculate next refresh time
                next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
                
                # Update the scheduled playlist record
                await db.update_scheduled_playlist_next_refresh(
                    scheduled_playlist.id, 
                    next_refresh
                )
                
                scheduler_logger.info(f"✅ Successfully refreshed This Is playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                scheduler_logger.warning(f"⚠️ No curated tracks generated for This Is playlist {scheduled_playlist.navidrome_playlist_id}")
        else:
            scheduler_logger.warning(f"⚠️ No tracks found for artist {artist_name} in playlist {scheduled_playlist.navidrome_playlist_id}")
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing This Is playlist {scheduled_playlist.navidrome_playlist_id}: {e}")

async def refresh_genre_mix_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a specific Genre Mix playlist"""
    try:
        scheduler_logger.info(f"🔄 Starting refresh for Genre Mix playlist ID: {scheduled_playlist.navidrome_playlist_id} (frequency: {scheduled_playlist.refresh_frequency})")

        # Get clients
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        # Find the original playlist — genre is stored in the artist_id field
        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)

        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return

        genre = original_playlist["artist_id"]  # genre is stored as artist_id for genre_mix playlists

        # FRESH DATA: Re-fetch ALL tracks for the genre
        all_tracks = await nav_client.get_tracks_by_genre(genre)

        if not all_tracks:
            scheduler_logger.warning(f"⚠️ No tracks found for genre '{genre}' in playlist {scheduled_playlist.navidrome_playlist_id}")
            return

        scheduler_logger.info(f"🎵 Found {len(all_tracks)} tracks for genre: {genre} (fresh data)")

        # ENFORCE original playlist length
        original_length = original_playlist.get("playlist_length", 25)
        scheduler_logger.info(f"🎯 ENFORCING original playlist length: {original_length}")

        if len(all_tracks) < original_length:
            scheduler_logger.warning(f"⚠️ Genre only has {len(all_tracks)} tracks, but user requested {original_length}. Using all available tracks.")
            original_length = len(all_tracks)

        # Exclude previously used tracks at the data layer when library is large enough
        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        if len(tracks_without_previous) >= original_length:
            candidate_tracks = tracks_without_previous
            scheduler_logger.info(f"🔄 Excluded {len(all_tracks) - len(tracks_without_previous)} previously-used tracks; {len(candidate_tracks)} remaining")
        else:
            candidate_tracks = all_tracks
            scheduler_logger.info(f"🔄 Library too small to fully exclude previous tracks; using full set of {len(candidate_tracks)}")

        # Apply smart filtering to optimise LLM payload
        library_stats = await nav_client.get_library_stats()
        filtered_tracks, filter_metadata = filter_tracks_for_this_is_playlist(
            source_tracks=candidate_tracks,
            target_playlist_size=original_length,
            library_stats=library_stats
        )
        if filter_metadata['filtered']:
            scheduler_logger.info(f"🎯 Smart filtering applied: {filter_metadata['source_count']} → {filter_metadata['sent_count']} tracks")

        variety_instruction = (
            "REFRESH: Keep the listening experience fresh — vary the mood, era mix, and track sequence significantly from last time."
            if previous_songs else "Create a fresh, engaging playlist arrangement."
        )

        curation_result = await ai_client_instance.curate_genre_mix(
            genre=genre,
            tracks_json=filtered_tracks,
            num_tracks=original_length,
            include_reasoning=True,
            variety_context=variety_instruction
        )

        if isinstance(curation_result, tuple):
            curated_track_ids, reasoning = curation_result
        else:
            curated_track_ids = curation_result
            reasoning = ""

        # Skip update if AI had a transient error (keep existing playlist, retry in 1 h)
        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Genre Mix refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            # Fill any gap if the final list is short
            if len(curated_track_ids) < original_length and len(all_tracks) >= original_length:
                gap = original_length - len(curated_track_ids)
                scheduler_logger.warning(f"⚠️ Got only {len(curated_track_ids)} tracks but user requested {original_length}. Filling gap of {gap}.")
                used_ids = set(curated_track_ids)
                remaining = [t for t in all_tracks if t["id"] not in used_ids]
                # Distribute gap-fill candidates so they are not alphabetically clustered
                gap_id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in remaining}
                gap_pool = [t["id"] for t in remaining[: gap * 4]]  # 4× pool for good diversity
                gap_fill = _distribute_by_artist(gap_pool, gap_id_to_artist, gap)
                # If distribution returned fewer than needed, top up with any remaining tracks
                if len(gap_fill) < gap:
                    used_after_gap = set(gap_fill)
                    gap_fill += [t["id"] for t in remaining if t["id"] not in used_after_gap][: gap - len(gap_fill)]
                curated_track_ids.extend(gap_fill)

            scheduler_logger.info(f"🎯 Final track count: {len(curated_track_ids)} (requested: {original_length})")

            await nav_client.update_playlist(
                playlist_id=scheduled_playlist.navidrome_playlist_id,
                track_ids=curated_track_ids,
                comment=reasoning if reasoning else None
            )

            track_id_to_title = {track["id"]: track["title"] for track in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]

            await db.update_playlist_content(
                navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                songs=track_titles,
                reasoning=reasoning
            )

            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)

            scheduler_logger.info(f"✅ Successfully refreshed Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}. Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            scheduler_logger.warning(f"⚠️ No curated tracks generated for Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing Genre Mix playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_multi_artist_radio_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a Multi-Artist Radio Blend playlist"""
    try:
        import json as _json
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return

        try:
            settings = _json.loads(original_playlist["artist_id"])
            artist_ids = settings.get("artist_ids", [])
            artist_names = settings.get("artist_names", [])
        except Exception:
            scheduler_logger.error(f"❌ Could not parse settings for multi_artist_radio playlist")
            return

        all_tracks = []
        seen_ids = set()
        for artist_id in artist_ids:
            tracks = await nav_client.get_tracks_by_artist(artist_id)
            for t in tracks:
                if t["id"] not in seen_ids:
                    seen_ids.add(t["id"])
                    all_tracks.append(t)

        if not all_tracks:
            scheduler_logger.warning(f"⚠️ No tracks found for multi_artist_radio refresh")
            return

        original_length = original_playlist.get("playlist_length", 30)
        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        candidate_tracks = tracks_without_previous if len(tracks_without_previous) >= original_length else all_tracks
        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(candidate_tracks, original_length, library_stats)
        variety_context = "REFRESH: Keep the selection fresh — vary mood, tempo, and track order significantly." if previous_songs else None

        curation_result = await ai_client_instance.curate_multi_artist_radio(
            artist_names=artist_names, tracks_json=filtered_tracks, num_tracks=original_length,
            include_reasoning=True, variety_context=variety_context
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        # Skip update if AI had a transient error (keep existing playlist, retry in 1 h)
        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Multi-Artist Radio refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            await nav_client.update_playlist(playlist_id=scheduled_playlist.navidrome_playlist_id, track_ids=curated_track_ids, comment=reasoning or None)
            track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]
            await db.update_playlist_content(navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id, songs=track_titles, reasoning=reasoning)
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(f"✅ Refreshed multi_artist_radio playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing multi_artist_radio playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_multi_genre_mix_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a Multi-Genre Mix playlist"""
    try:
        import json as _json
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        if not original_playlist:
            return

        try:
            settings = _json.loads(original_playlist["artist_id"])
            genres = settings.get("genres", [])
        except Exception:
            scheduler_logger.error(f"❌ Could not parse settings for multi_genre_mix playlist")
            return

        all_tracks = await nav_client.get_tracks_for_multiple_genres(genres)
        if not all_tracks:
            return

        original_length = original_playlist.get("playlist_length", 30)
        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        candidate_tracks = tracks_without_previous if len(tracks_without_previous) >= original_length else all_tracks
        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(candidate_tracks, original_length, library_stats)
        variety_context = "REFRESH: Keep the selection fresh — vary mood, tempo, and track order significantly." if previous_songs else None

        curation_result = await ai_client_instance.curate_multi_genre_mix(
            genre_names=genres, tracks_json=filtered_tracks, num_tracks=original_length,
            include_reasoning=True, variety_context=variety_context
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Multi-Genre Mix refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            await nav_client.update_playlist(playlist_id=scheduled_playlist.navidrome_playlist_id, track_ids=curated_track_ids, comment=reasoning or None)
            track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]
            await db.update_playlist_content(navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id, songs=track_titles, reasoning=reasoning)
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(f"✅ Refreshed multi_genre_mix playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing multi_genre_mix playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_decade_discovery_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a Decade & Discovery playlist"""
    try:
        import json as _json
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        if not original_playlist:
            return

        try:
            settings = _json.loads(original_playlist["artist_id"])
            decades = settings.get("decades", [])
            mode = settings.get("mode", "Blend")
        except Exception:
            scheduler_logger.error(f"❌ Could not parse settings for decade_discovery playlist")
            return

        year_start = min(DECADE_YEAR_MAP[d][0] for d in decades if d in DECADE_YEAR_MAP)
        year_end = max(DECADE_YEAR_MAP[d][1] for d in decades if d in DECADE_YEAR_MAP)
        all_tracks = await nav_client.get_tracks_by_year_range(year_start, year_end)
        if not all_tracks:
            return

        original_length = original_playlist.get("playlist_length", 30)
        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        candidate_tracks = tracks_without_previous if len(tracks_without_previous) >= original_length else all_tracks

        if mode == "Discovery":
            tracks_for_llm = candidate_tracks
        else:
            library_stats = await nav_client.get_library_stats()
            tracks_for_llm, _ = filter_tracks_for_this_is_playlist(candidate_tracks, original_length, library_stats)

        curation_result = await ai_client_instance.curate_decade_discovery(
            decades=decades, mode=mode, tracks_json=tracks_for_llm, num_tracks=original_length, include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Decade & Discovery refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            await nav_client.update_playlist(playlist_id=scheduled_playlist.navidrome_playlist_id, track_ids=curated_track_ids, comment=reasoning or None)
            track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]
            await db.update_playlist_content(navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id, songs=track_titles, reasoning=reasoning)
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(f"✅ Refreshed decade_discovery playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing decade_discovery playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_sonic_journey_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a Sonic Journey playlist"""
    try:
        import json as _json
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        if not original_playlist:
            return

        try:
            settings = _json.loads(original_playlist["artist_id"])
            start_artist_name = settings.get("start_artist_name", "")
            end_artist_name = settings.get("end_artist_name", "")
        except Exception:
            scheduler_logger.error(f"❌ Could not parse settings for sonic_journey playlist")
            return

        original_length = original_playlist.get("playlist_length", 30)
        all_tracks = await nav_client.get_all_tracks(max_tracks=3000)
        if not all_tracks:
            return

        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        candidate_tracks = tracks_without_previous if len(tracks_without_previous) >= original_length else all_tracks

        library_stats = await nav_client.get_library_stats()
        filtered_tracks, _ = filter_tracks_for_this_is_playlist(candidate_tracks, original_length * 4, library_stats)

        curation_result = await ai_client_instance.curate_sonic_journey(
            start_artist=start_artist_name, end_artist=end_artist_name,
            tracks_json=filtered_tracks, num_tracks=original_length, include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Sonic Journey refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            await nav_client.update_playlist(playlist_id=scheduled_playlist.navidrome_playlist_id, track_ids=curated_track_ids, comment=reasoning or None)
            track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]
            await db.update_playlist_content(navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id, songs=track_titles, reasoning=reasoning)
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(f"✅ Refreshed sonic_journey playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing sonic_journey playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


async def refresh_genre_archaeology_playlist(scheduled_playlist, db: DatabaseManager):
    """Refresh a Genre Archaeology playlist"""
    try:
        import json as _json
        nav_client = get_navidrome_client()
        ai_client_instance = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next((p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id), None)
        if not original_playlist:
            return

        try:
            settings = _json.loads(original_playlist["artist_id"])
            genre = settings.get("genre", "")
            dig_depth = settings.get("dig_depth", "Medium")
        except Exception:
            scheduler_logger.error(f"❌ Could not parse settings for genre_archaeology playlist")
            return

        all_tracks = await nav_client.get_tracks_by_genre(genre)
        if not all_tracks:
            return

        original_length = original_playlist.get("playlist_length", 30)
        previous_songs = original_playlist.get("songs", [])
        previous_titles = set(previous_songs)
        tracks_without_previous = [t for t in all_tracks if t.get("title", "") not in previous_titles]
        candidate_tracks = tracks_without_previous if len(tracks_without_previous) >= original_length else all_tracks

        if dig_depth == "Deep":
            tracks_for_llm = candidate_tracks
        else:
            library_stats = await nav_client.get_library_stats()
            tracks_for_llm, _ = filter_tracks_for_this_is_playlist(candidate_tracks, original_length, library_stats)

        curation_result = await ai_client_instance.curate_genre_archaeology(
            genre=genre, dig_depth=dig_depth, tracks_json=tracks_for_llm,
            num_tracks=original_length, include_reasoning=True
        )
        curated_track_ids, reasoning = curation_result if isinstance(curation_result, tuple) else (curation_result, "")

        if _is_transient_fallback(reasoning):
            retry_at = datetime.now() + timedelta(hours=1)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, retry_at)
            scheduler_logger.warning(
                f"⚠️ AI error on Genre Archaeology refresh — keeping existing playlist unchanged. "
                f"Retry scheduled for {retry_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            return

        if curated_track_ids:
            await nav_client.update_playlist(playlist_id=scheduled_playlist.navidrome_playlist_id, track_ids=curated_track_ids, comment=reasoning or None)
            track_id_to_title = {t["id"]: t["title"] for t in all_tracks}
            track_titles = [track_id_to_title[tid] for tid in curated_track_ids if tid in track_id_to_title]
            await db.update_playlist_content(navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id, songs=track_titles, reasoning=reasoning)
            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(f"✅ Refreshed genre_archaeology playlist {scheduled_playlist.navidrome_playlist_id}")

    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing genre_archaeology playlist {scheduled_playlist.navidrome_playlist_id}: {e}")


@app.get("/api/playlists")
async def get_all_playlists(db: DatabaseManager = Depends(get_db)):
    """Get all playlists with scheduling information"""
    try:
        playlists = await db.get_all_playlists_with_schedule_info()
        # Add track count to each playlist
        for playlist in playlists:
            songs = playlist.get("songs", [])
            playlist["track_count"] = len(songs) if isinstance(songs, list) else 0
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlists: {str(e)}")

@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a playlist from both local database and Navidrome"""
    try:
        # First, get the specific playlist to find the Navidrome playlist ID
        # Use a direct query instead of fetching all playlists
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        
        # Delete from Navidrome if we have a playlist ID
        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if navidrome_playlist_id:
            nav_client = get_navidrome_client()
            try:
                print(f"🗑️ Deleting playlist {playlist_id} from Navidrome (Navidrome ID: {navidrome_playlist_id})")
                deletion_result = await nav_client.delete_playlist(navidrome_playlist_id)
                print(f"✅ Navidrome deletion result: {deletion_result}")
            except Exception as e:
                print(f"❌ Warning: Failed to delete playlist from Navidrome: {e}")
                # Continue with local deletion even if Navidrome deletion fails
        else:
            print(f"⚠️ No Navidrome playlist ID found for local playlist {playlist_id}, skipping Navidrome deletion")
        
        # Delete from scheduled playlists if it exists
        if navidrome_playlist_id:
            await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
        
        # Delete from local database
        success = await db.delete_playlist(playlist_id)
        
        if not success:
            raise HTTPException(status_code=404, detail="Playlist not found in database")
        
        return {"message": "Playlist deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete playlist: {str(e)}")

@app.post("/api/playlists/{playlist_id}/refresh")
async def refresh_playlist_now(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Manually refresh a specific playlist immediately"""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)

        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if not navidrome_playlist_id:
            raise HTTPException(status_code=400, detail="Playlist has no Navidrome ID")

        playlist_type = playlist.get("playlist_type")
        if not playlist_type:
            raise HTTPException(status_code=400, detail="Playlist has no scheduled refresh type - only scheduled playlists can be refreshed")

        # Get the scheduled playlist record to pass into the refresh functions
        scheduled = await db.get_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
        if not scheduled:
            raise HTTPException(status_code=400, detail="No refresh schedule found for this playlist. Set a refresh frequency first.")

        # Clean up any duplicates to keep DB tidy
        await db.delete_duplicate_scheduled_playlists(navidrome_playlist_id)

        scheduler_logger.info(f"🔄 Manual refresh requested for playlist ID: {playlist_id} (type: {playlist_type})")

        if scheduled.playlist_type in ("rediscover", "rediscover_weekly_v2"):
            await refresh_rediscover_playlist(scheduled, db)
        elif scheduled.playlist_type == "this_is":
            await refresh_this_is_playlist(scheduled, db)
        elif scheduled.playlist_type == "genre_mix":
            await refresh_genre_mix_playlist(scheduled, db)
        elif scheduled.playlist_type == "multi_artist_radio":
            await refresh_multi_artist_radio_playlist(scheduled, db)
        elif scheduled.playlist_type == "multi_genre_mix":
            await refresh_multi_genre_mix_playlist(scheduled, db)
        elif scheduled.playlist_type == "decade_discovery":
            await refresh_decade_discovery_playlist(scheduled, db)
        elif scheduled.playlist_type == "sonic_journey":
            await refresh_sonic_journey_playlist(scheduled, db)
        elif scheduled.playlist_type == "genre_archaeology":
            await refresh_genre_archaeology_playlist(scheduled, db)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported playlist type for refresh: {scheduled.playlist_type}")

        return {"message": "Playlist refreshed successfully"}

    except HTTPException:
        raise
    except Exception as e:
        scheduler_logger.error(f"❌ Error in manual playlist refresh for ID {playlist_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh playlist: {str(e)}")

@app.patch("/api/playlists/{playlist_id}/settings")
async def update_playlist_settings(playlist_id: int, request: UpdatePlaylistSettingsRequest, db: DatabaseManager = Depends(get_db)):
    """Update playlist refresh frequency settings"""
    try:
        if request.refresh_frequency not in ["none", "daily", "weekly", "monthly"]:
            raise HTTPException(status_code=400, detail="Invalid refresh_frequency. Must be one of: none, daily, weekly, monthly")

        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if not navidrome_playlist_id:
            raise HTTPException(status_code=400, detail="Playlist has no Navidrome ID")

        if request.refresh_frequency == "none":
            # Remove the scheduled refresh entirely
            await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
            scheduler_logger.info(f"📅 Removed refresh schedule for playlist ID: {playlist_id}")
            return {"message": "Scheduled refresh removed", "refresh_frequency": "none", "next_refresh": None}
        else:
            next_refresh = calculate_next_refresh(request.refresh_frequency)

            # Clean up any duplicates first
            await db.delete_duplicate_scheduled_playlists(navidrome_playlist_id)

            existing = await db.get_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)

            if existing:
                await db.update_scheduled_playlist_settings(
                    navidrome_playlist_id=navidrome_playlist_id,
                    refresh_frequency=request.refresh_frequency,
                    next_refresh=next_refresh
                )
            else:
                # Create a new schedule - determine playlist type from current data
                playlist_type = playlist.get("playlist_type")
                if not playlist_type:
                    # Infer type from playlist name as fallback
                    playlist_name = playlist.get("playlist_name", "")
                    if "Re-Discover" in playlist_name:
                        playlist_type = "rediscover"
                    elif "Genre Mix" in playlist_name:
                        playlist_type = "genre_mix"
                    else:
                        playlist_type = "this_is"

                await db.create_scheduled_playlist(
                    playlist_type=playlist_type,
                    navidrome_playlist_id=navidrome_playlist_id,
                    refresh_frequency=request.refresh_frequency,
                    next_refresh=next_refresh
                )
                # Register scheduler job in case it's not running
                schedule_playlist_refresh()

            scheduler_logger.info(f"📅 Updated refresh schedule for playlist ID: {playlist_id} to {request.refresh_frequency}, next: {next_refresh.isoformat()}")
            return {
                "message": "Playlist settings updated",
                "refresh_frequency": request.refresh_frequency,
                "next_refresh": next_refresh.isoformat()
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update playlist settings: {str(e)}")

@app.get("/api/recipes")
async def get_available_recipes():
    """Get information about available playlist generation recipes"""
    try:
        recipes_info = recipe_manager.list_available_recipes()
        return recipes_info
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load recipes: {str(e)}")

@app.get("/api/recipes/validate")
async def validate_recipes():
    """Validate all recipe files and return any errors"""
    try:
        registry = recipe_manager._load_registry()
        validation_results = {}
        
        for playlist_type, recipe_filename in registry.items():
            errors = recipe_manager.validate_recipe(recipe_filename)
            validation_results[playlist_type] = {
                "recipe_file": recipe_filename,
                "valid": len(errors) == 0,
                "errors": errors
            }
        
        return validation_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate recipes: {str(e)}")

@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and active jobs"""
    try:
        global scheduler
        if scheduler:
            jobs = list(scheduler.get_jobs())
            job_info = []
            for job in jobs:
                job_info.append({
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "func": job.func.__name__ if hasattr(job, 'func') else str(job.func)
                })
            
            return {
                "scheduler_running": scheduler.running,
                "active_jobs": len(jobs),
                "jobs": job_info,
                "scheduler_state": str(scheduler.state)
            }
        else:
            return {
                "scheduler_running": False,
                "error": "Scheduler not initialized"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")

@app.post("/api/scheduler/trigger")
async def trigger_scheduler_check():
    """Manually trigger the scheduler to check for playlists due for refresh"""
    try:
        scheduler_logger.info("🧪 Manual scheduler trigger requested via API")
        await refresh_scheduled_playlists()
        return {"message": "Scheduler check completed successfully"}
    except Exception as e:
        scheduler_logger.error(f"❌ Error in manual scheduler trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")

@app.post("/api/scheduler/start")
async def start_scheduler_job():
    """Manually start the recurring scheduler job"""
    try:
        schedule_playlist_refresh()
        global scheduler
        jobs = list(scheduler.get_jobs()) if scheduler else []
        scheduler_logger.info(f"🔄 Scheduler job registration requested. Active jobs: {len(jobs)}")
        return {
            "message": "Scheduler job started",
            "active_jobs": len(jobs),
            "jobs": [{"id": job.id, "next_run": job.next_run_time.isoformat() if job.next_run_time else None} for job in jobs]
        }
    except Exception as e:
        scheduler_logger.error(f"❌ Error starting scheduler job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler job: {str(e)}")

@app.get("/api/ai-model-info")
async def get_ai_model_info():
    """Get current AI model information for analytics"""
    try:
        ai_client_instance = get_ai_client()
        return {
            "provider": ai_client_instance.provider.provider_type,
            "model": ai_client_instance.model or "unknown",
            "has_api_key": bool(ai_client_instance.api_key)
        }
    except Exception as e:
        return {
            "provider": "unknown",
            "model": "unknown", 
            "has_api_key": False
        }

@app.post("/api/track-library-size")
async def track_library_size(db: DatabaseManager = Depends(get_db)):
    """Track library size for analytics (called post-launch)"""
    try:
        # Check if we should track (90+ days since last tracking)
        should_track = await db.should_track_library_size()
        if not should_track:
            return {"message": "Library size tracking not needed yet", "tracked": False}
        
        # Get Navidrome client and query library size
        nav_client = get_navidrome_client()
        song_count = await nav_client.get_total_song_count()
        
        # Get or create user ID and record the data
        user_id = await db.get_or_create_user_id()
        await db.record_library_size(song_count)
        
        scheduler_logger.info(f"📊 Library size tracked: {song_count} songs for user {user_id}")
        
        return {
            "message": "Library size tracked successfully",
            "tracked": True,
            "song_count": song_count,
            "user_id": user_id
        }
        
    except Exception as e:
        scheduler_logger.error(f"❌ Error tracking library size: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track library size: {str(e)}")

# SPA ROUTING - Smart catch-all for client-side routing (MUST be last route)
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_router(request: Request, path: str):
    """Handle SPA routing - serve app for known paths, redirect unknown paths"""
    # Known SPA paths - serve the app and let frontend handle routing
    spa_paths = ["this-is", "re-discover", "playlists", "terms", "multi-artist-radio", "multi-genre-mix", "decade-discovery", "sonic-journey", "genre-archaeology"]
    
    if path in spa_paths:
        # Apply same system check logic as root
        if not system_check_passed:
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url="/system-check", status_code=302)
        return templates.TemplateResponse(request, "index.html")

    # Unknown paths - redirect to home
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/", status_code=302)

if __name__ == "__main__":
    # Custom logging config to filter out Umami heartbeat requests
    import uvicorn.config
    
    class FilteredUvicornFormatter(uvicorn.formatters.DefaultFormatter):
        def format(self, record):
            # Filter out GET / requests (Umami heartbeats) from access logs
            if hasattr(record, 'args') and record.args:
                # Look for GET / HTTP patterns in the log message
                message = str(record.args[2]) if len(record.args) > 2 else ""
                if 'GET / HTTP' in message:
                    return ""  # Return empty string to suppress this log
            return super().format(record)
    
    # Configure uvicorn with custom formatter
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["()"] = FilteredUvicornFormatter
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8000,
        log_config=log_config
    )