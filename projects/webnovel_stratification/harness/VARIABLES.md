# VARIABLES

## A. work_master

Primary key: `platform + work_id`.

| Variable | Meaning |
|---|---|
| platform | `qidian` / `jjwxc` |
| work_id | Stable platform work/novel ID where available |
| title_current | Current observed title |
| author_name_current | Current observed author name |
| author_id | Stable platform author ID where available |
| first_pub_date_raw | Raw platform/source date string |
| first_pub_date | Parsed date if defensible |
| first_pub_year | Parsed year if defensible |
| date_type | `platform_publication`, `first_chapter_update`, `snapshot_presence`, `external_bibliography`, etc. |
| date_confidence | `high`, `medium`, `low`, `unresolved` |
| genre_major | Platform major genre/category |
| genre_minor | Platform subgenre/category |
| audience_channel | Platform-defined channel if available; do not infer reader gender |
| status | serializing / completed / paused / other raw category |
| word_count | Observed word count |
| work_url | Canonical work URL |
| first_seen_source | Source used to create master record |
| first_seen_at | Research collection date |
| last_seen_at | Latest research collection date |

## B. source_observation

One row per work-source observation. Primary key can be a generated `observation_id`.

Required fields: `platform`, `work_id`, `source_name`, `source_url`, `snapshot_date`, `title_observed`, `author_observed`, `date_raw`, `genre_raw`, `status_raw`, `word_count_raw`, `retrieval_status`, `collection_timestamp`, `raw_file`.

This table should retain contradictory or changing information rather than silently overwriting it.

## C. text_availability

Fields: `platform`, `work_id`, `synopsis_available`, `opening_chapters_available`, `free_chapters_available`, `continuous_text_available`, `full_text_available`, `text_source`, `license_or_access_note`, `checked_at`.

Availability does not imply permission to redistribute text.

## D. market_visibility (future)

Possible fields: `platform`, `work_id`, `observation_date`, `ranking_type`, `rank`, `votes`, `comments`, `favorites`, `recommendation_slot`, `source_url`.

## E. sociological_coding (future)

Keep substantive coding separate from metadata. Initial candidate dimensions:

- `protagonist_upbringing_class`
- `biological_family_class`
- `usable_family_resources_at_start`
- `education_credential_role`
- `effort_role`
- `talent_role`
- `institutional_route_role`
- `family_resource_role`
- `inheritance_role`
- `marriage_role`
- `patronage_role`
- `hidden_elite_identity`
- `status_restoration`
- `genuine_upward_mobility`
- `success_legitimation_type`
- `coding_evidence_location`
- `coder_method`
- `coding_confidence`

Do not collapse upbringing conditions, biological family status, and usable resources into a single family-background variable during the first coding pass.
