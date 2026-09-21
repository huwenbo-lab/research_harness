"""Bounded work-level publication-window evidence, never actual writing dates.

Chapter titles can suggest narrative boundaries but cannot verify chapter prose.
Visible directory order and publication/update semantics remain explicit.
"""
import re

from date_parser_v04 import date_value, end_role


SCOPE = "work_date_endpoints"
AUXILIARY = re.compile(r"番外|外传|花絮|后记|感言|公告|通知|请假|新书|上架|题外话|序言|前言|作者的话|作品相关|预告")


def publication_window(work_id, chapters, status=None):
    """Return at most four selected endpoints and a fixed set of date roles."""
    def endpoint(row):
        return {
            "chapter_id": row.get("chapter_id"),
            "chapter_number": row.get("chapter_number_raw"),
            "title": row.get("chapter_title"),
            "volume": row.get("volume"),
            "url": row.get("chapter_url") or row.get("url"),
            "publication_date": row.get("publication_date") or row.get("publish_time_as_supplied"),
            "update_date": row.get("update_date") or row.get("update_time_as_supplied"),
        }

    rows = [endpoint(row) for row in chapters]
    # Titles and any supplied volume label are only classification evidence.
    auxiliary = [bool(AUXILIARY.search(str(row.get("chapter_title") or "") + " " + str(row.get("volume") or "")))
                 for row in chapters]
    main = [i for i in range(len(rows)) if not auxiliary[i]]
    explicit = [i for i in main if end_role(rows[i]["title"]) == "main_story_end_marker_update"]
    broader = [i for i in main if end_role(rows[i]["title"]) in {"all_text_end_marker_update", "ending_marker_update"}]
    complete = str(status or "").strip().lower() in {"完本", "已完成", "完结", "completed", "finished"}
    end, basis = None, "unresolved"
    markers = explicit or broader
    if len(markers) == 1:
        end = markers[0]
        basis = "explicit_main_text_title" if explicit else "ending_title"
    elif len(markers) > 1:
        basis = "ambiguous_ending_titles"
    elif main and main[-1] < len(rows) - 1:
        end, basis = main[-1], "before_trailing_auxiliary_titles"
    elif main and complete:
        end, basis = main[-1], "completed_status_last_non_auxiliary"
    elif main:
        basis = "no_ending_marker_or_completed_status"

    window = {
        "first_visible_chapter": rows[0] if rows else None,
        "main_text_start_candidate": rows[main[0]] if main else None,
        "main_text_end_candidate": rows[end] if end is not None else None,
        "last_visible_chapter": rows[-1] if rows else None,
        "start_basis": "first_visible_non_auxiliary_title" if main else "unresolved",
        "end_basis": basis,
        "boundary_status": "candidate_requires_review" if end is not None else "unresolved",
        "directory_coverage": "not_independently_verified",
        "chapter_count_observed": len(rows),
        "auxiliary_title_count": sum(auxiliary),
        "ending_title_count": len(markers),
        "interpretation": "public_serialization_evidence_not_actual_writing_dates",
    }
    dates = []
    def add(row, field, role, selection):
        value = row.get(field) if row else None
        if value and date_value(value):
            dates.append({"work_id": work_id, "role": role, "value": value,
                          "basis": selection + (":explicit_publication" if field == "publication_date" else ":update_only")})

    for key, prefix in (("first_visible_chapter", "first_observed_chapter"),
                        ("last_visible_chapter", "last_observed_chapter")):
        row = window[key]
        for field, suffix in (("publication_date", "publication"), ("update_date", "update")):
            add(row, field, prefix + "_" + suffix, "visible_directory_order")
    if rows and str(rows[0]["chapter_number"]) == "1":
        add(rows[0], "publication_date", "first_chapter_publication", "explicit_first_chapter_number")
    for key, prefix, selection in (("main_text_start_candidate", "main_text_start", window["start_basis"]),
                                   ("main_text_end_candidate", "main_text_end", basis)):
        for field, suffix in (("publication_date", "publication_candidate"), ("update_date", "update_candidate")):
            add(window[key], field, prefix + "_" + suffix, selection)
    return window, dates
