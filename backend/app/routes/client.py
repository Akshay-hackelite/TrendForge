from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response, StreamingResponse

from app import schemas
from app.auth import get_current_user
from app.clients import (
    analyze_client_trends,
    collect_client_channel_titles,
    collect_client_video_titles,
    create_client,
    delete_client,
    get_client_content_plan,
    get_client_script_narration_text,
    map_client_content_plan,
    persist_client_profile_fields,
    refresh_client_topics,
    run_client_content_plan,
    run_client_content_script_refine,
    run_client_content_scripts,
    save_client_recommendations,
    set_active_client,
    sync_client_channels_from_creds,
    update_client,
    update_client_content_script,
)
from app.database import (
    fetch_content_video,
    fetch_user,
    hydrate_suggestions_from_content_videos,
    list_channels_meta,
    list_clients_for_user,
    list_tracker_script_placements,
    list_videos_for_channel,
    replace_content_plan,
    upsert_content_video,
)
from app.google_oauth import get_user_google_creds
from app.services.topics import generate_auto_topics, normalize_topics
from app.services.youtube_api import fetch_all_channels
from app.services.youtube_metadata import (
    generate_youtube_metadata,
    generate_youtube_thumbnail,
    generate_youtube_thumbnail_prompt,
    normalize_yt_language,
    refine_youtube_metadata,
    refine_youtube_thumbnail_prompt,
)
from app.clients import _require_client_bundle

router = APIRouter(tags=["client"])


def _client_to_summary(client: dict) -> schemas.ClientSummary:
    return schemas.ClientSummary(
        id=client["id"],
        name=client.get("name") or "Client",
        channel_count=int(
            client.get("channel_count")
            if client.get("channel_count") is not None
            else len(client.get("channels") or [])
        ),
        website_url=client.get("website_url"),
        specialty=client.get("specialty"),
        designation=client.get("designation"),
        description=client.get("description"),
        reference_youtube_channel=client.get("reference_youtube_channel"),
        ai_videos_started_from=client.get("ai_videos_started_from"),
        topics=[schemas.TopicItem(**t) for t in normalize_topics(client.get("topics"))],
    )


def _client_list_response(username: str) -> schemas.ClientListResponse:
    user = fetch_user(username) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(username)]
    return schemas.ClientListResponse(
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )


@router.post("/client.list", response_model=schemas.ClientListResponse)
def client_list(current_user: dict = Depends(get_current_user)):
    return _client_list_response(current_user["username"])


@router.post("/client.create", response_model=schemas.ClientListResponse, status_code=201)
def client_create(
    body: schemas.ClientCreateRequest,
    current_user: dict = Depends(get_current_user),
):
    create_client(current_user["username"], body.name)
    return _client_list_response(current_user["username"])


@router.post("/client.update", response_model=schemas.ClientListResponse)
def client_update(
    body: schemas.ClientUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    topics = [t.model_dump() for t in body.topics] if body.topics is not None else None
    update_client(
        current_user["username"],
        body.client_id,
        name=body.name,
        website_url=body.website_url,
        specialty=body.specialty,
        designation=body.designation,
        description=body.description,
        reference_youtube_channel=body.reference_youtube_channel,
        ai_videos_started_from=body.ai_videos_started_from,
        topics=topics,
    )
    return _client_list_response(current_user["username"])


@router.post("/client.scrape-profile", response_model=schemas.ClientScrapeResponse)
def client_scrape_profile(
    body: schemas.ClientScrapeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Deep-scrape the brand website, persist website/niche, suggest topics."""
    print(
        f"[topics:route] scrape-profile START client={body.client_id} "
        f"website={bool(body.website_url)} specialty={bool(body.specialty)} "
        f"ref_yt={bool(body.reference_youtube_channel)}",
        flush=True,
    )
    website_url = (body.website_url or "").strip() or None
    specialty = (body.specialty or "").strip() or None
    reference_youtube_channel = (
        (body.reference_youtube_channel or "").strip() or None
        if body.reference_youtube_channel is not None
        else None
    )

    # Always store profile fields from the form before scraping
    client = persist_client_profile_fields(
        current_user["username"],
        body.client_id,
        website_url=website_url if body.website_url is not None else None,
        specialty=specialty if body.specialty is not None else None,
        reference_youtube_channel=reference_youtube_channel,
    )

    website_url = (website_url or client.get("website_url") or "").strip()
    specialty = specialty or client.get("specialty")
    has_ref = bool((client.get("reference_youtube_channel") or "").strip())
    if (
        not website_url
        and not specialty
        and not collect_client_video_titles(client)
        and not has_ref
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Add a website URL, specialty, or reference YouTube channel before scraping topics.",
        )

    try:
        print("[topics:route] scrape-profile → generate_auto_topics …", flush=True)
        auto_topics, meta = generate_auto_topics(
            client_id=client.get("id"),
            client_name=client.get("name"),
            specialty=specialty,
            description=client.get("description"),
            website_url=website_url or None,
            video_titles=collect_client_video_titles(client),
            channel_titles=collect_client_channel_titles(client),
            manual_topics=[
                t for t in normalize_topics(client.get("topics")) if t.get("source") == "manual"
            ],
        )
    except ValueError as exc:
        print(f"[topics:route] scrape-profile 400: {exc}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    detected = meta.get("specialty") or specialty
    if detected and detected != client.get("specialty"):
        client = persist_client_profile_fields(
            current_user["username"],
            body.client_id,
            specialty=detected,
        )

    user = fetch_user(current_user["username"]) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(current_user["username"])]
    print(
        f"[topics:route] scrape-profile DONE suggested={len(auto_topics)} "
        f"generator={meta.get('generator')} error={meta.get('openai_error')}",
        flush=True,
    )
    return schemas.ClientScrapeResponse(
        specialty=client.get("specialty") or detected,
        website_url=client.get("website_url"),
        suggested_topics=[schemas.TopicItem(**t) for t in auto_topics],
        page_title=meta.get("page_title"),
        page_snippet=meta.get("page_snippet") or meta.get("openai_rationale"),
        pages_scraped=meta.get("pages_scraped") or 0,
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
        generator=meta.get("generator"),
        openai_rationale=meta.get("openai_rationale"),
        openai_error=meta.get("openai_error"),
    )


@router.post("/client.refresh-topics", response_model=schemas.ClientRefreshTopicsResponse)
def client_refresh_topics(
    body: schemas.ClientRefreshTopicsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Regenerate auto topics from website + specialty + YouTube history. Manual topics kept."""
    print(
        f"[topics:route] refresh-topics START client={body.client_id} "
        f"website={bool(body.website_url)} specialty={bool(body.specialty)} "
        f"ref_yt={bool(body.reference_youtube_channel)} "
        f"prompt={bool(body.user_prompt)}",
        flush=True,
    )
    current_topics = [t.model_dump() for t in body.topics] if body.topics is not None else None
    try:
        result = refresh_client_topics(
            current_user["username"],
            body.client_id,
            website_url=body.website_url,
            specialty=body.specialty,
            description=body.description,
            reference_youtube_channel=body.reference_youtube_channel,
            topics=current_topics,
            user_prompt=body.user_prompt,
        )
    except ValueError as exc:
        print(f"[topics:route] refresh-topics 400: {exc}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        print(f"[topics:route] refresh-topics ERROR {type(exc).__name__}: {exc}", flush=True)
        raise

    user = fetch_user(current_user["username"]) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(current_user["username"])]
    client = result["client"]
    meta = result.get("scrape_meta") or {}
    print(
        f"[topics:route] refresh-topics DONE topics={len(client.get('topics') or [])} "
        f"generator={meta.get('generator')} stages={meta.get('openai_stages')} "
        f"ref={meta.get('reference_youtube')}",
        flush=True,
    )
    return schemas.ClientRefreshTopicsResponse(
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
        topics=[schemas.TopicItem(**t) for t in normalize_topics(client.get("topics"))],
        specialty=client.get("specialty"),
        page_title=meta.get("page_title"),
        page_snippet=meta.get("page_snippet"),
        pages_scraped=meta.get("pages_scraped") or 0,
        generator=meta.get("generator"),
        openai_rationale=meta.get("openai_rationale"),
        openai_error=meta.get("openai_error"),
    )


@router.post("/client.analyze-trends", response_model=schemas.ClientAnalyzeTrendsResponse)
async def client_analyze_trends(
    body: schemas.ClientAnalyzeTrendsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Score topics with Google Search + YouTube Trends for India; persist on client."""
    print(
        f"[trends:route] POST /client.analyze-trends "
        f"user={current_user.get('username')!r} client_id={body.client_id!r} force={body.force}",
        flush=True,
    )
    try:
        result = await analyze_client_trends(
            current_user["username"],
            body.client_id,
            force=body.force,
        )
    except ValueError as exc:
        print(f"[trends:route] 400 {exc}", flush=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        print(f"[trends:route] ERROR {type(exc).__name__}: {exc}", flush=True)
        raise

    user = fetch_user(current_user["username"]) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(current_user["username"])]
    client = result["client"]
    summary = result.get("summary") or {}
    print(
        f"[trends:route] OK scored={summary.get('scored')} "
        f"tasks={summary.get('api_tasks')} cost=${float(summary.get('total_cost') or 0):.4f} "
        f"cached_skip={summary.get('skipped_cached')} error={summary.get('error')!r}",
        flush=True,
    )
    return schemas.ClientAnalyzeTrendsResponse(
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
        topics=[schemas.TopicItem(**t) for t in normalize_topics(client.get("topics"))],
        geo=summary.get("geo") or "IN",
        scored=summary.get("scored") or 0,
        insufficient_data=summary.get("insufficient_data") or 0,
        skipped_cached=summary.get("skipped_cached") or 0,
        fetched_at=summary.get("fetched_at"),
        error=summary.get("error"),
        api_tasks=summary.get("api_tasks") or 0,
        total_cost=float(summary.get("total_cost") or 0),
    )


@router.post(
    "/client.save-recommendations",
    response_model=schemas.ClientSaveRecommendationsResponse,
)
def client_save_recommendations(
    body: schemas.ClientSaveRecommendationsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Compute and persist combined recommendation scores on client topics."""
    try:
        result = save_client_recommendations(
            current_user["username"],
            body.client_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    user = fetch_user(current_user["username"]) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(current_user["username"])]
    client = result["client"]
    return schemas.ClientSaveRecommendationsResponse(
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
        topics=[schemas.TopicItem(**t) for t in normalize_topics(client.get("topics"))],
        primary_count=result.get("primary_count") or 0,
        secondary_count=result.get("secondary_count") or 0,
        saved_at=result.get("saved_at"),
        threshold=float(result.get("threshold") or 50),
    )


def _content_plan_response(username: str, result: dict) -> schemas.ClientContentPlanResponse:
    user = fetch_user(username) or {}
    clients = [_client_to_summary(c) for c in list_clients_for_user(username)]
    raw = result.get("suggestions") or {}
    client = result.get("client") or {}
    client_id = client.get("id")
    if client_id:
        raw = hydrate_suggestions_from_content_videos(client_id, raw)
    placements_by_item: dict[str, list] = {}
    if client_id:
        for placement in list_tracker_script_placements(client_id):
            placements_by_item.setdefault(placement["item_id"], []).append(placement)
    coverage = raw.get("coverage")
    items = []
    for item in raw.get("items") or []:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        title_en = (row.get("title_en") or "").strip()
        title_hi = (row.get("title_hinglish") or "").strip()
        legacy = (row.get("working_title") or "").strip()
        if not title_en:
            title_en = legacy or title_hi or row.get("topic_text") or ""
        if not title_hi:
            title_hi = legacy or title_en
        row["title_en"] = title_en
        row["title_hinglish"] = title_hi
        row["working_title"] = legacy or title_hi or title_en
        row["tracker_placements"] = placements_by_item.get(row.get("id") or "", [])
        items.append(schemas.ContentSuggestionItem(**row))

    analysis_items = []
    for row in raw.get("keyword_analysis") or []:
        if not isinstance(row, dict):
            continue
        analysis_items.append(
            schemas.ContentKeywordAnalysisItem(
                topic_id=row.get("topic_id") or "",
                topic_text=row.get("topic_text") or "",
                recommendation_score=float(row.get("recommendation_score") or 0),
                weight=row.get("weight") or "medium",
                covered_long=bool(row.get("covered_long")),
                covered_short=bool(row.get("covered_short")),
                pending_long=bool(row.get("pending_long", not row.get("covered_long"))),
                pending_short=bool(row.get("pending_short", not row.get("covered_short"))),
                long_videos=[
                    schemas.ContentKeywordVideoRef(**v)
                    for v in (row.get("long_videos") or [])
                    if isinstance(v, dict) and v.get("video_id")
                ],
                short_videos=[
                    schemas.ContentKeywordVideoRef(**v)
                    for v in (row.get("short_videos") or [])
                    if isinstance(v, dict) and v.get("video_id")
                ],
                yt_title=row.get("yt_title"),
                yt_description=row.get("yt_description"),
                yt_tags=row.get("yt_tags"),
                yt_thumbnail_url=row.get("yt_thumbnail_url"),
                yt_thumbnail_prompt=row.get("yt_thumbnail_prompt"),
                yt_locales=row.get("yt_locales") or None,
            )
        )

    return schemas.ClientContentPlanResponse(
        clients=clients,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
        suggestions=schemas.ContentSuggestionsPayload(
            generated_at=raw.get("generated_at"),
            mapped_at=raw.get("mapped_at"),
            scripts_generated_at=raw.get("scripts_generated_at"),
            count=int(raw.get("count") or 0),
            user_prompt=raw.get("user_prompt"),
            items=items,
            coverage=schemas.ContentCoverageSummary(**coverage) if coverage else None,
            keyword_analysis=analysis_items,
            recent_video_types=list(raw.get("recent_video_types") or []),
        ),
    )


@router.post("/client.content-plan.get", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_get(
    body: schemas.ClientContentPlanGetRequest,
    current_user: dict = Depends(get_current_user),
):
    result = get_client_content_plan(current_user["username"], body.client_id)
    return _content_plan_response(current_user["username"], result)


@router.post("/client.content-plan.map", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_map(
    body: schemas.ClientContentPlanMapRequest,
    current_user: dict = Depends(get_current_user),
):
    """1st call: map library videos → keywords and persist Long/Short analysis."""
    try:
        result = map_client_content_plan(
            current_user["username"],
            body.client_id,
            force=body.force,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _content_plan_response(current_user["username"], result)


@router.post("/client.content-plan.generate", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_generate(
    body: schemas.ClientContentPlanGenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    try:
        result = run_client_content_plan(
            current_user["username"],
            body.client_id,
            count=body.count,
            force_remap=body.force_remap,
            regenerate=False,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _content_plan_response(current_user["username"], result)


@router.post("/client.content-plan.regenerate", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_regenerate(
    body: schemas.ClientContentPlanRegenerateRequest,
    current_user: dict = Depends(get_current_user),
):
    prompt = (body.user_prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_prompt is required to regenerate.",
        )
    try:
        # Prefer previous count when not specified
        count = body.count
        if count is None:
            existing = get_client_content_plan(current_user["username"], body.client_id)
            count = int((existing.get("suggestions") or {}).get("count") or 5)
        result = run_client_content_plan(
            current_user["username"],
            body.client_id,
            count=count,
            force_remap=body.force_remap,
            user_prompt=prompt,
            regenerate=True,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _content_plan_response(current_user["username"], result)


@router.post(
    "/client.content-plan.generate-scripts",
    response_model=schemas.ClientContentPlanResponse,
)
def client_content_plan_generate_scripts(
    body: schemas.ClientContentPlanScriptsRequest,
    current_user: dict = Depends(get_current_user),
):
    """3rd call: generate spoken Hinglish scripts for all content-plan titles."""
    try:
        result = run_client_content_scripts(
            current_user["username"],
            body.client_id,
            example1=body.example1,
            example2=body.example2,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _content_plan_response(current_user["username"], result)


@router.post(
    "/client.content-plan.refine-script",
    response_model=schemas.ClientContentPlanResponse,
)
def client_content_plan_refine_script(
    body: schemas.ClientContentPlanRefineScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Refine one item's script with a user prompt (single-script AI call)."""
    prompt = (body.user_prompt or "").strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="user_prompt is required to refine a script.",
        )
    if not (body.item_id or "").strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="item_id is required.",
        )
    try:
        result = run_client_content_script_refine(
            current_user["username"],
            body.client_id,
            item_id=body.item_id,
            user_prompt=prompt,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return _content_plan_response(current_user["username"], result)


@router.post(
    "/client.content-plan.update-script",
    response_model=schemas.ClientContentPlanResponse,
)
def client_content_plan_update_script(
    body: schemas.ClientContentPlanUpdateScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Overwrite one item's script from tracker (no AI)."""
    if not (body.item_id or "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="item_id is required.")
    try:
        result = update_client_content_script(
            current_user["username"],
            body.client_id,
            item_id=body.item_id,
            script=body.script,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _content_plan_response(current_user["username"], result)


@router.post("/client.content-plan.narrate-script")
def client_content_plan_narrate_script(
    body: schemas.ClientContentPlanNarrateScriptRequest,
    current_user: dict = Depends(get_current_user),
):
    """Stream narration audio/mpeg as OpenAI synthesizes (chunked transfer).

    Cached scripts stream from disk immediately. Fresh TTS is piped through
    while the mp3 is saved for later replay (unless force=true).
    """
    from app.services.openai_content_plan import stream_narrate_script_audio

    try:
        text = get_client_script_narration_text(
            current_user["username"],
            body.client_id,
            item_id=body.item_id,
            combined=bool(body.combined),
        )
        # Peek first chunk so validation / cache-hit errors happen before headers
        stream = stream_narrate_script_audio(text=text, force=bool(body.force))
        first_chunk, from_cache = next(stream)
    except StopIteration as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Narration returned no audio.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Narration failed: {exc}",
        ) from exc

    def byte_iter():
        try:
            if first_chunk:
                yield first_chunk
            for chunk, _cached in stream:
                if chunk:
                    yield chunk
        except Exception as exc:
            print(f"[content-plan:tts] stream error mid-flight: {exc}", flush=True)
            raise

    headers = {
        "Content-Disposition": 'inline; filename="script-narration.mp3"',
        "Cache-Control": "private, max-age=86400" if from_cache else "no-store",
        "X-Narration-Cached": "1" if from_cache else "0",
        "X-Accel-Buffering": "no",
    }
    if from_cache and first_chunk:
        headers["Content-Length"] = str(len(first_chunk))

    return StreamingResponse(
        byte_iter(),
        media_type="audio/mpeg",
        headers=headers,
    )


def _locale_payload(metadata_res: dict, thumbnail_prompt: str, thumbnail_url: str | None) -> dict:
    locale = {}
    if metadata_res.get("yt_title"):
        locale["yt_title"] = metadata_res["yt_title"]
    if metadata_res.get("yt_description"):
        locale["yt_description"] = metadata_res["yt_description"]
    if metadata_res.get("yt_tags"):
        locale["yt_tags"] = metadata_res["yt_tags"]
    if thumbnail_prompt:
        locale["yt_thumbnail_prompt"] = thumbnail_prompt
    if thumbnail_url:
        locale["yt_thumbnail_url"] = thumbnail_url
    return locale


def _mirror_legacy_yt_fields(target: dict) -> None:
    locales = target.get("yt_locales") or {}
    preferred = locales.get("hinglish") if isinstance(locales, dict) else None
    if not preferred and isinstance(locales, dict):
        preferred = next((v for v in locales.values() if isinstance(v, dict) and v.get("yt_title")), None)
    if not isinstance(preferred, dict):
        return
    for key in ("yt_title", "yt_description", "yt_tags", "yt_thumbnail_url", "yt_thumbnail_prompt"):
        if preferred.get(key) is not None:
            target[key] = preferred[key]


def _apply_locale_metadata(target: dict, language: str, locale: dict) -> None:
    locales = dict(target.get("yt_locales") or {})
    previous = locales.get(language) if isinstance(locales.get(language), dict) else {}
    locales[language] = {**previous, **locale}
    target["yt_locales"] = locales
    _mirror_legacy_yt_fields(target)


@router.post("/client.content-plan-generate-metadata", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_generate_metadata(
    body: schemas.ClientContentPlanGenerateMetadataRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    
    client_id = body.client_id
    languages = []
    for raw in (body.languages or ["hinglish"]):
        lang = normalize_yt_language(raw)
        if lang not in languages:
            languages.append(lang)
    if not languages:
        raise HTTPException(status_code=400, detail="Select at least one language.")

    print(
        f"[yt-metadata] START generate client={client_id} items={body.item_ids} "
        f"languages={languages}",
        flush=True,
    )

    channel_id = user.get("active_channel_id")
    if not channel_id:
        linked = list_channels_meta(client_id)
        channel_id = linked[0]["id"] if linked else None
        print(
            f"[yt-metadata] no active channel; using {channel_id!r} for reference thumbs",
            flush=True,
        )
        
    client_bundle = _require_client_bundle(username, client_id, with_videos=False)
    client_summary = {
        "name": client_bundle.get("name", "N/A"),
        "specialty": client_bundle.get("specialty", "N/A"),
    }
    suggestions = client_bundle.get("content_suggestions", {})
    items = suggestions.get("items", [])
    
    # Get reference image URLs
    reference_image_urls = []
    if channel_id:
        videos = list_videos_for_channel(channel_id, client_id)
        videos = sorted(videos, key=lambda v: v.get("published_at", ""), reverse=True)
        if body.reference_video_ids:
            selected = [v for v in videos if v.get("id") in body.reference_video_ids]
            reference_image_urls = [v.get("thumbnail_url") for v in selected]
            reference_image_urls = [u for u in reference_image_urls if u][:3]
        else:
            reference_image_urls = [v.get("thumbnail_url") for v in videos]
            reference_image_urls = [u for u in reference_image_urls if u][:3]
        
    # Build a lookup from topic_id -> content plan item (for script reuse)
    topic_id_to_item = {}
    for item in items:
        tid = item.get("topic_id")
        if tid:
            topic_id_to_item[tid] = item

    keyword_analysis = suggestions.get("keyword_analysis", [])

    def _persist_locale(topic_id, locale, language, *, topic_text, source, item_id):
        if not topic_id:
            return
        upsert_content_video(
            client_id,
            topic_id,
            topic_text=topic_text or "",
            source=source,
            content_plan_item_id=item_id,
            locales={language: locale},
            replace_locales=True,
        )

    def _script_title_for(topic):
        if not isinstance(topic, dict):
            return ""
        return (
            str(topic.get("title_hinglish") or "").strip()
            or str(topic.get("working_title") or "").strip()
            or str(topic.get("title_en") or "").strip()
        )

    def _generate_locale(topic, script, language):
        metadata_res = generate_youtube_metadata(
            client_summary=client_summary,
            topic=topic,
            script=script,
            user_prompt=body.user_prompt,
            language=language,
            script_title=_script_title_for(topic) if script else None,
        )
        thumbnail_prompt = generate_youtube_thumbnail_prompt(
            client_summary=client_summary,
            topic=topic,
            script=script,
            user_prompt=body.user_prompt,
            reference_image_urls=reference_image_urls,
            language=language,
        )
        thumbnail_url = None
        if thumbnail_prompt:
            try:
                thumbnail_url = generate_youtube_thumbnail(thumbnail_prompt)
            except Exception as e:
                print(f"Failed to generate thumbnail for language={language}: {e}")
        return _locale_payload(metadata_res, thumbnail_prompt, thumbnail_url)

    # Track which topic_ids we've already processed to avoid duplicate generation
    processed_topic_ids = set()

    # --- Pass 1: Content Plan items (From Script) ---
    for item in items:
        if item.get("id") in body.item_ids:
            topic_id = item.get("topic_id")
            processed_topic_ids.add(topic_id)
            source = "script" if item.get("script") else "manual"
            topic_text = item.get("topic") or item.get("topic_text") or item.get("working_title") or ""
            for language in languages:
                try:
                    locale = _generate_locale(item, item.get("script"), language)
                except Exception as exc:  # noqa: BLE001
                    print(
                        f"[yt-metadata] failed language={language} item={item.get('id')}: {exc}",
                        flush=True,
                    )
                    continue
                _persist_locale(
                    topic_id,
                    locale,
                    language,
                    topic_text=topic_text,
                    source=source,
                    item_id=item.get("id"),
                )

    # --- Pass 2: Keyword Analysis items (Manual Pick) ---
    str_item_ids = [str(x) for x in body.item_ids]
    for kw in keyword_analysis:
        if not isinstance(kw, dict):
            continue
        kw_topic_id = str(kw.get("topic_id"))
        if kw_topic_id not in str_item_ids:
            continue
        # Skip if already processed via content plan item
        if kw.get("topic_id") in processed_topic_ids:
            continue

        matching_item = topic_id_to_item.get(kw.get("topic_id"))
        script_to_use = matching_item.get("script") if matching_item else None
        topic_for_prompt = matching_item if matching_item else {"topic_text": kw.get("topic_text")}
        source = "script" if script_to_use else "manual"
        item_id = matching_item.get("id") if matching_item else None
        topic_text = (
            (matching_item.get("topic") if matching_item else None)
            or kw.get("topic_text")
            or ""
        )

        for language in languages:
            try:
                locale = _generate_locale(topic_for_prompt, script_to_use, language)
            except Exception as exc:  # noqa: BLE001
                print(
                    f"[yt-metadata] failed language={language} topic={kw.get('topic_id')}: {exc}",
                    flush=True,
                )
                continue
            _persist_locale(
                kw.get("topic_id"),
                locale,
                language,
                topic_text=topic_text,
                source=source,
                item_id=item_id,
            )
                    
    client_bundle["content_suggestions"] = suggestions
    replace_content_plan(client_id, client_bundle)
    return client_content_plan_get(schemas.ClientContentPlanGetRequest(client_id=client_id), current_user=current_user)


@router.post("/client.content-plan-refine-metadata", response_model=schemas.ClientContentPlanResponse)
def client_content_plan_refine_metadata(
    body: schemas.ClientContentPlanRefineMetadataRequest,
    current_user: dict = Depends(get_current_user),
):
    username = current_user["username"]
    user = fetch_user(username)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
        
    client_id = body.client_id
    channel_id = user.get("active_channel_id")
    
    client_bundle = _require_client_bundle(username, client_id, with_videos=False)
    suggestions = client_bundle.get("content_suggestions", {})
    items = suggestions.get("items", [])
    keyword_analysis = suggestions.get("keyword_analysis", [])
    
    # Try to find the target in content plan items first, then keyword_analysis
    target_item = next((i for i in items if i.get("id") == body.item_id), None)
    target_kw = None
    if not target_item:
        # Search keyword_analysis by topic_id
        target_kw = next((k for k in keyword_analysis if isinstance(k, dict) and str(k.get("topic_id")) == str(body.item_id)), None)
    
    if not target_item and not target_kw:
        raise HTTPException(status_code=404, detail="Topic item not found")
    
    target = target_item or target_kw
    language = normalize_yt_language(body.language or "hinglish")
    topic_id = target.get("topic_id")
    matching_item = target_item or next((i for i in items if i.get("topic_id") == topic_id), None)
    matching_kw = target_kw or next((k for k in keyword_analysis if isinstance(k, dict) and k.get("topic_id") == topic_id), None)
    source = "script" if matching_item and matching_item.get("script") else "manual"
    topic_text = (
        (matching_item.get("topic") if matching_item else None)
        or (matching_item.get("topic_text") if matching_item else None)
        or (matching_kw.get("topic_text") if matching_kw else None)
        or ""
    )
    package = fetch_content_video(client_id, topic_id) if topic_id else None
        
    # Get reference image URLs
    reference_image_urls = []
    if channel_id and body.reference_video_ids:
        videos = list_videos_for_channel(channel_id, client_id)
        selected = [v for v in videos if v.get("id") in body.reference_video_ids]
        reference_image_urls = [v.get("thumbnail_url") for v in selected]
        reference_image_urls = [u for u in reference_image_urls if u][:3]

    locales = dict((package or {}).get("yt_locales") or target.get("yt_locales") or {})
    current_locale = locales.get(language) if isinstance(locales.get(language), dict) else {}
    if not current_locale and language == "hinglish":
        current_locale = {
            "yt_title": target.get("yt_title"),
            "yt_description": target.get("yt_description"),
            "yt_tags": target.get("yt_tags"),
            "yt_thumbnail_prompt": target.get("yt_thumbnail_prompt"),
            "yt_thumbnail_url": target.get("yt_thumbnail_url"),
        }
        
    current_meta = {
        "yt_title": current_locale.get("yt_title"),
        "yt_description": current_locale.get("yt_description"),
        "yt_tags": current_locale.get("yt_tags"),
    }
    
    metadata_res = refine_youtube_metadata(
        current_metadata=current_meta,
        user_prompt=body.user_prompt,
        language=language,
    )
    
    current_thumbnail_prompt = current_locale.get("yt_thumbnail_prompt") or ""
    thumbnail_prompt = refine_youtube_thumbnail_prompt(
        current_thumbnail_prompt=current_thumbnail_prompt,
        user_prompt=body.user_prompt,
        language=language,
    )
    
    locale = _locale_payload(metadata_res, thumbnail_prompt, None)
    if thumbnail_prompt and thumbnail_prompt != current_thumbnail_prompt:
        try:
            locale["yt_thumbnail_url"] = generate_youtube_thumbnail(thumbnail_prompt)
        except Exception as e:
            print(f"Failed to generate thumbnail during refine: {e}")
    elif current_locale.get("yt_thumbnail_url"):
        locale["yt_thumbnail_url"] = current_locale.get("yt_thumbnail_url")

    if topic_id:
        upsert_content_video(
            client_id,
            topic_id,
            topic_text=topic_text,
            source=source,
            content_plan_item_id=(matching_item or {}).get("id") if matching_item else None,
            locales={language: locale},
            replace_locales=True,
        )
            
    client_bundle["content_suggestions"] = suggestions
    replace_content_plan(client_id, client_bundle)
    return client_content_plan_get(schemas.ClientContentPlanGetRequest(client_id=client_id), current_user=current_user)


@router.post("/client.select", response_model=schemas.ClientListResponse)
def client_select(
    body: schemas.ClientSelectRequest,
    current_user: dict = Depends(get_current_user),
):
    set_active_client(current_user["username"], body.client_id)
    return _client_list_response(current_user["username"])


@router.post("/client.sync-channels", response_model=schemas.YouTubeChannelListResponse)
def client_sync_channels(
    body: schemas.ClientSyncChannelsRequest,
    current_user: dict = Depends(get_current_user),
):
    """Re-discover YouTube channels using a linked channel's Google credentials."""
    username = current_user["username"]
    target_client_id = body.client_id
    source_channel_id = body.channel_id

    creds = get_user_google_creds(username, target_client_id, source_channel_id)
    channel_infos = fetch_all_channels(creds)
    sync_client_channels_from_creds(
        username, target_client_id, source_channel_id, channel_infos
    )

    user = fetch_user(username) or {}
    channels = [
        schemas.YouTubeChannelInfo(
            id=c["id"],
            title=c.get("title", ""),
            description=c.get("description", ""),
            custom_url=c.get("custom_url"),
            published_at=c.get("published_at") or "",
            view_count=c.get("view_count", 0),
            subscriber_count=c.get("subscriber_count", 0),
            video_count=c.get("video_count", 0),
            language=c.get("language"),
        )
        for c in list_channels_meta(target_client_id)
    ]
    return schemas.YouTubeChannelListResponse(
        channels=channels,
        active_client_id=user.get("active_client_id"),
        active_channel_id=user.get("active_channel_id"),
    )


@router.post("/client.delete", response_model=schemas.ClientListResponse)
def client_delete(
    body: schemas.ClientDeleteRequest,
    current_user: dict = Depends(get_current_user),
):
    delete_client(current_user["username"], body.client_id)
    return _client_list_response(current_user["username"])
