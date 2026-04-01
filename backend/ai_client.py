import heapq
import math
import httpx
import os
import json
from collections import defaultdict, deque
from typing import List, Dict, Any, Union, Tuple, Optional
from .recipe_manager import recipe_manager
from .services.ai_providers import get_ai_provider


import re as _re

def _primary_artist(artist) -> str:
    """
    Normalise a collaboration string to the primary artist so that
    'Queen' and 'Queen & David Bowie' are treated as the same artist.

    Rules applied in order:
      1. Strip featured artist:  'Linkin Park feat. Jay-Z' → 'Linkin Park'
      2. Strip guest collab where the guest looks like a person name
         (part after ' & ' contains a space):
         'Queen & David Bowie' → 'Queen'
         'Simon & Garfunkel'   → 'Simon & Garfunkel'  (no space after &)
         'Earth, Wind & Fire'  → 'Earth, Wind & Fire'  (no space after &)
    """
    if not artist:
        return "Unknown"
    artist = str(artist)
    # Strip featuring
    artist = _re.split(
        r'\s+(?:feat\.?|ft\.?|featuring|with)\s+',
        artist,
        maxsplit=1,
        flags=_re.IGNORECASE,
    )[0].strip()
    # Strip collaboration guest that looks like a person name
    parts = _re.split(r'\s+&\s+', artist, maxsplit=1)
    if len(parts) == 2 and ' ' in parts[1]:
        artist = parts[0].strip()
    return artist or "Unknown"


def _distribute_by_artist(
    track_ids: List[str],
    id_to_artist: Dict[str, str],
    num_tracks: int,
) -> List[str]:
    """
    Reorder track_ids so that:
      1. No two consecutive tracks share the same primary artist.
      2. Each primary artist appears at most fair_share times, where
         fair_share = ceil(num_tracks / n_artists).

    Artist strings are normalised via _primary_artist() so that e.g.
    'Queen' and 'Queen & David Bowie' count as the same artist.

    When only one artist remains and a consecutive pair would be forced,
    that track is still appended (accepting a single consecutive pair is
    always better than leaving a gap that gets filled with unsorted data).
    """
    artist_queues: Dict[str, deque] = defaultdict(deque)
    for tid in track_ids:
        raw = id_to_artist.get(tid) or "Unknown"
        primary = _primary_artist(raw)
        artist_queues[primary].append(tid)

    n_artists = len(artist_queues)
    if n_artists <= 1:
        return list(track_ids[:num_tracks])

    fair_share = math.ceil(num_tracks / n_artists)
    max_per_artist = max(2, fair_share)

    for artist in list(artist_queues):
        q = artist_queues[artist]
        while len(q) > max_per_artist:
            q.pop()

    # Max-heap: (-remaining, tiebreak, artist)
    tb = 0
    heap: List = []
    for artist, q in artist_queues.items():
        if q:
            heapq.heappush(heap, (-len(q), tb, artist))
            tb += 1

    result: List[str] = []
    prev_artist: str = ""

    while heap and len(result) < num_tracks:
        neg, t, artist = heapq.heappop(heap)

        if artist == prev_artist:
            if heap:
                # Swap with the next-best artist
                neg2, t2, artist2 = heapq.heappop(heap)
                result.append(artist_queues[artist2].popleft())
                prev_artist = artist2
                if artist_queues[artist2]:
                    heapq.heappush(heap, (-len(artist_queues[artist2]), tb, artist2))
                    tb += 1
                heapq.heappush(heap, (neg, t, artist))
            else:
                # No alternative — accept one consecutive rather than leaving a gap
                result.append(artist_queues[artist].popleft())
                prev_artist = artist
                if artist_queues[artist]:
                    heapq.heappush(heap, (-len(artist_queues[artist]), tb, artist))
                    tb += 1
        else:
            result.append(artist_queues[artist].popleft())
            prev_artist = artist
            if artist_queues[artist]:
                heapq.heappush(heap, (-len(artist_queues[artist]), tb, artist))
                tb += 1

    return result


class AIClient:
    """Client for AI-powered track curation using configurable providers"""
    
    def __init__(self):
        self.provider = get_ai_provider()
        # Backward compatibility - keep these for fallback logic
        self.api_key = self.provider.api_key
        self.model = self.provider.model
        self.base_url = self.provider.base_url

        # Debug logging
        print(f"🔍 AIClient initialized with provider: {self.provider.provider_type}")
        print(f"🤖 Using model: {self.model}")
        print(f"🌐 Base URL: {self.base_url}")
        
        
    async def curate_this_is(
        self, 
        artist_name: str, 
        tracks_json: List[Dict[str, Any]], 
        num_tracks: int = 20,
        include_reasoning: bool = False,
        variety_context: str = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a 'This Is' playlist for a single artist using AI
        
        Args:
            artist_name: Name of the artist
            tracks_json: List of track dictionaries with id, title, album, year, play_count
            num_tracks: Number of tracks to select (default: 20)
            include_reasoning: Whether to return AI's reasoning along with track IDs
            
        Returns:
            List of track IDs in curated order, or tuple of (track_ids, reasoning) if include_reasoning=True
        """
        
        if not self.api_key and self.provider.provider_type == "openrouter":
            print(f"❌ No AI API key configured, using fallback curation for {artist_name}")
            # Processing tracks for curation (logging moved to scheduler_logger)
            # Fallback: return first num_tracks by play count
            sorted_tracks = sorted(
                tracks_json,
                key=lambda x: x.get("play_count", 0),
                reverse=True
            )
            track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]

            if include_reasoning:
                fallback_reasoning = f"Fallback curation: Selected {len(track_ids)} tracks sorted by play count (highest first). No AI API key configured."
                return track_ids, fallback_reasoning
            else:
                return track_ids
        
        try:
            # Using AI to curate playlist (logging moved to scheduler_logger)
            
            # SHUFFLE tracks to prevent AI from album-grouping based on input order
            import random
            shuffled_tracks = tracks_json.copy()  # Don't modify the original list
            random.shuffle(shuffled_tracks)
            
            # Note: We now pass shuffled_tracks directly as clean JSON array to the AI
            # No more string conversion and text blob parsing!
            
            # Log track data completeness
            original_track_count = len(tracks_json)
            shuffled_track_count = len(shuffled_tracks)
            
            print(f"🎵 Preparing {shuffled_track_count} tracks for AI curation")
            
            # Verify track data includes essential fields
            if shuffled_tracks:
                sample_track = shuffled_tracks[0]
                essential_fields = ['id', 'title', 'artist', 'album']
                missing_fields = [field for field in essential_fields if field not in sample_track]
                if missing_fields:
                    print(f"⚠️  Missing essential fields in tracks: {missing_fields}")
            else:
                print(f"❌ ERROR: No tracks available for curation!")
            
            # Use recipe system to generate prompt and get LLM parameters
            recipe_inputs = {
                "artists": artist_name,
                "num_tracks": num_tracks,
                "variety_context": variety_context or ""
            }
            
            print(f"🍳 Applying recipe for {artist_name} ({num_tracks} tracks)")
            
            final_recipe = recipe_manager.apply_recipe("this_is", recipe_inputs, include_reasoning)
            
            # Check if this is new recipe format (has llm_config) or legacy format
            if "llm_config" in final_recipe:
                # New recipe format
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")
                
                # Use model from environment (.env file), ignoring recipe model_name
                model = self.model or "openai/gpt-3.5-turbo"
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1000)
                
                print(f"🤖 Using AI model: {model} (from {self.provider.provider_type} provider)")

                # Serialize the complete recipe (excluding tracks_data to avoid duplication)
                recipe_without_tracks = {k: v for k, v in final_recipe.items() if k != "tracks_data"}

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # Build structured JSON payload with INDEX-BASED approach
                # Create indexed tracks (remove complex IDs, use simple indices)
                indexed_tracks = []
                track_id_map = []  # Keep mapping of index → actual track ID
                
                for index, track in enumerate(shuffled_tracks):
                    # Store the actual track ID in our mapping
                    track_id_map.append(track["id"])
                    
                    # Create indexed track (minimal essential data to reduce token usage)
                    indexed_track = {
                        "index": index,
                        "track_name": track.get("title", "Unknown"),
                        "album": track.get("album", "Unknown"),
                        "year": track.get("year", 0),
                        "play_count": track.get("play_count", 0),
                        "local_library_likes": track.get("local_library_likes", False)
                    }
                    indexed_tracks.append(indexed_track)
                
                structured_payload = {
                    "recipe": recipe_without_tracks,
                    "available_tracks": indexed_tracks,  # INDEX-BASED tracks (no complex IDs)
                    "request": {
                        "artist_name": artist_name,
                        "desired_track_count": num_tracks,
                        "playlist_type": "this_is"
                     }
                }

                print(f"🔢 Using index-based approach for {len(track_id_map)} tracks")

                # Minimal payload for "This Is" - only essential data
                user_content = f"""Select up to {num_tracks} tracks for a "This Is {artist_name}" playlist. If fewer than {num_tracks} tracks are available, select all available tracks.

Tracks: {json.dumps(indexed_tracks, separators=(',', ':'), ensure_ascii=False)}

Return JSON: {{"track_ids": [indices], "reasoning": "summary"}}"""
                
                payload = {
                    "model": model,
                    "messages": [
                        {
                            "role": "system",
                            "content": model_instructions
                        },
                        {
                            "role": "user", 
                            "content": user_content
                        }
                    ],
                    "max_tokens": max_tokens,
                    "temperature": temperature
                }
                
                print(f"💬 Sending structured payload to AI")
                
                # DEBUG: Dump payload to file for "This Is" playlist inspection

            else:
                # Legacy recipe format
                prompt = final_recipe["prompt"]
                llm_params = final_recipe["llm_params"]
                
                # Use model from environment first, only fallback to recipe if not set
                model = self.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_params.get("temperature", 0.7)
                max_tokens = llm_params.get("max_tokens", 1000)
                

                
                system_prompt = "You are a professional music curator. Always respond with valid JSON containing track_ids array and reasoning string. No other text outside the JSON."
            
            
            # Use the provider to make the AI request
            if "llm_config" in final_recipe:
                # New recipe format - use structured payload
                content = await self.provider.generate(
                    system_prompt=model_instructions,
                    user_prompt=user_content,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            else:
                # Legacy recipe format
                content = await self.provider.generate(
                    system_prompt="You are a professional music curator. Always respond with valid JSON containing track_ids array and reasoning string. No other text outside the JSON.",
                    user_prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

            # Log the full raw AI response for debugging
            print(f"🤖 FULL RAW AI RESPONSE for This Is: {content}")

            # Parse the JSON response with comprehensive validation
            try:
                # Clean up the response and extract JSON
                cleaned_content = content.strip()

                # Remove markdown code fences if present
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]  # Remove ```json
                if cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content[3:]   # Remove ```
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]  # Remove trailing ```

                cleaned_content = cleaned_content.strip()

                # Extract JSON from mixed text/JSON response
                import re

                # Try to find JSON object first (new format): {"track_ids": [...], "reasoning": "..."}
                json_object_match = re.search(r'\{.*?"track_ids".*?\}', cleaned_content, re.DOTALL)
                if json_object_match:
                    json_str = json_object_match.group(0)
                    print(f"🔍 Extracted JSON object: {json_str[:100]}...")
                else:
                    # Try to find JSON array (legacy format): [1, 2, 3, ...]
                    json_array_match = re.search(r'\[([\d\s,]+)\]', cleaned_content, re.DOTALL)
                    if json_array_match:
                        json_str = json_array_match.group(0)
                        print(f"🔍 Extracted JSON array: {json_str[:100]}...")
                    else:
                        # No JSON found, try to parse the whole cleaned content
                        json_str = cleaned_content
                        print(f"🔍 Using entire cleaned content for JSON parsing")

                # Clean up the extracted JSON
                lines = json_str.split('\n')
                cleaned_lines = []

                for line in lines:
                    # Remove // comments but preserve URLs like http://
                    if '//' in line and 'http://' not in line and 'https://' not in line:
                        comment_pos = line.find('//')
                        line = line[:comment_pos].rstrip()

                    # Remove trailing commas before closing brackets
                    line = re.sub(r',(\s*[\]}])', r'\1', line)

                    if line.strip():  # Only add non-empty lines
                        cleaned_lines.append(line)

                final_json = '\n'.join(cleaned_lines).strip()

                # Try to parse the extracted JSON
                response_data = json.loads(final_json)

                # Validate response structure with index-based approach
                source_track_count = len(tracks_json)
                
                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning - validate structure
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")
                    
                    # Structure checks
                    if not isinstance(track_ids, list):
                        print(f"❌ Response validation failed: track_ids is not a list")
                        raise ValueError("Response structure invalid: track_ids must be a list")
                    
                    if not isinstance(reasoning, str):
                        print(f"❌ Response validation failed: reasoning is not a string")
                        raise ValueError("Response structure invalid: reasoning must be a string")

                    # INDEX-BASED: Validate all track IDs are integers (indices)
                    if not all(isinstance(tid, int) for tid in track_ids):
                        print(f"❌ Response validation failed: not all track_ids are integers")
                        raise ValueError("Invalid track_ids format: all IDs must be integers (indices)")
                    
                    returned_track_count = len(track_ids)

                    # Simplified validation - focus on response quality
                    # Check 1: AI returned some tracks
                    if returned_track_count == 0:
                        print(f"❌ AI returned no tracks - invalid response")
                        raise ValueError("AI response validation failed: No tracks returned")

                    # Check 2: Reasonable upper bound
                    max_reasonable = int(num_tracks * 1.5)  # Allow up to 1.5x requested for minor flexibility
                    if returned_track_count > max_reasonable:
                        print(f"❌ AI returned {returned_track_count} tracks, much more than requested {num_tracks}")
                        raise ValueError(f"AI response validation failed: Too many tracks returned ({returned_track_count} vs requested {num_tracks})")

                    # Check 3: Allow AI to return more indices than available tracks (for duplicates to reach target count)
                    # Note: Invalid indices will be filtered out later, duplicates are allowed

                    print(f"✅ AI returned {returned_track_count} tracks (requested: {num_tracks}), validation passed")

                    # INDEX-BASED: Map indices back to actual track IDs
                    # Find which indices are invalid (out of range)
                    invalid_indices = [idx for idx in track_ids if idx < 0 or idx >= len(track_id_map)]
                    if invalid_indices:
                        print(f"❌ AI returned {len(invalid_indices)} invalid indices out of {len(track_ids)}")
                    
                    # Map valid indices to actual track IDs
                    valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
                    mapped_track_ids = [track_id_map[idx] for idx in valid_indices]
                    # Mapped indices to track IDs
                    
                    # Final selection (limit to requested count)
                    final_selection = mapped_track_ids[:num_tracks]
                    
                    # AI curation successful for Re-Discover Weekly (logging moved to scheduler_logger)
                    if reasoning:
                        # AI reasoning available (logged in main.py scheduler_logger)
                        pass

                    # Final selection (limit to requested count)
                    final_selection = mapped_track_ids[:num_tracks]

                    if include_reasoning:
                        return final_selection, reasoning
                    else:
                        return final_selection

                # Handle simple array format (legacy)
                elif isinstance(response_data, list) and all(isinstance(tid, str) for tid in response_data):
                    valid_ids = {track["id"] for track in tracks_json}
                    filtered_ids = [tid for tid in response_data if tid in valid_ids]
                    id_to_artist = {t["id"]: t.get("artist", "Unknown") for t in shuffled_tracks}
                    filtered_ids = _distribute_by_artist(filtered_ids, id_to_artist, num_tracks)
                    final_selection = filtered_ids[:num_tracks]

                    if include_reasoning:
                        return final_selection, ""  # No reasoning available
                    else:
                        return final_selection
                else:
                    raise ValueError("Invalid response format: expected dict with track_ids or array of track IDs")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse AI response: {e}")
                print(f"Response content: {content}")
                # Fall back to simple selection
                return self._fallback_rediscover_selection(tracks_json, num_tracks, include_reasoning)

        except httpx.RequestError as e:
            print(f"🌐 Network error calling AI API: {e}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🌐 Base URL: {self.base_url}")
            return self._fallback_rediscover_selection(tracks_json, num_tracks, include_reasoning, f"Network error: {e}")
        except httpx.HTTPStatusError as e:
            response_text = e.response.text

            # Detect HTML error pages (like Cloudflare 502 errors) and truncate for logging
            if (response_text.strip().startswith('<!DOCTYPE html') or
                response_text.strip().startswith('<html') or
                len(response_text) > 500):

                # Truncate long responses for clean logging
                truncated_text = response_text[:200] + "..." if len(response_text) > 200 else response_text
                print(f"🚨 HTTP error from AI API: {e.response.status_code} - {truncated_text}")

                # User-friendly error for common infrastructure issues
                if e.response.status_code in [502, 503, 504]:
                    user_message = f"AI service temporarily unavailable (error {e.response.status_code}). Please try again in a minute."
                else:
                    user_message = f"AI service error (HTTP {e.response.status_code}). Please try again."

                return self._fallback_rediscover_selection(tracks_json, num_tracks, include_reasoning, user_message)
            else:
                # Normal error response, log as before
                print(f"🚨 HTTP error from AI API: {e.response.status_code} - {response_text}")
                print(f"🔑 API Key present: {bool(self.api_key)}")
                print(f"🤖 Model: {self.model}")
                return self._fallback_rediscover_selection(tracks_json, num_tracks, include_reasoning, f"HTTP {e.response.status_code}: {response_text}")
        except Exception as e:
            print(f"💥 Unexpected error in This Is AI curation: {e}")
            import traceback
            print(f"📋 Traceback: {traceback.format_exc()}")
            return self._fallback_rediscover_selection(tracks_json, num_tracks, include_reasoning, f"Unexpected error: {e}")

    async def curate_rediscover_weekly(
        self,
        candidate_tracks: List[Dict[str, Any]],
        analysis_summary: str,
        num_tracks: int = 20,
        include_reasoning: bool = True,
        variety_context: str = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Re-Discover Weekly playlist using AI

        Args:
            candidate_tracks: List of pre-filtered candidate tracks with metadata
            analysis_summary: Summary of the algorithmic analysis performed
            num_tracks: Number of tracks to select (default: 20)
            include_reasoning: Whether to return AI's reasoning along with track IDs
            variety_context: Additional context for variety (optional)

        Returns:
            List of track IDs in curated order, or tuple of (track_ids, reasoning) if include_reasoning=True
        """

        if not self.api_key and self.provider.provider_type == "openrouter":
            print(f"❌ No AI API key configured, using fallback curation for Re-Discover Weekly")
            # Fallback: return first num_tracks by score (should already be sorted by rediscover algorithm)
            track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]

            if include_reasoning:
                fallback_reasoning = f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic scoring (highest score first). No AI API key configured."
                return track_ids, fallback_reasoning
            else:
                return track_ids

        # Build indexed tracks (remove complex IDs, use simple indices)
        indexed_tracks = []
        track_id_map = []  # Keep mapping of index → actual track ID

        for index, track in enumerate(candidate_tracks):
            # Store the actual track ID in our mapping
            track_id_map.append(track["id"])

            # Create indexed track (minimal metadata to reduce prompt size)
            indexed_track = {
                "index": index,
                "track_name": track.get("title", "Unknown"),
                "artist": track.get("artist", "Unknown"),
                "genre": track.get("genre", "Unknown"),
                "rediscovery_score": round(track.get("rediscovery_score", 0), 1)
            }
            indexed_tracks.append(indexed_track)

        try:
            print(f"🤖 Making AI request for Re-Discover Weekly curation...")

            # Use recipe system with proper placeholder replacement
            recipe_inputs = {
                "analysis_summary": analysis_summary,
                "num_tracks": num_tracks
            }

            final_recipe = recipe_manager.apply_recipe("re_discover", recipe_inputs)

            # Check if this is new recipe format (has llm_config) or legacy format
            if "llm_config" in final_recipe:
                # New recipe format with placeholders properly replaced
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")

                # Use model from environment (.env file), ignoring recipe model_name
                model = self.model or "openai/gpt-3.5-turbo"
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1500)

                print(f"🤖 Using AI model: {model} (from {self.provider.provider_type} provider)")

                # Serialize the complete recipe (excluding tracks for structured payload)
                recipe_without_tracks = {k: v for k, v in final_recipe.items() if k not in ["candidate_tracks", "tracks_data"]}

                structured_payload = {
                    "recipe": recipe_without_tracks,
                    "available_tracks": indexed_tracks,  # INDEX-BASED tracks (no complex IDs)
                    "analysis_summary": analysis_summary,
                    "request": {
                        "desired_track_count": num_tracks,
                        "playlist_type": "rediscover",
                        "variety_context": variety_context or ""
                    }
                }

                # Minimal payload for re-discover - only essential data
                user_content = f"""Select {num_tracks} tracks for a Re-Discover Weekly playlist.

Tracks: {json.dumps(indexed_tracks, separators=(',', ':'), ensure_ascii=False)}

Return JSON: {{"track_ids": [indices], "reasoning": "summary"}}"""

                print(f"📤 Phase 2 AI Payload (first 500 chars): {user_content[:500]}...")
                print(f"📤 Phase 2 AI Payload (structured_tracks count): {len(indexed_tracks)}")

                content = await self.provider.generate(
                    system_prompt=model_instructions,
                    user_prompt=user_content,
                    max_tokens=max_tokens,
                    temperature=temperature
                )
            else:
                # Legacy recipe format fallback
                prompt = final_recipe.get("prompt", "")
                llm_params = final_recipe.get("llm_params", {})

                model = self.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_params.get("temperature", 0.8)
                max_tokens = llm_params.get("max_tokens", 2500)

                content = await self.provider.generate(
                    system_prompt="You are a professional music curator specializing in rediscovery playlists. Always respond with valid JSON containing track_ids array and reasoning string. No other text outside the JSON.",
                    user_prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature
                )

            # Parse the JSON response with comprehensive validation
            try:
                # Clean up the response and extract JSON
                cleaned_content = content.strip()

                # Remove markdown code fences if present
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]  # Remove ```json
                if cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content[3:]   # Remove ```
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]  # Remove trailing ```

                cleaned_content = cleaned_content.strip()

                # Extract JSON from mixed text/JSON response
                import re

                # Try to find JSON object first (new format): {"track_ids": [...], "reasoning": "..."}
                json_object_match = re.search(r'\{.*?"track_ids".*?\}', cleaned_content, re.DOTALL)
                if json_object_match:
                    json_str = json_object_match.group(0)
                    print(f"🔍 Extracted JSON object: {json_str[:100]}...")
                else:
                    # Try to find JSON array (legacy format): [1, 2, 3, ...]
                    json_array_match = re.search(r'\[([\d\s,]+)\]', cleaned_content, re.DOTALL)
                    if json_array_match:
                        json_str = json_array_match.group(0)
                        print(f"🔍 Extracted JSON array: {json_str[:100]}...")
                    else:
                        # No JSON found, try to parse the whole cleaned content
                        json_str = cleaned_content
                        print(f"🔍 Using entire cleaned content for JSON parsing")

                # Clean up the extracted JSON
                lines = json_str.split('\n')
                cleaned_lines = []

                for line in lines:
                    # Remove // comments but preserve URLs like http://
                    if '//' in line and 'http://' not in line and 'https://' not in line:
                        comment_pos = line.find('//')
                        line = line[:comment_pos].rstrip()

                    # Remove trailing commas before closing brackets
                    line = re.sub(r',(\s*[\]}])', r'\1', line)

                    if line.strip():  # Only add non-empty lines
                        cleaned_lines.append(line)

                final_json = '\n'.join(cleaned_lines).strip()

                # Try to parse the extracted JSON
                result = json.loads(final_json)

                # Validate response structure with index-based approach
                if isinstance(result, dict) and "track_ids" in result:
                    # New format with reasoning - validate structure
                    track_indices = result.get("track_ids", [])
                    reasoning = result.get("reasoning", "")

                    # Structure checks
                    if not isinstance(track_indices, list):
                        print(f"❌ Response validation failed: track_ids is not a list")
                        raise ValueError("Response structure invalid: track_ids must be a list")

                    if not isinstance(reasoning, str):
                        print(f"❌ Response validation failed: reasoning is not a string")
                        raise ValueError("Response structure invalid: reasoning must be a string")

                    print(f"✅ Response validation passed: {len(track_indices)} track indices, reasoning length: {len(reasoning)}")

                    # Map indices back to actual track IDs
                    track_ids = []
                    for index in track_indices:
                        if 0 <= index < len(track_id_map):
                            track_ids.append(track_id_map[index])
                        else:
                            print(f"⚠️ Invalid track index {index}, skipping")

                    print(f"🔄 Mapped {len(track_ids)} track IDs from {len(track_indices)} indices")

                    # Ensure we have the right number of tracks
                    if len(track_ids) < num_tracks and len(candidate_tracks) >= num_tracks:
                        # Fill with remaining tracks if AI didn't provide enough
                        used_indices = set(track_indices)
                        remaining_tracks = [track_id_map[i] for i in range(len(track_id_map)) if i not in used_indices]
                        track_ids.extend(remaining_tracks[:num_tracks - len(track_ids)])
                        print(f"🔄 Filled to {len(track_ids)} tracks with remaining candidates")

                    print(f"✅ Phase 2 AI curation successful: returning {len(track_ids)} tracks with reasoning length {len(reasoning)}")

                    if include_reasoning:
                        return track_ids, reasoning
                    else:
                        return track_ids

                else:
                    print(f"❌ Response validation failed: expected dict with 'track_ids' key, got: {type(result)}")
                    raise ValueError("Response structure invalid: missing track_ids")

            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse AI response as JSON: {e}")
                print(f"🔍 Raw response: {content}")
                return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"AI returned invalid JSON: {e}")
            except Exception as e:
                print(f"❌ Failed to validate AI response: {e}")
                print(f"🔍 Raw response: {content}")
                return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"AI response validation failed: {e}")

        except Exception as e:
            print(f"💥 Unexpected error in Re-Discover Weekly AI curation: {e}")
            import traceback
            print(f"📋 Traceback: {traceback.format_exc()}")
            return self._fallback_rediscover_selection(candidate_tracks, num_tracks, include_reasoning, f"Unexpected error: {e}")

    def _fallback_rediscover_selection(self, candidate_tracks: List[Dict[str, Any]], num_tracks: int, include_reasoning: bool = False, error_reason: str = "AI service was unavailable") -> Union[List[str], Tuple[List[str], str]]:
        """Fallback selection algorithm for rediscover when AI is unavailable"""
        # Use the pre-sorted candidates (should already be sorted by score)
        track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]
        
        if include_reasoning:
            reasoning = f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic pre-filtering (sorted by play count × days since last play). {error_reason}"
            return track_ids, reasoning
        else:
            return track_ids

    async def call_ai(self, llm_config: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """Generic method to call AI with llm_config from recipes"""
        try:
            model = self.model or llm_config.get("model_fallback", "openai/gpt-3.5-turbo")
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 1500)

            # Get system and user prompts from llm_config
            system_prompt = llm_config.get("system_prompt", "You are a helpful AI assistant.")
            user_prompt = llm_config.get("user_prompt", "")

            print(f"🤖 Making generic AI call with model {model}...")

            content = await self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Try to parse as JSON, return as string if not
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return content

        except Exception as e:
            print(f"💥 Error in generic AI call: {e}")
            raise

    async def curate_genre_mix(
        self,
        genre: str,
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 20,
        include_reasoning: bool = False,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a 'Genre Mix' playlist for a specific genre using AI

        Args:
            genre: Name of the genre
            tracks_json: List of track dictionaries with id, title, album, year, play_count
            num_tracks: Number of tracks to select (default: 20)
            include_reasoning: Whether to return AI's reasoning along with track IDs
            variety_context: Additional context for variety (optional)

        Returns:
            List of track IDs in curated order, or tuple of (track_ids, reasoning) if include_reasoning=True
        """

        if not self.api_key and self.provider.provider_type == "openrouter":
            print(f"❌ No AI API key configured, using fallback curation for {genre}")
            return self._fallback_genre_mix_selection(
                tracks_json, num_tracks, include_reasoning,
                "No AI API key configured."
            )

        try:
            # Using AI to curate playlist (logging moved to scheduler_logger)

            # SHUFFLE tracks to prevent AI from album-grouping based on input order
            import random
            shuffled_tracks = tracks_json.copy()  # Don't modify the original list
            random.shuffle(shuffled_tracks)

            # Note: We now pass shuffled_tracks directly as clean JSON array to the AI
            # No more string conversion and text blob parsing!

            # Log track data completeness
            original_track_count = len(tracks_json)
            shuffled_track_count = len(shuffled_tracks)

            print(f"🎵 Preparing {shuffled_track_count} tracks for AI curation")

            # Verify track data includes essential fields
            if shuffled_tracks:
                sample_track = shuffled_tracks[0]
                essential_fields = ['id', 'title', 'artist', 'album']
                missing_fields = [field for field in essential_fields if field not in sample_track]
                if missing_fields:
                    print(f"⚠️  Missing essential fields in tracks: {missing_fields}")
            else:
                print(f"❌ ERROR: No tracks available for curation!")

            # Use recipe system to generate prompt and get LLM parameters
            recipe_inputs = {
                "genre": genre,
                "num_tracks": num_tracks,
                "variety_context": variety_context or ""
            }

            print(f"🍳 Applying recipe for {genre} ({num_tracks} tracks)")

            final_recipe = recipe_manager.apply_recipe("genre_mix", recipe_inputs, include_reasoning)

            # Initialize variables
            model_instructions = ""
            user_content = ""
            prompt = ""
            track_id_map = []

            # New recipe format (genre_mix recipe has llm_config)
            llm_config = final_recipe.get("llm_config", {})
            model_instructions = final_recipe.get("model_instructions", "")

            # Use model from environment (.env file), ignoring recipe model_name
            model = self.model or "openai/gpt-3.5-turbo"
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 32000)

            print(f"🤖 Using AI model: {model} (from {self.provider.provider_type} provider)")

            # Serialize the complete recipe (excluding tracks_data to avoid duplication)
            recipe_without_tracks = {k: v for k, v in final_recipe.items() if k != "tracks_data"}

            # Build structured JSON payload with INDEX-BASED approach
            # Create indexed tracks (remove complex IDs, use simple indices)
            indexed_tracks = []

            for index, track in enumerate(shuffled_tracks):
                # Store the actual track ID in our mapping
                track_id_map.append(track["id"])

                # Create indexed track (minimal essential data to reduce token usage)
                indexed_track = {
                    "index": index,
                    "track_name": track.get("title", "Unknown"),
                    "artist": track.get("artist", "Unknown"),
                    "play_count": track.get("play_count", 0),
                    "local_library_likes": track.get("local_library_likes", False)
                }
                indexed_tracks.append(indexed_track)

            structured_payload = {
                "recipe": recipe_without_tracks,
                "available_tracks": indexed_tracks,  # INDEX-BASED tracks (no complex IDs)
                "request": {
                    "genre_name": genre,
                    "desired_track_count": num_tracks,
                    "playlist_type": "genre_mix"
                }
            }

            print(f"🔢 Using index-based approach for {len(track_id_map)} tracks")

            # Minimal payload for genre mix - only essential data
            user_content = f"""Select {num_tracks} tracks for a {genre} playlist.

Tracks: {json.dumps(indexed_tracks, separators=(',', ':'), ensure_ascii=False)}

Return JSON: {{"track_ids": [indices], "reasoning": "summary"}}"""

            # Use the provider to make the AI request
            content = await self.provider.generate(
                system_prompt=model_instructions,
                user_prompt=user_content,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Log the full raw AI response for debugging
            print(f"🤖 FULL RAW AI RESPONSE for Genre Mix: {content}")

            # Parse the JSON response with comprehensive validation
            try:
                # Clean up the response and extract JSON
                cleaned_content = content.strip()

                # Remove markdown code fences if present
                if cleaned_content.startswith("```json"):
                    cleaned_content = cleaned_content[7:]  # Remove ```json
                if cleaned_content.startswith("```"):
                    cleaned_content = cleaned_content[3:]   # Remove ```
                if cleaned_content.endswith("```"):
                    cleaned_content = cleaned_content[:-3]  # Remove trailing ```

                cleaned_content = cleaned_content.strip()

                # Extract JSON from mixed text/JSON response
                import re

                # Try to find JSON object first (new format): {"track_ids": [...], "reasoning": "..."}
                json_object_match = re.search(r'\{.*?"track_ids".*?\}', cleaned_content, re.DOTALL)
                if json_object_match:
                    json_str = json_object_match.group(0)
                    print(f"🔍 Extracted JSON object: {json_str[:100]}...")
                else:
                    # Try to find JSON array (legacy format): [1, 2, 3, ...]
                    json_array_match = re.search(r'\[([\d\s,]+)\]', cleaned_content, re.DOTALL)
                    if json_array_match:
                        json_str = json_array_match.group(0)
                        print(f"🔍 Extracted JSON array: {json_str[:100]}...")
                    else:
                        # No JSON found, try to parse the whole cleaned content
                        json_str = cleaned_content
                        print(f"🔍 Using entire cleaned content for JSON parsing")

                # Clean up the extracted JSON
                lines = json_str.split('\n')
                cleaned_lines = []

                for line in lines:
                    # Remove // comments but preserve URLs like http://
                    if '//' in line and 'http://' not in line and 'https://' not in line:
                        comment_pos = line.find('//')
                        line = line[:comment_pos].rstrip()

                    # Remove trailing commas before closing brackets
                    line = re.sub(r',(\s*[\]}])', r'\1', line)

                    if line.strip():  # Only add non-empty lines
                        cleaned_lines.append(line)

                final_json = '\n'.join(cleaned_lines).strip()

                # Try to parse the extracted JSON
                response_data = json.loads(final_json)

                # Validate response structure with index-based approach
                source_track_count = len(tracks_json)

                if isinstance(response_data, dict) and "track_ids" in response_data:
                    # New format with reasoning - validate structure
                    track_ids = response_data.get("track_ids", [])
                    reasoning = response_data.get("reasoning", "")

                    # Structure checks
                    if not isinstance(track_ids, list):
                        print(f"❌ Response validation failed: track_ids is not a list")
                        raise ValueError("Response structure invalid: track_ids must be a list")

                    if not isinstance(reasoning, str):
                        print(f"❌ Response validation failed: reasoning is not a string")
                        raise ValueError("Response structure invalid: reasoning must be a string")

                    # INDEX-BASED: Validate all track IDs are integers (indices)
                    if not all(isinstance(tid, int) for tid in track_ids):
                        print(f"❌ Response validation failed: not all track_ids are integers")
                        raise ValueError("Invalid track_ids format: all IDs must be integers (indices)")

                    returned_track_count = len(track_ids)

                    # Simplified validation - focus on response quality
                    # Check 1: AI returned some tracks
                    if returned_track_count == 0:
                        print(f"❌ AI returned no tracks - invalid response")
                        raise ValueError("AI response validation failed: No tracks returned")

                    # Check 2: Reasonable upper bound
                    max_reasonable = int(num_tracks * 1.5)  # Allow up to 1.5x requested for minor flexibility
                    if returned_track_count > max_reasonable:
                        print(f"❌ AI returned {returned_track_count} tracks, much more than requested {num_tracks}")
                        raise ValueError(f"AI response validation failed: Too many tracks returned ({returned_track_count} vs requested {num_tracks})")

                    # Check 3: Validate tracks are within source bounds
                    if returned_track_count > source_track_count:
                        print(f"❌ AI returned {returned_track_count} tracks but we only provided {source_track_count}")
                        raise ValueError(f"AI response validation failed: More tracks returned than provided")

                    print(f"✅ AI returned {returned_track_count} tracks (requested: {num_tracks}), validation passed")

                    # INDEX-BASED: Map indices back to actual track IDs
                    # Find which indices are invalid (out of range)
                    invalid_indices = [idx for idx in track_ids if idx < 0 or idx >= len(track_id_map)]
                    if invalid_indices:
                        print(f"❌ AI returned {len(invalid_indices)} invalid indices out of {len(track_ids)}")

                    # Map valid indices to actual track IDs
                    valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
                    mapped_track_ids = [track_id_map[idx] for idx in valid_indices]

                    # Distribute by artist: cap per-artist count and interleave
                    # so no two consecutive tracks share the same artist.
                    id_to_artist = {t["id"]: t.get("artist", "Unknown") for t in shuffled_tracks}
                    mapped_track_ids = _distribute_by_artist(mapped_track_ids, id_to_artist, num_tracks)

                    final_selection = mapped_track_ids[:num_tracks]

                    if include_reasoning:
                        return final_selection, reasoning
                    else:
                        return final_selection

                # Handle simple array format (legacy)
                elif isinstance(response_data, list) and all(isinstance(tid, str) for tid in response_data):
                    valid_ids = {track["id"] for track in tracks_json}
                    filtered_ids = [tid for tid in response_data if tid in valid_ids]
                    id_to_artist = {t["id"]: t.get("artist", "Unknown") for t in shuffled_tracks}
                    filtered_ids = _distribute_by_artist(filtered_ids, id_to_artist, num_tracks)
                    final_selection = filtered_ids[:num_tracks]

                    if include_reasoning:
                        return final_selection, ""  # No reasoning available
                    else:
                        return final_selection
                else:
                    raise ValueError("Invalid response format: expected dict with track_ids or array of track IDs")

            except (json.JSONDecodeError, ValueError) as e:
                print(f"Failed to parse AI response: {e}")
                print(f"Response content: {content}")
                # Fall back to simple selection
                return self._fallback_genre_mix_selection(tracks_json, num_tracks, include_reasoning)

        except httpx.RequestError as e:
            print(f"🌐 Network error calling AI API: {e}")
            print(f"🔑 API Key present: {bool(self.api_key)}")
            print(f"🌐 Base URL: {self.base_url}")
            return self._fallback_genre_mix_selection(tracks_json, num_tracks, include_reasoning, f"Network error: {e}")
        except httpx.HTTPStatusError as e:
            response_text = e.response.text

            # Detect HTML error pages (like Cloudflare 502 errors) and truncate for logging
            if (response_text.strip().startswith('<!DOCTYPE html') or
                response_text.strip().startswith('<html') or
                len(response_text) > 500):

                # Truncate long responses for clean logging
                truncated_text = response_text[:200] + "..." if len(response_text) > 200 else response_text
                print(f"🚨 HTTP error from AI API: {e.response.status_code} - {truncated_text}")

                # User-friendly error for common infrastructure issues
                if e.response.status_code in [502, 503, 504]:
                    user_message = f"AI service temporarily unavailable (error {e.response.status_code}). Please try again in a minute."
                else:
                    user_message = f"AI service error (HTTP {e.response.status_code}). Please try again."
                return self._fallback_genre_mix_selection(tracks_json, num_tracks, include_reasoning, user_message)
            else:
                # Normal error response, log as before
                print(f"🚨 HTTP error from AI API: {e.response.status_code} - {response_text}")
                print(f"🔑 API Key present: {bool(self.api_key)}")
                print(f"🤖 Model: {self.model}")
                return self._fallback_genre_mix_selection(tracks_json, num_tracks, include_reasoning, f"HTTP {e.response.status_code}: {response_text}")
        except Exception as e:
            print(f"💥 Unexpected error in Genre Mix AI curation: {e}")
            import traceback
            print(f"📋 Traceback: {traceback.format_exc()}")
            return self._fallback_genre_mix_selection(tracks_json, num_tracks, include_reasoning, f"Unexpected error: {e}")

    def _fallback_genre_mix_selection(self, tracks_json: List[Dict[str, Any]], num_tracks: int, include_reasoning: bool = False, error_reason: str = "AI service was unavailable") -> Union[List[str], Tuple[List[str], str]]:
        """Fallback selection algorithm for genre mix when AI is unavailable"""
        # Sort by play count (highest first)
        sorted_tracks = sorted(
            tracks_json,
            key=lambda x: x.get("play_count", 0),
            reverse=True
        )
        # Take a larger pool first so distribution has variety to work with
        pool = sorted_tracks[:num_tracks * 3]
        id_to_artist = {t["id"]: t.get("artist", "Unknown") for t in pool}
        pool_ids = [t["id"] for t in pool]
        distributed = _distribute_by_artist(pool_ids, id_to_artist, num_tracks)
        track_ids = distributed[:num_tracks]

        if include_reasoning:
            reasoning = f"Fallback curation: Selected top {len(track_ids)} tracks sorted by play count (highest first). {error_reason}"
            return track_ids, reasoning
        else:
            return track_ids

    async def _curate_with_recipe(
        self,
        recipe_key: str,
        model_instructions: str,
        user_content: str,
        tracks_json: List[Dict[str, Any]],
        num_tracks: int,
        include_reasoning: bool,
        fallback_fn
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Shared AI call, parse, and index-map logic for all curate_* methods"""
        import random
        import re

        shuffled_tracks = tracks_json.copy()
        random.shuffle(shuffled_tracks)

        # Build index map
        track_id_map = []
        indexed_tracks = []
        for index, track in enumerate(shuffled_tracks):
            track_id_map.append(track["id"])
            indexed_tracks.append({
                "index": index,
                "track_name": track.get("title", "Unknown"),
                "artist": track.get("artist", "Unknown"),
                "album": track.get("album", "Unknown"),
                "year": track.get("year", 0),
                "play_count": track.get("play_count", 0),
                "local_library_likes": track.get("local_library_likes", False),
            })

        # Substitute indexed tracks into user_content
        final_user_content = user_content.replace("__INDEXED_TRACKS__", json.dumps(indexed_tracks, separators=(',', ':'), ensure_ascii=False))

        try:
            recipe = recipe_manager.get_recipe(recipe_key)
            llm_config = recipe.get("llm_config", {})
            model = self.model or "openai/gpt-3.5-turbo"
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 16000)

            print(f"🤖 {recipe_key}: sending {len(indexed_tracks)} tracks to AI")

            content = await self.provider.generate(
                system_prompt=model_instructions,
                user_prompt=final_user_content,
                max_tokens=max_tokens,
                temperature=temperature
            )

            print(f"🤖 FULL RAW AI RESPONSE for {recipe_key}: {content[:500]}")

            # Parse response
            cleaned = content.strip()
            for fence in ("```json", "```"):
                if cleaned.startswith(fence):
                    cleaned = cleaned[len(fence):]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            json_match = re.search(r'\{.*?"track_ids".*?\}', cleaned, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
            else:
                json_str = cleaned

            # Clean JSON
            lines = json_str.split('\n')
            cleaned_lines = []
            for line in lines:
                if '//' in line and 'http://' not in line and 'https://' not in line:
                    line = line[:line.find('//')].rstrip()
                line = re.sub(r',(\s*[\]}])', r'\1', line)
                if line.strip():
                    cleaned_lines.append(line)
            final_json = '\n'.join(cleaned_lines).strip()

            response_data = json.loads(final_json)

            if isinstance(response_data, dict) and "track_ids" in response_data:
                track_ids = response_data.get("track_ids", [])
                reasoning = response_data.get("reasoning", "")

                if not isinstance(track_ids, list):
                    raise ValueError("track_ids must be a list")
                if not all(isinstance(tid, int) for tid in track_ids):
                    raise ValueError("all track_ids must be integers (indices)")
                if len(track_ids) == 0:
                    raise ValueError("AI returned no tracks")
                if len(track_ids) > int(num_tracks * 1.5):
                    raise ValueError(f"AI returned too many tracks: {len(track_ids)}")

                valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
                mapped_ids = [track_id_map[idx] for idx in valid_indices]

                # Distribute by artist: cap per-artist count and interleave
                id_to_artist = {t["id"]: t.get("artist", "Unknown") for t in shuffled_tracks}
                mapped_ids = _distribute_by_artist(mapped_ids, id_to_artist, num_tracks)

                final_selection = mapped_ids[:num_tracks]

                print(f"✅ {recipe_key}: {len(final_selection)} tracks curated")

                if include_reasoning:
                    return final_selection, reasoning
                else:
                    return final_selection
            else:
                raise ValueError("Response missing track_ids")

        except (json.JSONDecodeError, ValueError) as e:
            print(f"❌ {recipe_key}: parse error: {e}")
            return fallback_fn(tracks_json, num_tracks, include_reasoning)
        except Exception as e:
            import traceback
            print(f"💥 {recipe_key}: unexpected error: {e}\n{traceback.format_exc()}")
            return fallback_fn(tracks_json, num_tracks, include_reasoning)

    async def curate_multi_artist_radio(
        self,
        artist_names: List[str],
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 30,
        include_reasoning: bool = True,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Multi-Artist Radio Blend playlist"""
        if not self.api_key and self.provider.provider_type == "openrouter":
            sorted_tracks = sorted(tracks_json, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = sorted_tracks[:num_tracks * 3]
            id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            distributed = _distribute_by_artist([t["id"] for t in pool], id_to_artist, num_tracks)
            reasoning = f"Fallback curation: Selected top {len(distributed)} tracks sorted by play count (highest first). No AI API key configured."
            return (distributed, reasoning) if include_reasoning else distributed

        recipe = recipe_manager.get_recipe("multi_artist_radio")
        artist_names_str = ", ".join(artist_names)
        model_instructions = (
            recipe.get("model_instructions", "")
            .replace("{{ARTIST_NAMES}}", artist_names_str)
            .replace("{{DESIRED_TRACK_COUNT}}", str(num_tracks))
        )
        if variety_context:
            model_instructions += f"\n\n{variety_context}"

        user_content = f'Select {num_tracks} tracks for a radio blend of {artist_names_str}.\n\nTracks: __INDEXED_TRACKS__\n\nReturn JSON: {{"track_ids": [indices], "reasoning": "summary"}}'

        def fallback(tracks, n, inc_r):
            s = sorted(tracks, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = s[:n * 3]
            id_to_art = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            ids = _distribute_by_artist([t["id"] for t in pool], id_to_art, n)
            r = f"Fallback curation: Selected top {len(ids)} tracks sorted by play count (highest first)."
            return (ids, r) if inc_r else ids

        return await self._curate_with_recipe("multi_artist_radio", model_instructions, user_content, tracks_json, num_tracks, include_reasoning, fallback)

    async def curate_multi_genre_mix(
        self,
        genre_names: List[str],
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 30,
        include_reasoning: bool = True,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Multi-Genre Mix playlist"""
        if not self.api_key and self.provider.provider_type == "openrouter":
            sorted_tracks = sorted(tracks_json, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = sorted_tracks[:num_tracks * 3]
            id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            distributed = _distribute_by_artist([t["id"] for t in pool], id_to_artist, num_tracks)
            reasoning = f"Fallback curation: Selected top {len(distributed)} tracks sorted by play count (highest first). No AI API key configured."
            return (distributed, reasoning) if include_reasoning else distributed

        recipe = recipe_manager.get_recipe("multi_genre_mix")
        genre_names_str = ", ".join(genre_names)
        model_instructions = (
            recipe.get("model_instructions", "")
            .replace("{{GENRE_NAMES}}", genre_names_str)
            .replace("{{DESIRED_TRACK_COUNT}}", str(num_tracks))
        )
        if variety_context:
            model_instructions += f"\n\n{variety_context}"

        user_content = f'Select {num_tracks} tracks for a multi-genre mix of {genre_names_str}.\n\nTracks: __INDEXED_TRACKS__\n\nReturn JSON: {{"track_ids": [indices], "reasoning": "summary"}}'

        def fallback(tracks, n, inc_r):
            s = sorted(tracks, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = s[:n * 3]
            id_to_art = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            ids = _distribute_by_artist([t["id"] for t in pool], id_to_art, n)
            r = f"Fallback curation: Selected top {len(ids)} tracks sorted by play count (highest first)."
            return (ids, r) if inc_r else ids

        return await self._curate_with_recipe("multi_genre_mix", model_instructions, user_content, tracks_json, num_tracks, include_reasoning, fallback)

    async def curate_decade_discovery(
        self,
        decades: List[str],
        mode: str,
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 30,
        include_reasoning: bool = True,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Decade & Discovery playlist"""
        if not self.api_key and self.provider.provider_type == "openrouter":
            rev = (mode != "Discovery")
            sorted_tracks = sorted(tracks_json, key=lambda x: x.get("play_count", 0), reverse=rev)
            pool = sorted_tracks[:num_tracks * 3]
            id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            distributed = _distribute_by_artist([t["id"] for t in pool], id_to_artist, num_tracks)
            reasoning = f"Fallback curation: Selected top {len(distributed)} tracks. No AI API key configured."
            return (distributed, reasoning) if include_reasoning else distributed

        recipe = recipe_manager.get_recipe("decade_discovery")
        decades_str = ", ".join(decades)
        model_instructions = (
            recipe.get("model_instructions", "")
            .replace("{{DECADE_LABELS}}", decades_str)
            .replace("{{MODE}}", mode)
            .replace("{{DESIRED_TRACK_COUNT}}", str(num_tracks))
        )
        if variety_context:
            model_instructions += f"\n\n{variety_context}"

        user_content = f'Select {num_tracks} tracks for a {decades_str} decade playlist in {mode} mode.\n\nTracks: __INDEXED_TRACKS__\n\nReturn JSON: {{"track_ids": [indices], "reasoning": "summary"}}'

        def fallback(tracks, n, inc_r):
            rev = (mode != "Discovery")
            s = sorted(tracks, key=lambda x: x.get("play_count", 0), reverse=rev)
            pool = s[:n * 3]
            id_to_art = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            ids = _distribute_by_artist([t["id"] for t in pool], id_to_art, n)
            r = f"Fallback curation: Selected top {len(ids)} tracks sorted by play count (highest first)."
            return (ids, r) if inc_r else ids

        return await self._curate_with_recipe("decade_discovery", model_instructions, user_content, tracks_json, num_tracks, include_reasoning, fallback)

    async def curate_sonic_journey(
        self,
        start_artist: str,
        end_artist: str,
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 30,
        include_reasoning: bool = True,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Sonic Journey playlist from start_artist to end_artist"""
        if not self.api_key and self.provider.provider_type == "openrouter":
            sorted_tracks = sorted(tracks_json, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = sorted_tracks[:num_tracks * 3]
            id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            distributed = _distribute_by_artist([t["id"] for t in pool], id_to_artist, num_tracks)
            reasoning = f"Fallback curation: Selected top {len(distributed)} tracks. No AI API key configured."
            return (distributed, reasoning) if include_reasoning else distributed

        recipe = recipe_manager.get_recipe("sonic_journey")
        model_instructions = (
            recipe.get("model_instructions", "")
            .replace("{{START_ARTIST}}", start_artist)
            .replace("{{END_ARTIST}}", end_artist)
            .replace("{{DESIRED_TRACK_COUNT}}", str(num_tracks))
        )
        if variety_context:
            model_instructions += f"\n\n{variety_context}"

        user_content = f'Select {num_tracks} tracks for a sonic journey from {start_artist} to {end_artist}.\n\nTracks: __INDEXED_TRACKS__\n\nReturn JSON: {{"track_ids": [indices], "reasoning": "summary"}}'

        def fallback(tracks, n, inc_r):
            s = sorted(tracks, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = s[:n * 3]
            id_to_art = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            ids = _distribute_by_artist([t["id"] for t in pool], id_to_art, n)
            r = f"Fallback curation: Selected top {len(ids)} tracks sorted by play count (highest first)."
            return (ids, r) if inc_r else ids

        return await self._curate_with_recipe("sonic_journey", model_instructions, user_content, tracks_json, num_tracks, include_reasoning, fallback)

    async def curate_genre_archaeology(
        self,
        genre: str,
        dig_depth: str,
        tracks_json: List[Dict[str, Any]],
        num_tracks: int = 30,
        include_reasoning: bool = True,
        variety_context: Optional[str] = None
    ) -> Union[List[str], Tuple[List[str], str]]:
        """Curate a Genre Archaeology playlist"""
        if not self.api_key and self.provider.provider_type == "openrouter":
            if dig_depth == "Deep":
                sorted_tracks = sorted(tracks_json, key=lambda x: x.get("year", 0))
            else:
                sorted_tracks = sorted(tracks_json, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = sorted_tracks[:num_tracks * 3]
            id_to_artist = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            distributed = _distribute_by_artist([t["id"] for t in pool], id_to_artist, num_tracks)
            reasoning = f"Fallback curation: Selected top {len(distributed)} tracks. No AI API key configured."
            return (distributed, reasoning) if include_reasoning else distributed

        recipe = recipe_manager.get_recipe("genre_archaeology")
        model_instructions = (
            recipe.get("model_instructions", "")
            .replace("{{TARGET_GENRE}}", genre)
            .replace("{{DIG_DEPTH}}", dig_depth)
            .replace("{{DESIRED_TRACK_COUNT}}", str(num_tracks))
        )
        if variety_context:
            model_instructions += f"\n\n{variety_context}"

        user_content = f'Select {num_tracks} tracks for a {dig_depth} genre archaeology of {genre}.\n\nTracks: __INDEXED_TRACKS__\n\nReturn JSON: {{"track_ids": [indices], "reasoning": "summary"}}'

        def fallback(tracks, n, inc_r):
            if dig_depth == "Deep":
                s = sorted(tracks, key=lambda x: x.get("year", 0))
            else:
                s = sorted(tracks, key=lambda x: x.get("play_count", 0), reverse=True)
            pool = s[:n * 3]
            id_to_art = {t["id"]: t.get("artist") or "Unknown" for t in pool}
            ids = _distribute_by_artist([t["id"] for t in pool], id_to_art, n)
            r = f"Fallback curation: Selected top {len(ids)} tracks sorted by play count (highest first)."
            return (ids, r) if inc_r else ids

        return await self._curate_with_recipe("genre_archaeology", model_instructions, user_content, tracks_json, num_tracks, include_reasoning, fallback)

    async def close(self):
        """Close the HTTP client"""
        try:
            if hasattr(self, 'provider') and self.provider:
                await self.provider.close()
        except Exception as e:
            print(f"Warning: Error closing AI provider: {e}")