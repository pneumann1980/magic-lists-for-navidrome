"""
Smart Track Scoring & Filtering for "This Is" Playlists

Optimizes payload size for LLM compatibility and token cost efficiency by intelligently 
scoring and filtering source tracks based on user listening behavior.
"""

import random
from datetime import datetime
from typing import List, Dict, Tuple, Any


def score_tracks_by_user_engagement(tracks: List[Dict], library_stats: Dict) -> List[Tuple[float, Dict]]:
    """
    Score tracks based on user's listening behavior.
    Returns list of (score, track) tuples sorted by score descending.
    
    Args:
        tracks: List of track objects to score
        library_stats: Dict containing user's library statistics:
            - max_play_count: Highest play count in library
            - max_playlist_appearances: Most appearances any track has
            
    Returns:
        List of (score, track) tuples, sorted descending by score
    """
    scored_tracks = []
    
    # Initialize counters for detailed logging
    engagement_stats = {
        'total_tracks': len(tracks),
        'loved_tracks': 0,
        'rated_tracks': 0,
        'tracks_with_plays': 0,
        'tracks_in_playlists': 0,
        'recent_tracks': 0,
        'total_play_count': 0,
        'total_playlist_appearances': 0,
        'max_score': 0,
        'min_score': float('inf'),
        'avg_score': 0
    }
    
    total_score = 0
    
    for track in tracks:
        score = 0.0
        track_breakdown = {}  # For detailed per-track logging if needed
        
        # Play count (normalize to 0-100 scale)
        play_count = track.get('play_count', 0)
        if play_count > 0:
            engagement_stats['tracks_with_plays'] += 1
            engagement_stats['total_play_count'] += play_count
            
        if library_stats.get('max_play_count', 0) > 0:
            normalized_plays = (play_count / library_stats['max_play_count']) * 100
            score += normalized_plays
            track_breakdown['play_score'] = normalized_plays
        
        # Loved/hearted tracks (high value binary signal).
        # Navidrome returns this as 'local_library_likes' (from starred), 'loved', or 'favorited'.
        if track.get('loved', False) or track.get('favorited', False) or track.get('local_library_likes', False):
            score += 50
            engagement_stats['loved_tracks'] += 1
            track_breakdown['loved_bonus'] = 50
        
        # Star ratings (0-5 scale, normalize to 0-50)
        rating = track.get('rating', 0)
        if rating > 0:
            engagement_stats['rated_tracks'] += 1
            score += rating * 10
            track_breakdown['rating_score'] = rating * 10
        
        # Playlist appearances (cap at 50 to avoid over-weighting)
        playlist_count = track.get('playlist_appearances', 0)
        if playlist_count > 0:
            engagement_stats['tracks_in_playlists'] += 1
            engagement_stats['total_playlist_appearances'] += playlist_count
            
        playlist_score = min(playlist_count * 5, 50)
        score += playlist_score
        track_breakdown['playlist_score'] = playlist_score
        
        # Optional: Recency bonus (tracks played in last 30 days)
        # Only include if last_played data is available
        if track.get('last_played'):
            try:
                # Handle both string and datetime objects
                if isinstance(track['last_played'], str):
                    last_played_date = datetime.fromisoformat(track['last_played'].replace('Z', '+00:00'))
                else:
                    last_played_date = track['last_played']
                
                days_since = (datetime.now() - last_played_date.replace(tzinfo=None)).days
                if days_since <= 30:
                    recency_bonus = max(0, 30 - days_since)
                    score += recency_bonus
                    engagement_stats['recent_tracks'] += 1
                    track_breakdown['recency_bonus'] = recency_bonus
            except (ValueError, TypeError):
                # Skip recency bonus if date parsing fails
                pass
        
        # Random jitter: ensures candidate pool varies between refreshes.
        # Tracks with very high engagement scores still tend to be included,
        # but marginal tracks rotate in/out, preventing stale repetition.
        score += random.uniform(0, 45)

        scored_tracks.append((score, track))

        # Update score statistics
        total_score += score
        engagement_stats['max_score'] = max(engagement_stats['max_score'], score)
        engagement_stats['min_score'] = min(engagement_stats['min_score'], score)
    
    # Calculate average score
    engagement_stats['avg_score'] = total_score / len(tracks) if tracks else 0
    if engagement_stats['min_score'] == float('inf'):
        engagement_stats['min_score'] = 0
    
    # Sort by score descending
    scored_tracks.sort(reverse=True, key=lambda x: x[0])
    
    # Log detailed engagement statistics
    print(f"🎯 SCORING ANALYSIS:")
    print(f"   📊 Sourced {engagement_stats['total_tracks']} tracks for analysis")
    print(f"   ❤️  Found {engagement_stats['loved_tracks']} loved/favorited tracks")
    print(f"   ⭐ Found {engagement_stats['rated_tracks']} rated tracks")
    print(f"   🎵 Found {engagement_stats['tracks_with_plays']} tracks with play counts (total: {engagement_stats['total_play_count']} plays)")
    print(f"   📋 Found {engagement_stats['tracks_in_playlists']} tracks in playlists (total: {engagement_stats['total_playlist_appearances']} appearances)")
    print(f"   🕐 Found {engagement_stats['recent_tracks']} recently played tracks (last 30 days)")
    print(f"   🏆 Score range: {engagement_stats['max_score']:.1f} - {engagement_stats['min_score']:.1f} (avg: {engagement_stats['avg_score']:.1f})")
    
    return scored_tracks


def calculate_filter_threshold(target_playlist_size: int) -> int:
    """
    Calculate optimal multiplier for filtering source tracks.
    
    Rationale: As playlist size increases, we can use a lower multiplier
    because probability of capturing high-quality tracks increases.
    
    Args:
        target_playlist_size: Desired number of tracks in final playlist
        
    Returns:
        int: Multiplier for filtering (e.g., 10 means keep 10x target size)
    """
    if target_playlist_size <= 25:
        return 10  # 25 tracks -> keep top 250
    elif target_playlist_size <= 50:
        return 8   # 50 tracks -> keep top 400
    elif target_playlist_size <= 100:
        return 6   # 100 tracks -> keep top 600
    else:
        # For larger playlists, use diminishing multiplier
        # Cap at 5x to balance quality and token efficiency
        return max(5, int(600 / target_playlist_size * 6))


def should_apply_smart_filtering(source_tracks: List[Dict], target_playlist_size: int) -> bool:
    """
    Determine if smart filtering should be applied based on track count and target size.
    
    Args:
        source_tracks: List of all available tracks for the artist
        target_playlist_size: Desired number of tracks in final playlist
        
    Returns:
        bool: True if filtering should be applied
    """
    threshold_multiplier = calculate_filter_threshold(target_playlist_size)
    threshold = target_playlist_size * threshold_multiplier
    
    return len(source_tracks) > threshold


def filter_tracks_by_engagement(
    tracks: List[Dict], 
    target_playlist_size: int, 
    library_stats: Dict
) -> List[Dict]:
    """
    Apply smart filtering to tracks if needed, returning filtered subset.
    
    Args:
        tracks: List of all available tracks
        target_playlist_size: Desired number of tracks in final playlist
        library_stats: Library statistics for scoring
        
    Returns:
        List[Dict]: Filtered tracks (or original if filtering not needed)
    """
    # Check if filtering is needed
    if not should_apply_smart_filtering(tracks, target_playlist_size):
        return tracks
    
    # Calculate how many tracks to keep
    threshold_multiplier = calculate_filter_threshold(target_playlist_size)
    max_tracks_to_keep = target_playlist_size * threshold_multiplier
    
    # Score and filter tracks
    scored_tracks = score_tracks_by_user_engagement(tracks, library_stats)
    
    # Return top-scored tracks up to the limit
    filtered_tracks = [track for score, track in scored_tracks[:max_tracks_to_keep]]
    
    return filtered_tracks


def filter_tracks_for_this_is_playlist(
    source_tracks: List[Dict], 
    target_playlist_size: int, 
    library_stats: Dict
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Filter source tracks for "This Is" playlists using engagement scoring.
    
    Args:
        source_tracks: Full list of tracks matching artist/criteria
        target_playlist_size: Desired final playlist length
        library_stats: User's library statistics for normalization
        
    Returns:
        tuple: (filtered_tracks, filter_metadata)
            - filtered_tracks: Subset of tracks to send to LLM
            - filter_metadata: Dict with info about filtering for logging/UI
    """
    threshold_multiplier = calculate_filter_threshold(target_playlist_size)
    threshold_count = target_playlist_size * threshold_multiplier
    
    # Only filter if source tracks exceed threshold
    if len(source_tracks) <= threshold_count:
        return source_tracks, {
            'filtered': False,
            'reason': 'below_threshold',
            'source_count': len(source_tracks),
            'sent_count': len(source_tracks)
        }
    
    # Score all tracks
    scored_tracks = score_tracks_by_user_engagement(source_tracks, library_stats)
    
    # Take top N scored tracks
    filtered_tracks = [track for score, track in scored_tracks[:threshold_count]]
    
    # Log filtering decision and final payload
    print(f"🎯 FILTERING DECISION:")
    print(f"   🎯 Threshold: {threshold_count} tracks (target: {target_playlist_size} × {threshold_multiplier}x multiplier)")
    print(f"   ✂️  Filtered {len(source_tracks)} → {len(filtered_tracks)} tracks for LLM payload")
    print(f"   📤 Payload reduction: {((len(source_tracks) - len(filtered_tracks)) / len(source_tracks) * 100):.1f}%")
    
    # Metadata for logging and user feedback
    filter_metadata = {
        'filtered': True,
        'source_count': len(source_tracks),
        'sent_count': len(filtered_tracks),
        'threshold_multiplier': threshold_multiplier,
        'score_range': {
            'highest': scored_tracks[0][0] if scored_tracks else 0,
            'lowest': scored_tracks[threshold_count-1][0] if len(scored_tracks) >= threshold_count else 0,
            'cutoff': scored_tracks[threshold_count][0] if len(scored_tracks) > threshold_count else 0
        }
    }
    
    return filtered_tracks, filter_metadata


def build_tiered_pool(
    source_tracks: List[Dict],
    pool_size: int,
    discovery_ratio: float,
    library_stats: Dict,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Build a candidate pool that explicitly mixes familiar and undiscovered tracks.

    Tiers (classified by play_count):
      • Hits        (A): play_count > median  — well-loved favourites
      • Familiar    (B): 3 ≤ play_count ≤ median — comfortable tracks
      • Discovery   (C): play_count < 3        — barely heard tracks

    ``discovery_ratio`` controls the share of Tier C in the pool.
    The remaining share is split 55 / 45 between Hits and Familiar.

    A per-artist cap of 10 % of pool_size prevents any single artist from
    dominating the candidate pool regardless of how many tracks they have.

    If a tier does not have enough tracks to fill its quota the shortfall is
    redistributed proportionally from the other tiers.

    Args:
        source_tracks:   All available tracks for the current context.
        pool_size:       Total number of candidates to return for the LLM.
        discovery_ratio: Share of pool that should be discovery tracks (0.0–0.75).
        library_stats:   Library statistics dict (used for engagement scoring).

    Returns:
        Tuple of (pool_tracks, metadata_dict).
    """
    import math as _math

    if not source_tracks:
        return [], {'tiered': False, 'reason': 'empty_source', 'source_count': 0, 'sent_count': 0}

    # ------------------------------------------------------------------
    # 1. Skip tiering when the source is too small to be worth splitting.
    # ------------------------------------------------------------------
    if len(source_tracks) <= pool_size:
        return source_tracks, {
            'tiered': False,
            'reason': 'below_threshold',
            'source_count': len(source_tracks),
            'sent_count': len(source_tracks),
        }

    # ------------------------------------------------------------------
    # 2. Classify tracks into tiers.
    # ------------------------------------------------------------------
    # Recompute max_play_count from the actual source tracks so we aren't
    # stuck with get_library_stats()'s rough estimate when it returns 0.
    actual_max = max((t.get('play_count', 0) for t in source_tracks), default=0)
    if actual_max > 0:
        library_stats = {**library_stats, 'max_play_count': actual_max}

    play_counts = sorted(t.get('play_count', 0) for t in source_tracks)
    median_idx = len(play_counts) // 2
    median_pc = play_counts[median_idx] if play_counts else 0

    tier_a: List[Dict] = []  # Hits
    tier_b: List[Dict] = []  # Familiar
    tier_c: List[Dict] = []  # Discovery

    for track in source_tracks:
        pc = track.get('play_count', 0)
        if pc < 3:
            tier_c.append(track)
        elif pc > median_pc:
            tier_a.append(track)
        else:
            tier_b.append(track)

    # ------------------------------------------------------------------
    # 3. Calculate per-tier quotas with overflow redistribution.
    # ------------------------------------------------------------------
    dr = max(0.0, min(0.75, discovery_ratio))
    n_c_want = int(pool_size * dr)
    n_a_want = int((pool_size - n_c_want) * 0.55)
    n_b_want = pool_size - n_c_want - n_a_want

    # Score tiers A and B by engagement (brings recency/liked signals in).
    def _score_tier(tier: List[Dict]) -> List[Dict]:
        scored = score_tracks_by_user_engagement(tier, library_stats)
        return [t for _, t in scored]

    tier_a_sorted = _score_tier(tier_a)
    tier_b_sorted = _score_tier(tier_b)
    random.shuffle(tier_c)  # Discovery tier: pure random, no popularity bias

    # Redistribute overflow from undersupplied tiers.
    n_c = min(n_c_want, len(tier_c))
    n_a = min(n_a_want, len(tier_a_sorted))
    n_b = min(n_b_want, len(tier_b_sorted))

    shortfall = pool_size - (n_c + n_a + n_b)
    if shortfall > 0:
        # Fill from whichever tiers still have spare capacity.
        extra_a = len(tier_a_sorted) - n_a
        extra_b = len(tier_b_sorted) - n_b
        extra_c = len(tier_c) - n_c
        total_extra = extra_a + extra_b + extra_c
        if total_extra > 0:
            n_a += int(shortfall * extra_a / total_extra)
            n_b += int(shortfall * extra_b / total_extra)
            n_c += shortfall - (n_a - min(n_a_want, len(tier_a_sorted))) - (n_b - min(n_b_want, len(tier_b_sorted)))
            n_a = min(n_a, len(tier_a_sorted))
            n_b = min(n_b, len(tier_b_sorted))
            n_c = min(n_c, len(tier_c))

    # ------------------------------------------------------------------
    # 4. Apply per-artist cap within each tier (max 10 % of pool_size).
    # ------------------------------------------------------------------
    max_per_artist = max(1, _math.ceil(pool_size * 0.10))

    def _cap_artists(tracks: List[Dict], n: int) -> List[Dict]:
        counts: Dict[str, int] = {}
        result: List[Dict] = []
        for t in tracks:
            artist = t.get('artist') or 'Unknown'
            if counts.get(artist, 0) < max_per_artist:
                result.append(t)
                counts[artist] = counts.get(artist, 0) + 1
            if len(result) >= n:
                break
        return result

    hits_sample      = _cap_artists(tier_a_sorted, n_a)
    familiar_sample  = _cap_artists(tier_b_sorted, n_b)
    discovery_sample = _cap_artists(tier_c,        n_c)

    # ------------------------------------------------------------------
    # 5. Merge and shuffle so tiers are interleaved in the LLM payload.
    # ------------------------------------------------------------------
    pool = hits_sample + familiar_sample + discovery_sample
    random.shuffle(pool)

    actual_discovery_pct = round(len(discovery_sample) / len(pool) * 100) if pool else 0

    metadata = {
        'tiered': True,
        'source_count': len(source_tracks),
        'sent_count': len(pool),
        'discovery_ratio_requested': dr,
        'discovery_count': len(discovery_sample),
        'familiar_count': len(familiar_sample),
        'hits_count': len(hits_sample),
        'actual_discovery_pct': actual_discovery_pct,
    }
    return pool, metadata