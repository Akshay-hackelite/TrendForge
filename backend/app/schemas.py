from datetime import date
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# Local Authentication Schemas
class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    password: str


class TopicItem(BaseModel):
    id: str
    text: str
    weight: str = "medium"  # high | medium | low
    source: str = "manual"  # manual | auto
    # Optional Google Trends (India) scores — filled by /client.analyze-trends
    trend_score: Optional[float] = None
    trend_confidence: Optional[str] = None  # high | medium | low
    trend_geo: Optional[str] = None  # e.g. IN
    web_interest: Optional[float] = None
    youtube_interest: Optional[float] = None
    momentum: Optional[float] = None
    rising_flag: Optional[int] = None  # 0 none | 1 rising | 2 breakout
    trend_fetched_at: Optional[str] = None
    # Combined recommendation — filled by /client.save-recommendations
    recommendation_score: Optional[float] = None
    priority_points: Optional[float] = None
    trend_points: Optional[float] = None
    recommendation_saved_at: Optional[str] = None


class ClientSummary(BaseModel):
    id: str
    name: str
    channel_count: int = 0
    website_url: Optional[str] = None
    specialty: Optional[str] = None
    designation: Optional[str] = None
    description: Optional[str] = None
    # Public channel URL/@handle for keyword planning (no OAuth)
    reference_youtube_channel: Optional[str] = None
    # YYYY-MM — videos published on/after this month count as AI/new
    ai_videos_started_from: Optional[str] = None
    topics: List[TopicItem] = []


class ChannelSummary(BaseModel):
    id: str
    title: str


class UserResponse(UserBase):
    is_active: bool
    has_clients: bool
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    clients: List[ClientSummary] = []
    channels: List[ChannelSummary] = []


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None


# Admin dashboard schemas (gated by hardcoded admin password)
class AdminAuthRequest(BaseModel):
    admin_password: str


class AdminUserSummary(BaseModel):
    username: str
    is_active: bool
    client_count: int = 0
    channel_count: int = 0


class AdminUserListResponse(BaseModel):
    users: List[AdminUserSummary]


class AdminUserCreateRequest(BaseModel):
    admin_password: str
    username: str
    password: str


class AdminUserDeleteRequest(BaseModel):
    admin_password: str
    username: str


class AdminUserResetPasswordRequest(BaseModel):
    admin_password: str
    username: str
    password: str


class AdminUserSetActiveRequest(BaseModel):
    admin_password: str
    username: str
    is_active: bool


# Client Schemas
class ClientListResponse(BaseModel):
    clients: List[ClientSummary]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None


class ClientCreateRequest(BaseModel):
    name: str


class ClientUpdateRequest(BaseModel):
    client_id: str
    name: Optional[str] = None
    website_url: Optional[str] = None
    specialty: Optional[str] = None
    designation: Optional[str] = None
    description: Optional[str] = None
    reference_youtube_channel: Optional[str] = None
    ai_videos_started_from: Optional[str] = None
    topics: Optional[List[TopicItem]] = None


class ClientSelectRequest(BaseModel):
    client_id: str


class ClientDeleteRequest(BaseModel):
    client_id: str


class ClientSyncChannelsRequest(BaseModel):
    client_id: Optional[str] = None
    channel_id: Optional[str] = None


class ClientScrapeRequest(BaseModel):
    client_id: str
    website_url: Optional[str] = None
    specialty: Optional[str] = None
    reference_youtube_channel: Optional[str] = None


class ClientScrapeResponse(BaseModel):
    specialty: Optional[str] = None
    suggested_topics: List[TopicItem] = []
    page_title: Optional[str] = None
    page_snippet: Optional[str] = None
    pages_scraped: int = 0
    website_url: Optional[str] = None
    clients: List[ClientSummary] = []
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    generator: Optional[str] = None
    openai_rationale: Optional[str] = None
    openai_error: Optional[str] = None


class ClientRefreshTopicsRequest(BaseModel):
    client_id: str
    website_url: Optional[str] = None
    specialty: Optional[str] = None
    description: Optional[str] = None
    reference_youtube_channel: Optional[str] = None
    topics: Optional[List[TopicItem]] = None  # current form state; manuals preserved
    user_prompt: Optional[str] = None  # optional instruction to refine the auto list


class ClientRefreshTopicsResponse(BaseModel):
    clients: List[ClientSummary]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    topics: List[TopicItem] = []
    specialty: Optional[str] = None
    page_title: Optional[str] = None
    page_snippet: Optional[str] = None
    pages_scraped: int = 0
    generator: Optional[str] = None
    openai_rationale: Optional[str] = None
    openai_error: Optional[str] = None


class ClientAnalyzeTrendsRequest(BaseModel):
    client_id: str
    force: bool = False


class ClientAnalyzeTrendsResponse(BaseModel):
    clients: List[ClientSummary]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    topics: List[TopicItem] = []
    geo: str = "IN"
    scored: int = 0
    insufficient_data: int = 0
    skipped_cached: int = 0
    fetched_at: Optional[str] = None
    error: Optional[str] = None
    api_tasks: int = 0
    total_cost: float = 0.0


class ClientSaveRecommendationsRequest(BaseModel):
    client_id: str


class ClientSaveRecommendationsResponse(BaseModel):
    clients: List[ClientSummary]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    topics: List[TopicItem] = []
    primary_count: int = 0
    secondary_count: int = 0
    saved_at: Optional[str] = None
    threshold: float = 50.0


class TrackerScriptPlacement(BaseModel):
    year: int
    month: int
    week: int
    card_id: str = ""
    card_type: str = ""


# Content plan (next-topic suggestions)
class YouTubeLocaleMetadata(BaseModel):
    yt_title: Optional[str] = None
    yt_description: Optional[str] = None
    yt_tags: Optional[List[str]] = None
    yt_thumbnail_url: Optional[str] = None
    yt_thumbnail_prompt: Optional[str] = None


class ContentSuggestionItem(BaseModel):
    id: str
    topic_id: str
    topic_text: str
    recommendation_score: float = 0.0
    format: str  # Long | Short
    video_type: str
    title_en: str = ""
    title_hinglish: str = ""
    working_title: Optional[str] = None  # legacy alias
    reasoning: str
    script: Optional[str] = None
    script_target_duration: Optional[str] = None
    script_hook_used: Optional[str] = None
    script_cta: Optional[str] = None
    script_checklist_passed: Optional[bool] = None
    script_checklist_notes: Optional[str] = None
    yt_title: Optional[str] = None
    yt_description: Optional[str] = None
    yt_tags: Optional[List[str]] = None
    yt_thumbnail_url: Optional[str] = None
    yt_thumbnail_prompt: Optional[str] = None
    yt_locales: Optional[Dict[str, YouTubeLocaleMetadata]] = None
    tracker_placements: List[TrackerScriptPlacement] = []


class ContentCoverageSummary(BaseModel):
    total: int = 0
    mapped_to_keyword: int = 0
    out_of_keyword: int = 0


class ContentKeywordVideoRef(BaseModel):
    video_id: str
    title: str = ""
    published_at: str = ""
    view_count: int = 0
    video_type: Optional[str] = None
    format: str = "Long"


class ContentKeywordAnalysisItem(BaseModel):
    topic_id: str
    topic_text: str
    recommendation_score: float = 0.0
    weight: str = "medium"
    covered_long: bool = False
    covered_short: bool = False
    pending_long: bool = True
    pending_short: bool = True
    long_videos: List[ContentKeywordVideoRef] = []
    short_videos: List[ContentKeywordVideoRef] = []
    yt_title: Optional[str] = None
    yt_description: Optional[str] = None
    yt_tags: Optional[List[str]] = None
    yt_thumbnail_url: Optional[str] = None
    yt_thumbnail_prompt: Optional[str] = None
    yt_locales: Optional[Dict[str, YouTubeLocaleMetadata]] = None


class ContentSuggestionsPayload(BaseModel):
    generated_at: Optional[str] = None
    mapped_at: Optional[str] = None
    scripts_generated_at: Optional[str] = None
    count: int = 0
    user_prompt: Optional[str] = None
    items: List[ContentSuggestionItem] = []
    coverage: Optional[ContentCoverageSummary] = None
    keyword_analysis: List[ContentKeywordAnalysisItem] = []
    recent_video_types: List[str] = []


class ClientContentPlanGetRequest(BaseModel):
    client_id: str


class ClientContentPlanMapRequest(BaseModel):
    client_id: str
    force: bool = True


class ClientContentPlanGenerateRequest(BaseModel):
    client_id: str
    count: int = 5
    force_remap: bool = False


class ClientContentPlanRegenerateRequest(BaseModel):
    client_id: str
    count: Optional[int] = None
    user_prompt: str
    force_remap: bool = False


class ClientContentPlanScriptsRequest(BaseModel):
    client_id: str
    example1: Optional[str] = None
    example2: Optional[str] = None


class ClientContentPlanRefineScriptRequest(BaseModel):
    client_id: str
    item_id: str
    user_prompt: str


class ClientContentPlanUpdateScriptRequest(BaseModel):
    client_id: str
    item_id: str
    script: str


class ClientContentPlanNarrateScriptRequest(BaseModel):
    client_id: str
    item_id: Optional[str] = None  # omit / "combined" for all scripts joined
    combined: bool = False
    force: bool = False  # skip disk cache and re-call OpenAI TTS


class ClientContentPlanGenerateMetadataRequest(BaseModel):
    client_id: str
    item_ids: List[str]
    reference_video_ids: List[str] = []
    user_prompt: Optional[str] = None
    languages: List[str] = Field(default_factory=lambda: ["hinglish"])


class ClientContentPlanRefineMetadataRequest(BaseModel):
    client_id: str
    item_id: str
    user_prompt: str
    reference_video_ids: List[str] = []
    language: Optional[str] = None


class ClientContentPlanResponse(BaseModel):
    clients: List[ClientSummary]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None
    suggestions: ContentSuggestionsPayload


# Social Media Schemas
class SocialClientRequest(BaseModel):
    client_id: str

class SocialInstagramMediaRequest(SocialClientRequest):
    limit: int = 30
    after: Optional[str] = None


class InstagramConfigSaveRequest(BaseModel):
    client_id: str
    app_id: str
    app_secret: Optional[str] = None


class InstagramConnectionSummary(BaseModel):
    connected: bool = False
    instagram_user_id: Optional[str] = None
    instagram_username: Optional[str] = None
    token_expires_at: Optional[str] = None
    connected_at: Optional[str] = None


class InstagramConfigResponse(BaseModel):
    client_id: str
    app_id: Optional[str] = None
    has_app_secret: bool = False
    redirect_uri: str
    connection: InstagramConnectionSummary


class InstagramConnectUrlResponse(BaseModel):
    authorization_url: str
    state: str


class InstagramAnalyticsRequest(SocialClientRequest):
    since: Optional[str] = None
    until: Optional[str] = None
    days: Optional[int] = None


class InstagramMediaItem(BaseModel):
    id: str
    media_type: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    permalink: Optional[str] = None
    timestamp: Optional[str] = None
    caption: Optional[str] = None
    selected_as_reference: bool = False


class InstagramMediaUploadResponse(BaseModel):
    count: int

class FacebookConfigSaveRequest(BaseModel):
    client_id: str
    app_id: str
    app_secret: str

class FacebookConnectionSummary(BaseModel):
    connected: bool
    facebook_user_id: Optional[str] = None
    facebook_username: Optional[str] = None
    selected_page_id: Optional[str] = None
    selected_page_name: Optional[str] = None

class FacebookConfigResponse(BaseModel):
    app_id: Optional[str] = None
    redirect_uri: str
    connection: FacebookConnectionSummary

class FacebookConnectUrlResponse(BaseModel):
    authorization_url: str
    state: str

class FacebookPageInfo(BaseModel):
    id: str
    name: str
    access_token: str

class FacebookPageSelectRequest(BaseModel):
    client_id: str
    page_id: str
    page_name: str
    page_access_token: str

class InstagramMediaResponse(BaseModel):
    media: List[InstagramMediaItem] = []
    reference_media: List[InstagramMediaItem] = []
    next_cursor: Optional[str] = None


class SocialScriptedItem(BaseModel):
    id: str
    topic_id: Optional[str] = None
    topic_text: str
    recommendation_score: float = 0.0
    format: Optional[str] = None
    video_type: Optional[str] = None
    title_en: Optional[str] = None
    title_hinglish: Optional[str] = None
    working_title: Optional[str] = None
    script: str


class SocialKeywordItem(BaseModel):
    topic_id: str
    topic_text: str
    recommendation_score: float = 0.0
    weight: str = "medium"


class SocialPostSourcesResponse(BaseModel):
    client_id: str
    scripts_generated_at: Optional[str] = None
    scripted_items: List[SocialScriptedItem] = []
    recommended_keywords: List[SocialKeywordItem] = []


class SocialKeywordPickRequest(BaseModel):
    client_id: str
    count: int = 3


class SocialKeywordPickResponse(BaseModel):
    selected_keywords: List[SocialKeywordItem] = []


class SocialPostDraftGenerateRequest(BaseModel):
    client_id: str
    source_type: str
    content_plan_item_id: Optional[str] = None
    topic_id: Optional[str] = None
    topic_text: Optional[str] = None
    custom_prompt: Optional[str] = None
    reference_media_ids: Optional[List[str]] = None
    reference_image_urls: Optional[str] = None
    # Extra metadata for Festive Posts sections so the UI does not parse topic_id.
    generation_origin: Optional[str] = None

class SocialPostVersionsRequest(BaseModel):
    client_id: str
    source_type: str
    content_plan_item_id: Optional[str] = None
    topic_id: Optional[str] = None


class SocialPostPublishRequest(BaseModel):
    client_id: str
    post_id: str
    caption: str
    targets: List[str] = ["instagram"]
    topic_id: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = None
    week: Optional[int] = None


class SocialPostActionRequest(BaseModel):
    client_id: str
    post_id: str


class SocialPostBrief(BaseModel):
    headline: str
    subheadline: str
    supporting_text: str
    caption: str
    cta: str


class SocialPostDraft(BaseModel):
    id: str
    client_id: str
    platform: str = "instagram"
    source_type: str
    topic_id: Optional[str] = None
    topic_text: str
    content_plan_item_id: Optional[str] = None
    brief: SocialPostBrief
    image_status: str = "pending"
    image_model: Optional[str] = None
    image_url: Optional[str] = None
    reference_media_ids: List[str] = []
    status: str = "draft"
    is_selected: bool = False
    selected_at: Optional[str] = None
    created_at: str
    publish_status: str = "draft"
    publish_targets: List[str] = ["instagram"]
    queue_order: Optional[float] = None
    # Extra metadata for Festive Posts sections so the UI does not parse topic_id.
    # cron-festival = auto column, manual-festival = manual section. 9 AM uses topic_id.
    generation_origin: Optional[str] = None
    instagram_post_id: Optional[str] = None
    facebook_post_id: Optional[str] = None
    instagram_permalink: Optional[str] = None
    facebook_permalink: Optional[str] = None

class SocialPostQueueAddRequest(BaseModel):
    post_id: str
    client_id: str
    targets: Optional[List[str]] = ["instagram"]


class SocialPostQueueAddBulkRequest(BaseModel):
    post_ids: List[str]
    client_id: str
    targets: Optional[List[str]] = ["instagram"]


class SocialPostTargetsUpdateRequest(BaseModel):
    post_id: str
    client_id: str
    targets: List[str] = ["instagram"]


class SocialPostQueueRemoveRequest(BaseModel):
    client_id: str
    post_id: str

class SocialPostQueueReorderRequest(BaseModel):
    client_id: str
    ordered_post_ids: List[str]

class SocialPostQueueEditRequest(BaseModel):
    client_id: str
    post_id: str
    caption: str

class SocialScheduleSaveRequest(BaseModel):
    client_id: str
    frequency: str
    selected_days: List[str] = []
    auto_fallback: bool = False
    facebook_auto_publish: bool = False
    festive_auto_publish: bool = False
    festive_facebook_auto_publish: bool = False
    posts_per_day: int = 1

class SocialScheduleResponse(BaseModel):
    frequency: str = "off"
    selected_days: List[str] = []
    auto_fallback: bool = False
    facebook_auto_publish: bool = False
    festive_auto_publish: bool = False
    festive_facebook_auto_publish: bool = False
    posts_per_day: int = 1


class SocialPostDraftResponse(BaseModel):
    post: SocialPostDraft


class SocialPostVersionsResponse(BaseModel):
    posts: List[SocialPostDraft] = []
    current_post: Optional[SocialPostDraft] = None


# YouTube Channel Schemas
class YouTubeChannelInfo(BaseModel):
    id: str
    title: str
    description: str
    custom_url: Optional[str] = None
    published_at: str = ""
    view_count: int
    subscriber_count: int
    video_count: int
    language: Optional[str] = None


class YouTubeChannelListResponse(BaseModel):
    channels: List[YouTubeChannelInfo]
    active_client_id: Optional[str] = None
    active_channel_id: Optional[str] = None


class ChannelListRequest(BaseModel):
    client_id: Optional[str] = None


class ChannelGetRequest(BaseModel):
    channel_id: Optional[str] = None
    client_id: Optional[str] = None


class ChannelSelectRequest(BaseModel):
    channel_id: str
    client_id: Optional[str] = None


class ChannelDisconnectRequest(BaseModel):
    channel_id: str
    client_id: str


class ChannelLanguageAssignments(BaseModel):
    hinglish: List[str] = []
    arabic: List[str] = []
    russian: List[str] = []


class ChannelSetLanguagesRequest(BaseModel):
    client_id: str
    assignments: ChannelLanguageAssignments


# YouTube Video Schemas
class YouTubeVideoInfo(BaseModel):
    id: str
    title: str
    published_at: str
    thumbnail_url: Optional[str] = None
    view_count: int
    like_count: int
    comment_count: int
    duration: Optional[str] = None
    duration_seconds: Optional[int] = 0
    duration_type: Optional[str] = "long"
    is_short: Optional[bool] = False
    short_link: Optional[str] = None
    privacy_status: Optional[str] = "public"  # public | unlisted | private
    notes: Optional[str] = ""
    metadata_fields: Optional[dict] = {}


class YouTubeVideoListResponse(BaseModel):
    videos: List[YouTubeVideoInfo]


class VideoListRequest(BaseModel):
    channel_id: Optional[str] = None
    client_id: Optional[str] = None


class VideoGetRequest(BaseModel):
    video_id: str
    channel_id: Optional[str] = None
    client_id: Optional[str] = None


class VideoSyncRequest(BaseModel):
    channel_id: Optional[str] = None
    client_id: Optional[str] = None


class VideoUpdateRequest(BaseModel):
    video_id: str
    channel_id: Optional[str] = None
    client_id: Optional[str] = None
    notes: Optional[str] = None
    metadata_fields: Optional[dict] = None


# YouTube Analytics Schemas
class YouTubeAnalyticsRequest(BaseModel):
    start_date: date
    end_date: date
    client_id: Optional[str] = None
    channel_id: Optional[str] = None
    metrics: str = "views,comments,likes,dislikes,shares,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost"
    dimensions: str = "day"
    sort: Optional[str] = "day"


class YouTubeAnalyticsRow(BaseModel):
    dimension_value: str
    metrics: dict


class YouTubeAnalyticsResponse(BaseModel):
    column_headers: List[str]
    rows: List[List[Any]]


# Google OAuth
class GoogleLoginRequest(BaseModel):
    client_id: str


# Monthly YouTube AI reports
class ReportListRequest(BaseModel):
    client_id: str


class ReportGetRequest(BaseModel):
    report_id: str


class ReportGenerateRequest(BaseModel):
    client_id: str
    report_month: Optional[str] = None  # YYYY-MM; default = previous calendar month
    channel_ids: Optional[List[str]] = None


class ReportRefineRequest(BaseModel):
    report_id: str
    prompt: str


class ReportRefineHistoryItem(BaseModel):
    prompt: str
    created_at: str


class ReportSummary(BaseModel):
    id: str
    client_id: str
    report_month: str
    previous_month: Optional[str] = None
    ai_videos_started_from: Optional[str] = None
    channel_ids: List[str] = []
    status: str
    error: Optional[str] = None
    has_metrics_cache: bool = False
    refine_history: List[ReportRefineHistoryItem] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ReportListResponse(BaseModel):
    reports: List[ReportSummary]


class ReportDetailResponse(BaseModel):
    id: str
    client_id: str
    report_month: str
    previous_month: Optional[str] = None
    ai_videos_started_from: Optional[str] = None
    channel_ids: List[str] = []
    status: str
    error: Optional[str] = None
    has_metrics_cache: bool = False
    narrative: Optional[dict] = None
    metrics_summary: Optional[dict] = None
    refine_history: List[ReportRefineHistoryItem] = []
    html_url: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WeeklyTrackerGetRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int


class WeeklyTrackerMonthSummaryRequest(BaseModel):
    client_id: str
    year: int
    month: int


class WeeklyTrackerWeekSummary(BaseModel):
    week: int
    out: int
    total: int
    to_start: int


class WeeklyTrackerMonthSummaryResponse(BaseModel):
    weeks: List[WeeklyTrackerWeekSummary] = []


class WeeklyTrackerPocSummaryRequest(BaseModel):
    year: int
    month: int


class WeeklyTrackerPocClientSummary(BaseModel):
    client_id: str
    name: str
    weeks: List[WeeklyTrackerWeekSummary] = []


class WeeklyTrackerPocSummaryResponse(BaseModel):
    weeks: List[WeeklyTrackerWeekSummary] = []
    clients: List[WeeklyTrackerPocClientSummary] = []


class WeeklyTrackerDestination(BaseModel):
    id: str
    language: Optional[str] = None
    platform: str
    url: str = ""
    label: Optional[str] = None


class WeeklyTrackerAttachment(BaseModel):
    id: str
    name: str = ""
    url: str
    content_type: Optional[str] = None


class WeeklyTrackerNote(BaseModel):
    id: str
    text: str = ""
    language: str = "all"
    attachments: List[WeeklyTrackerAttachment] = []
    created_by: str = ""
    created_at: str = ""


class WeeklyTrackerDoctorFile(BaseModel):
    id: str
    name: str = ""
    url: str
    created_by: str = ""
    created_at: str = ""


class WeeklyTrackerExtraSlot(BaseModel):
    id: str
    label: str = "Extra"
    platform: str = "other"


class WeeklyTrackerStructure(BaseModel):
    platforms: List[str] = []
    extra_slots: List[WeeklyTrackerExtraSlot] = []
    hidden_cells: List[str] = []


class WeeklyTrackerAssets(BaseModel):
    script_url: str = ""
    script_text: str = ""
    audio_url: str = ""
    video_url: str = ""


class WeeklyTrackerCard(BaseModel):
    id: str
    type: str
    title: str = ""
    started: bool = False
    collapsed: bool = True
    sort_order: int = 0
    stage: str = "planned"
    is_default: bool = False
    assets: WeeklyTrackerAssets = Field(default_factory=WeeklyTrackerAssets)
    destinations: List[WeeklyTrackerDestination] = []
    structure: WeeklyTrackerStructure = Field(default_factory=WeeklyTrackerStructure)
    generated_post_ids: List[str] = []
    destination_post_ids: Dict[str, str] = {}
    feedback_notes: List[WeeklyTrackerNote] = []
    doctor_notes: List[WeeklyTrackerNote] = []
    doctor_files: List[WeeklyTrackerDoctorFile] = []
    content_plan_item_id: Optional[str] = None
    topic_id: Optional[str] = None


class WeeklyTrackerAttachScriptRequest(BaseModel):
    client_id: str
    item_id: str
    year: int
    month: int
    week: int
    card_id: Optional[str] = None


class WeeklyTrackerScriptLinksRequest(BaseModel):
    client_id: str


class WeeklyTrackerSaveRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int
    cards: List[WeeklyTrackerCard]


class WeeklyTrackerNoteAddRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int
    card_id: str
    section: str  # feedback | doctor
    text: str = ""
    language: str = "all"
    attachments: List[WeeklyTrackerAttachment] = []


class WeeklyTrackerDoc(BaseModel):
    id: str
    client_id: str
    year: int
    month: int
    week: int
    cards: List[dict] = []
    languages: List[str] = []
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class WeeklyTrackerResponse(BaseModel):
    tracker: WeeklyTrackerDoc
    languages: List[str] = []


class CustomTrackerSubtask(BaseModel):
    id: str
    title: str = ""
    done: bool = False
    due_date: str = ""
    comment: str = ""


class CustomTrackerTask(BaseModel):
    id: str
    title: str = ""
    done: bool = False
    due_date: str = ""
    comment: str = ""
    subtasks: List[CustomTrackerSubtask] = []


class CustomTrackerNote(BaseModel):
    id: str
    text: str = ""
    created_by: str = ""
    created_at: str = ""


class CustomTrackerIssue(BaseModel):
    id: str
    display_id: str = ""
    title: str = ""
    status: str = "todo"
    priority: str = "p1"
    collapsed: bool = False
    comment: str = ""
    tasks: List[CustomTrackerTask] = []
    notes: List[CustomTrackerNote] = []


class CustomTrackerCategory(BaseModel):
    id: str
    name: str
    is_default: bool = False
    collapsed: bool = False
    issues: List[CustomTrackerIssue] = []


class CustomTrackerGetRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int


class CustomTrackerSaveRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int
    categories: List[CustomTrackerCategory]
    issue_seq: int = 1


class CustomTrackerDoc(BaseModel):
    id: str
    client_id: str
    year: int
    month: int
    week: int
    categories: List[dict] = []
    issue_seq: int = 1
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class CustomTrackerResponse(BaseModel):
    tracker: CustomTrackerDoc


class CustomTrackerWeekSummary(BaseModel):
    week: int
    issues: int = 0
    done: int = 0
    open: int = 0


class CustomTrackerMonthSummaryResponse(BaseModel):
    weeks: List[CustomTrackerWeekSummary] = []


class TrackerSheetClientSummary(BaseModel):
    client_id: str
    name: str


class TrackerSheetClientsResponse(BaseModel):
    clients: List[TrackerSheetClientSummary] = []


class TrackerSheetWeeklyRequest(BaseModel):
    client_id: str
    year: int
    month: int


class TrackerSheetWeeklyRow(BaseModel):
    week: int
    card_id: str
    row_key: str
    content_type: str
    content_type_label: str
    stage: str
    stage_label: str
    links: List[str] = []


class TrackerSheetWeeklyResponse(BaseModel):
    year: int
    month: int
    rows: List[TrackerSheetWeeklyRow] = []
    comments: Dict[str, str] = {}


class TrackerSheetCustomRequest(BaseModel):
    client_id: str
    year: int
    month: int


class TrackerSheetCustomWeek(BaseModel):
    week: int
    categories: List[dict] = []


class TrackerSheetCustomResponse(BaseModel):
    year: int
    month: int
    weeks: List[TrackerSheetCustomWeek] = []


class TrackerSheetCommentSaveRequest(BaseModel):
    client_id: str
    year: int
    month: int
    week: int
    row_key: str
    comment: str = ""


class TrackerSheetCommentSaveResponse(BaseModel):
    comment: dict


class ContentVideoPostedUrl(BaseModel):
    url: str
    posted_at: str
    channel_id: Optional[str] = None
    language: Optional[str] = None
    youtube_id: Optional[str] = None
    post_id: Optional[str] = None


class ContentVideoSourceUrl(BaseModel):
    url: str
    posted_at: str
    kind: str  # youtube | social
    channel_id: Optional[str] = None
    language: Optional[str] = None


class ContentVideo(BaseModel):
    id: str
    client_id: str
    topic_id: str
    topic_text: str = ""
    source: str = "manual"  # script | manual
    content_plan_item_id: Optional[str] = None
    yt_locales: Dict[str, YouTubeLocaleMetadata] = {}
    yt_title: Optional[str] = None
    yt_description: Optional[str] = None
    yt_tags: Optional[List[str]] = None
    yt_thumbnail_url: Optional[str] = None
    yt_thumbnail_prompt: Optional[str] = None
    youtube_urls: List[ContentVideoPostedUrl] = []
    instagram_urls: List[ContentVideoPostedUrl] = []
    facebook_urls: List[ContentVideoPostedUrl] = []
    source_urls: List[ContentVideoSourceUrl] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VideoUploadRequest(BaseModel):
    client_id: str
    channel_id: str
    drive_link: str
    title: str
    description: str
    tags: List[str]
    thumbnail_url: Optional[str] = None
    post_to_instagram: bool = False
    post_to_facebook: bool = False
    topic_id: Optional[str] = None
    language: Optional[str] = None
    social_source_url: Optional[str] = None
